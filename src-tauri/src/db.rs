use std::{
    collections::{BTreeMap, HashMap},
    fs,
    path::PathBuf,
};

use anyhow::{anyhow, Context, Result};
use chrono::{DateTime, Duration, Local, NaiveDate, NaiveDateTime, TimeZone};
use rusqlite::{params, Connection, OptionalExtension};

use crate::{
    models::{
        ActivitySampleRecord, CountItem, SampleOverview, SettingsDto, SettingsInput, SlotSummary,
        WorkInterval,
    },
    prediction::build_prediction,
};

pub const SAMPLE_RETENTION_DAYS: i64 = 90;

#[derive(Clone)]
pub struct Database {
    path: PathBuf,
}

#[derive(Clone, Debug)]
pub struct RuntimeSettings {
    pub excluded_processes: Vec<String>,
    pub excluded_title_keywords: Vec<String>,
}

impl Database {
    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }

    pub fn initialize(&self) -> Result<()> {
        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }

        let connection = self.connection()?;
        connection.execute_batch(
            "
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS activity_samples (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              captured_at TEXT NOT NULL,
              slot_start TEXT NOT NULL,
              window_title TEXT NOT NULL,
              process_name TEXT NOT NULL,
              classification TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_activity_samples_slot_start
            ON activity_samples(slot_start);

            CREATE TABLE IF NOT EXISTS work_intervals (
              slot_start TEXT PRIMARY KEY,
              slot_end TEXT NOT NULL,
              status TEXT NOT NULL,
              predicted_text TEXT NOT NULL,
              predicted_candidates TEXT NOT NULL,
              confirmed_text TEXT,
              summary TEXT NOT NULL,
              snooze_until TEXT,
              last_prompt_at TEXT,
              prompt_count INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS excluded_processes (
              value TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS excluded_title_keywords (
              value TEXT PRIMARY KEY
            );
            ",
        )?;

        Ok(())
    }

    pub fn load_runtime_settings(&self) -> Result<RuntimeSettings> {
        let connection = self.connection()?;
        Ok(RuntimeSettings {
            excluded_processes: query_column(
                &connection,
                "SELECT value FROM excluded_processes ORDER BY value",
            )?,
            excluded_title_keywords: query_column(
                &connection,
                "SELECT value FROM excluded_title_keywords ORDER BY value",
            )?,
        })
    }

    pub fn load_settings(&self, autostart_enabled: bool) -> Result<SettingsDto> {
        let runtime = self.load_runtime_settings()?;
        Ok(SettingsDto {
            excluded_processes: runtime.excluded_processes,
            excluded_title_keywords: runtime.excluded_title_keywords,
            autostart_enabled,
            retention_days: SAMPLE_RETENTION_DAYS,
        })
    }

    pub fn save_settings(&self, input: &SettingsInput) -> Result<RuntimeSettings> {
        let connection = self.connection()?;
        let transaction = connection.unchecked_transaction()?;

        transaction.execute("DELETE FROM excluded_processes", [])?;
        for value in normalize_lines(&input.excluded_processes) {
            transaction.execute(
                "INSERT INTO excluded_processes (value) VALUES (?)",
                params![value],
            )?;
        }

        transaction.execute("DELETE FROM excluded_title_keywords", [])?;
        for value in normalize_lines(&input.excluded_title_keywords) {
            transaction.execute(
                "INSERT INTO excluded_title_keywords (value) VALUES (?)",
                params![value],
            )?;
        }

        transaction.commit()?;
        self.load_runtime_settings()
    }

    pub fn insert_sample(&self, sample: &ActivitySampleRecord) -> Result<()> {
        let connection = self.connection()?;
        connection.execute(
            "INSERT INTO activity_samples (captured_at, slot_start, window_title, process_name, classification)
             VALUES (?, ?, ?, ?, ?)",
            params![
                sample.captured_at.to_rfc3339(),
                sample.slot_start.to_rfc3339(),
                sample.window_title,
                sample.process_name,
                sample.classification,
            ],
        )?;

        Ok(())
    }

    pub fn latest_sample(&self) -> Result<Option<SampleOverview>> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT captured_at, window_title, process_name, classification
                 FROM activity_samples
                 ORDER BY captured_at DESC
                 LIMIT 1",
                [],
                |row| {
                    Ok(SampleOverview {
                        captured_at: row.get(0)?,
                        window_title: row.get(1)?,
                        process_name: row.get(2)?,
                        classification: row.get(3)?,
                    })
                },
            )
            .optional()
            .map_err(Into::into)
    }

    pub fn recent_intervals(&self, limit: usize) -> Result<Vec<WorkInterval>> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
             FROM work_intervals
             ORDER BY slot_start DESC
             LIMIT ?",
        )?;

        let rows = statement.query_map(params![limit as i64], map_interval_row)?;
        let mut intervals = Vec::new();

        for row in rows {
            intervals.push(row?);
        }

        Ok(intervals)
    }

    pub fn latest_pending_interval(&self) -> Result<Option<WorkInterval>> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
                 FROM work_intervals
                 WHERE status = 'pending'
                 ORDER BY slot_start ASC
                 LIMIT 1",
                [],
                map_interval_row,
            )
            .optional()
            .map_err(Into::into)
    }

    pub fn ensure_completed_intervals(&self, current_slot_start: DateTime<Local>) -> Result<()> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT DISTINCT slot_start
             FROM activity_samples
             WHERE slot_start < ?
               AND slot_start NOT IN (SELECT slot_start FROM work_intervals)
             ORDER BY slot_start ASC",
        )?;

        let rows = statement.query_map(params![current_slot_start.to_rfc3339()], |row| {
            row.get::<_, String>(0)
        })?;
        let mut slot_starts = Vec::new();
        for row in rows {
            slot_starts.push(row?);
        }

        for slot_start in slot_starts {
            let slot_start_dt = parse_local(&slot_start)?;
            let slot_end = slot_start_dt + Duration::minutes(30);
            let summary = self.summary_for_slot(slot_start_dt)?;
            let history = self.confirmed_history(48)?;
            let (predicted_text, predicted_candidates) = build_prediction(&summary, &history);
            let now = Local::now().to_rfc3339();

            connection.execute(
                "INSERT OR IGNORE INTO work_intervals
                 (slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count, created_at, updated_at)
                 VALUES (?, ?, 'pending', ?, ?, NULL, ?, NULL, NULL, 0, ?, ?)",
                params![
                    slot_start_dt.to_rfc3339(),
                    slot_end.to_rfc3339(),
                    predicted_text,
                    serde_json::to_string(&predicted_candidates)?,
                    serde_json::to_string(&summary)?,
                    now,
                    now,
                ],
            )?;
        }

        Ok(())
    }

    pub fn backfill_missed_intervals(&self, current_slot_start: DateTime<Local>) -> Result<()> {
        let connection = self.connection()?;

        let last_known: Option<String> = connection.query_row(
            "SELECT MAX(slot_start) FROM (
                SELECT slot_start FROM activity_samples
                UNION
                SELECT slot_start FROM work_intervals
            )",
            [],
            |row| row.get(0),
        )?;

        let Some(last_known) = last_known else {
            return Ok(());
        };

        let mut slot = parse_local(&last_known)? + Duration::minutes(30);
        let history = self.confirmed_history(48)?;
        let now = Local::now().to_rfc3339();
        let empty_summary = SlotSummary {
            sample_count: 0,
            away_count: 0,
            excluded_count: 0,
            active_duration_seconds: 0,
            top_processes: Vec::new(),
            top_titles: Vec::new(),
            top_title_tokens: Vec::new(),
        };
        let (predicted_text, predicted_candidates) = build_prediction(&empty_summary, &history);
        let predicted_candidates_json = serde_json::to_string(&predicted_candidates)?;
        let empty_summary_json = serde_json::to_string(&empty_summary)?;

        while slot < current_slot_start {
            let slot_end = slot + Duration::minutes(30);

            connection.execute(
                "INSERT OR IGNORE INTO work_intervals
                 (slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count, created_at, updated_at)
                 VALUES (?, ?, 'pending', ?, ?, NULL, ?, NULL, NULL, 0, ?, ?)",
                params![
                    slot.to_rfc3339(),
                    slot_end.to_rfc3339(),
                    predicted_text,
                    predicted_candidates_json,
                    empty_summary_json,
                    now,
                    now,
                ],
            )?;

            slot = slot_end;
        }

        Ok(())
    }

    pub fn due_prompt_interval(
        &self,
        current_slot_start: DateTime<Local>,
        now: DateTime<Local>,
    ) -> Result<Option<WorkInterval>> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
                 FROM work_intervals
                 WHERE status = 'pending'
                   AND slot_start < ?
                   AND (snooze_until IS NULL OR snooze_until <= ?)
                   AND (last_prompt_at IS NULL OR snooze_until IS NOT NULL)
                 ORDER BY slot_start ASC
                 LIMIT 1",
                params![current_slot_start.to_rfc3339(), now.to_rfc3339()],
                map_interval_row,
            )
            .optional()
            .map_err(Into::into)
    }

    pub fn mark_prompted(&self, slot_start: &str) -> Result<()> {
        let connection = self.connection()?;
        connection.execute(
            "UPDATE work_intervals
             SET last_prompt_at = ?, prompt_count = prompt_count + 1, snooze_until = NULL, updated_at = ?
             WHERE slot_start = ?",
            params![Local::now().to_rfc3339(), Local::now().to_rfc3339(), slot_start],
        )?;
        Ok(())
    }

    pub fn snooze_interval(&self, slot_start: &str, minutes: i64) -> Result<()> {
        let connection = self.connection()?;
        let snooze_until = (Local::now() + Duration::minutes(minutes)).to_rfc3339();
        connection.execute(
            "UPDATE work_intervals
             SET snooze_until = ?, updated_at = ?
             WHERE slot_start = ?",
            params![snooze_until, Local::now().to_rfc3339(), slot_start],
        )?;
        Ok(())
    }

    pub fn confirm_interval(&self, slot_start: &str, text: &str) -> Result<()> {
        let connection = self.connection()?;
        let interval = self
            .interval_by_slot(slot_start)?
            .ok_or_else(|| anyhow!("interval not found for {}", slot_start))?;
        let confirmed_text = if text.trim().is_empty() {
            interval.predicted_text
        } else {
            text.trim().to_string()
        };

        connection.execute(
            "UPDATE work_intervals
             SET status = 'confirmed', confirmed_text = ?, snooze_until = NULL, updated_at = ?
             WHERE slot_start = ?",
            params![confirmed_text, Local::now().to_rfc3339(), slot_start],
        )?;
        Ok(())
    }

    pub fn interval_by_slot(&self, slot_start: &str) -> Result<Option<WorkInterval>> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
                 FROM work_intervals
                 WHERE slot_start = ?",
                params![slot_start],
                map_interval_row,
            )
            .optional()
            .map_err(Into::into)
    }

    pub fn intervals_for_date(&self, date: NaiveDate) -> Result<Vec<WorkInterval>> {
        let connection = self.connection()?;
        let start = Local
            .from_local_datetime(&date.and_hms_opt(0, 0, 0).unwrap())
            .single()
            .ok_or_else(|| anyhow!("invalid local date {}", date))?;
        let end = start + Duration::days(1);

        let mut statement = connection.prepare(
            "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
             FROM work_intervals
             WHERE slot_start >= ? AND slot_start < ?
             ORDER BY slot_start ASC",
        )?;

        let rows = statement.query_map(
            params![start.to_rfc3339(), end.to_rfc3339()],
            map_interval_row,
        )?;
        let mut intervals = Vec::new();

        for row in rows {
            intervals.push(row?);
        }

        Ok(intervals)
    }

    pub fn cleanup_expired_samples(&self) -> Result<()> {
        let connection = self.connection()?;
        let threshold = (Local::now() - Duration::days(SAMPLE_RETENTION_DAYS)).to_rfc3339();
        connection.execute(
            "DELETE FROM activity_samples WHERE captured_at < ?",
            params![threshold],
        )?;
        Ok(())
    }

    fn confirmed_history(&self, limit: usize) -> Result<Vec<WorkInterval>> {
        let connection = self.connection()?;
        let mut statement = connection.prepare(
            "SELECT slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count
             FROM work_intervals
             WHERE status = 'confirmed'
             ORDER BY slot_start DESC
             LIMIT ?",
        )?;

        let rows = statement.query_map(params![limit as i64], map_interval_row)?;
        let mut intervals = Vec::new();

        for row in rows {
            intervals.push(row?);
        }

        Ok(intervals)
    }

    fn summary_for_slot(&self, slot_start: DateTime<Local>) -> Result<SlotSummary> {
        let connection = self.connection()?;
        let slot_key = slot_start.to_rfc3339();

        let sample_count: usize = connection.query_row(
            "SELECT COUNT(*) FROM activity_samples WHERE slot_start = ?",
            params![slot_key],
            |row| row.get(0),
        )?;

        let away_count: usize = connection.query_row(
            "SELECT COUNT(*) FROM activity_samples WHERE slot_start = ? AND classification = 'away'",
            params![slot_key],
            |row| row.get(0),
        )?;

        let excluded_count: usize = connection.query_row(
            "SELECT COUNT(*) FROM activity_samples WHERE slot_start = ? AND classification = 'excluded'",
            params![slot_key],
            |row| row.get(0),
        )?;

        let top_processes = grouped_counts(
            &connection,
            "SELECT process_name, COUNT(*) AS count
             FROM activity_samples
             WHERE slot_start = ? AND classification = 'active'
             GROUP BY process_name
             ORDER BY count DESC, process_name ASC
             LIMIT 5",
            &slot_key,
        )?;

        let top_titles = grouped_counts(
            &connection,
            "SELECT window_title, COUNT(*) AS count
             FROM activity_samples
             WHERE slot_start = ? AND classification = 'active'
             GROUP BY window_title
             ORDER BY count DESC, window_title ASC
             LIMIT 5",
            &slot_key,
        )?;

        let title_tokens = title_tokens(&connection, &slot_key)?;

        Ok(SlotSummary {
            sample_count,
            away_count,
            excluded_count,
            active_duration_seconds: sample_count.saturating_sub(away_count + excluded_count) * 3,
            top_processes,
            top_titles,
            top_title_tokens: title_tokens,
        })
    }

    fn connection(&self) -> Result<Connection> {
        Connection::open(&self.path)
            .with_context(|| format!("failed to open {}", self.path.display()))
    }
}

fn grouped_counts(
    connection: &Connection,
    query: &str,
    slot_start: &str,
) -> Result<Vec<CountItem>> {
    let mut statement = connection.prepare(query)?;
    let rows = statement.query_map(params![slot_start], |row| {
        Ok(CountItem {
            name: row.get(0)?,
            count: row.get(1)?,
        })
    })?;

    let mut items = Vec::new();
    for row in rows {
        items.push(row?);
    }

    Ok(items)
}

fn title_tokens(connection: &Connection, slot_start: &str) -> Result<Vec<CountItem>> {
    let mut statement = connection.prepare(
        "SELECT window_title, COUNT(*) AS count
         FROM activity_samples
         WHERE slot_start = ? AND classification = 'active'
         GROUP BY window_title",
    )?;

    let rows = statement.query_map(params![slot_start], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, usize>(1)?))
    })?;

    let mut counts: HashMap<String, usize> = HashMap::new();

    for row in rows {
        let (title, weight) = row?;
        for token in tokenize(&title) {
            *counts.entry(token).or_insert(0) += weight;
        }
    }

    let mut ordered: Vec<(String, usize)> = counts.into_iter().collect();
    ordered.sort_by(|left, right| right.1.cmp(&left.1).then_with(|| left.0.cmp(&right.0)));

    Ok(ordered
        .into_iter()
        .take(8)
        .map(|(name, count)| CountItem { name, count })
        .collect())
}

fn tokenize(title: &str) -> Vec<String> {
    title
        .split(|character: char| {
            !(character.is_alphanumeric()
                || ('\u{3040}'..='\u{30ff}').contains(&character)
                || ('\u{4e00}'..='\u{9faf}').contains(&character))
        })
        .filter_map(|token| {
            let trimmed = token.trim().to_lowercase();
            if trimmed.len() < 2 {
                None
            } else {
                Some(trimmed)
            }
        })
        .collect()
}

fn parse_local(value: &str) -> Result<DateTime<Local>> {
    if let Ok(parsed) = DateTime::parse_from_rfc3339(value) {
        return Ok(parsed.with_timezone(&Local));
    }

    let naive = NaiveDateTime::parse_from_str(value, "%Y-%m-%d %H:%M:%S")
        .with_context(|| format!("failed to parse timestamp {}", value))?;
    Local
        .from_local_datetime(&naive)
        .single()
        .ok_or_else(|| anyhow!("invalid local timestamp {}", value))
}

fn query_column(connection: &Connection, query: &str) -> Result<Vec<String>> {
    let mut statement = connection.prepare(query)?;
    let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
    let mut values = Vec::new();
    for row in rows {
        values.push(row?);
    }
    Ok(values)
}

fn normalize_lines(values: &[String]) -> Vec<String> {
    let mut map = BTreeMap::new();
    for value in values {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            map.insert(trimmed.to_lowercase(), trimmed.to_string());
        }
    }
    map.into_values().collect()
}

fn map_interval_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<WorkInterval> {
    Ok(WorkInterval {
        slot_start: row.get(0)?,
        slot_end: row.get(1)?,
        status: row.get(2)?,
        predicted_text: row.get(3)?,
        predicted_candidates: serde_json::from_str::<Vec<String>>(&row.get::<_, String>(4)?)
            .unwrap_or_default(),
        confirmed_text: row.get(5)?,
        summary: serde_json::from_str::<SlotSummary>(&row.get::<_, String>(6)?).unwrap_or(
            SlotSummary {
                sample_count: 0,
                away_count: 0,
                excluded_count: 0,
                active_duration_seconds: 0,
                top_processes: Vec::new(),
                top_titles: Vec::new(),
                top_title_tokens: Vec::new(),
            },
        ),
        snooze_until: row.get(7)?,
        last_prompt_at: row.get(8)?,
        prompt_count: row.get(9)?,
    })
}
