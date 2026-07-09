use chrono::{DateTime, Local};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CountItem {
    pub name: String,
    pub count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SlotSummary {
    pub sample_count: usize,
    pub away_count: usize,
    pub excluded_count: usize,
    pub active_duration_seconds: usize,
    pub top_processes: Vec<CountItem>,
    pub top_titles: Vec<CountItem>,
    pub top_title_tokens: Vec<CountItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkInterval {
    pub slot_start: String,
    pub slot_end: String,
    pub status: String,
    pub predicted_text: String,
    pub predicted_candidates: Vec<String>,
    pub confirmed_text: Option<String>,
    pub summary: SlotSummary,
    pub snooze_until: Option<String>,
    pub last_prompt_at: Option<String>,
    pub prompt_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SampleOverview {
    pub captured_at: String,
    pub window_title: String,
    pub process_name: String,
    pub classification: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsDto {
    pub excluded_processes: Vec<String>,
    pub excluded_title_keywords: Vec<String>,
    pub autostart_enabled: bool,
    pub retention_days: i64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub intervals: Vec<WorkInterval>,
    pub pending_prompt: Option<WorkInterval>,
    pub current_sample: Option<SampleOverview>,
    pub settings: SettingsDto,
    pub current_slot_start: String,
    pub next_prompt_at: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SettingsInput {
    pub excluded_processes: Vec<String>,
    pub excluded_title_keywords: Vec<String>,
    pub autostart_enabled: bool,
}

#[derive(Debug, Clone)]
pub struct ActivitySampleRecord {
    pub captured_at: DateTime<Local>,
    pub slot_start: DateTime<Local>,
    pub window_title: String,
    pub process_name: String,
    pub classification: String,
}

#[derive(Debug, Clone)]
pub struct ActiveWindowInfo {
    pub window_title: String,
    pub process_name: String,
    pub is_fullscreen: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DailySummaryItem {
    pub label: String,
    pub minutes: i64,
    pub slot_count: usize,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DailySummarySlot {
    pub slot_start: String,
    pub slot_end: String,
    pub status: String,
    pub label: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DailySummary {
    pub date: String,
    pub total_minutes: i64,
    pub items: Vec<DailySummaryItem>,
    pub slots: Vec<DailySummarySlot>,
}
