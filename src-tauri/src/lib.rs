mod db;
mod models;
mod prediction;
mod windows_activity;

use std::{collections::HashMap, sync::Arc, thread, time::Duration as StdDuration};

use anyhow::Result;
use chrono::{DateTime, Duration, Local, NaiveDate, Timelike};
use db::{Database, RuntimeSettings};
use models::{
    ActivitySampleRecord, DailySummary, DailySummaryItem, DailySummarySlot, SettingsInput,
    Snapshot, WorkInterval,
};
use parking_lot::RwLock;
use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, UserAttentionType, WebviewUrl,
    WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const SAMPLE_INTERVAL_SECONDS: i64 = 3;
const SLEEP_RESUME_GAP_SECONDS: i64 = 15;
const POST_SLEEP_AWAY_SECONDS: i64 = 15;
const HISTORY_WINDOW_WIDTH: f64 = 1300.0;
const HISTORY_WINDOW_HEIGHT: f64 = 1000.0;
const COUNTDOWN_SECONDS: u32 = 30;
const COUNTDOWN_WINDOW_WIDTH: f64 = 240.0;
const COUNTDOWN_WINDOW_HEIGHT: f64 = 88.0;
const COUNTDOWN_WINDOW_MARGIN: f64 = 20.0;

#[derive(Clone)]
struct AppState {
    db: Database,
    runtime_settings: Arc<RwLock<RuntimeSettings>>,
    countdown_slot: Arc<RwLock<Option<String>>>,
}

#[derive(Default)]
struct SamplerRuntime {
    last_sample_at: Option<DateTime<Local>>,
    force_away_until: Option<DateTime<Local>>,
}

#[derive(serde::Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct NavigatePayload {
    view: &'static str,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None::<Vec<&str>>,
        ))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let data_dir = app
                .path()
                .app_data_dir()
                .map_err(|error| anyhow::anyhow!(error.to_string()))?;
            let database = Database::new(data_dir.join("work-pulse-checker.sqlite3"));
            database.initialize()?;

            let runtime_settings = Arc::new(RwLock::new(database.load_runtime_settings()?));
            let state = AppState {
                db: database.clone(),
                runtime_settings: runtime_settings.clone(),
                countdown_slot: Arc::new(RwLock::new(None)),
            };
            let sampler_runtime = Arc::new(RwLock::new(SamplerRuntime::default()));
            app.manage(state);

            database.backfill_missed_intervals(floor_to_slot(Local::now()))?;

            configure_autostart(app)?;
            configure_window(app)?;
            configure_tray(app)?;
            spawn_sampler(
                app.handle().clone(),
                database.clone(),
                runtime_settings.clone(),
                sampler_runtime,
            );
            spawn_scheduler(app.handle().clone(), database);

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_snapshot,
            save_settings,
            confirm_interval,
            snooze_interval,
            get_daily_summary,
            open_prompt_now
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn configure_autostart(app: &tauri::App) -> Result<()> {
    let autostart = app.autolaunch();
    if !autostart.is_enabled().unwrap_or(false) {
        let _ = autostart.enable();
    }
    Ok(())
}

fn configure_window(app: &tauri::App) -> Result<()> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| anyhow::anyhow!("main window not found"))?;
    let managed_window = window.clone();

    window.on_window_event(move |event| {
        if let WindowEvent::CloseRequested { api, .. } = event {
            api.prevent_close();
            let _ = managed_window.set_always_on_top(false);
            let _ = managed_window.hide();
        }
    });

    Ok(())
}

fn configure_tray(app: &tauri::App) -> Result<()> {
    let open_prompt = MenuItemBuilder::with_id("open-prompt", "確認を開く").build(app)?;
    let open_history = MenuItemBuilder::with_id("open-history", "履歴を開く").build(app)?;
    let quit = MenuItemBuilder::with_id("quit", "終了").build(app)?;
    let tray_icon = Image::from_bytes(include_bytes!("../icons/tray-icon.png"))?;
    let menu = MenuBuilder::new(app)
        .items(&[&open_prompt, &open_history, &quit])
        .build()?;

    TrayIconBuilder::with_id("main-tray")
        .icon(tray_icon)
        .menu(&menu)
        .tooltip("Work Pulse Checker")
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open-prompt" => {
                let _ = show_pending_or_history(app);
            }
            "open-history" => {
                let _ = show_history(app);
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let _ = show_history(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

fn spawn_sampler(
    app: AppHandle,
    database: Database,
    runtime_settings: Arc<RwLock<RuntimeSettings>>,
    sampler_runtime: Arc<RwLock<SamplerRuntime>>,
) {
    thread::spawn(move || loop {
        if let Err(error) = sample_activity(&database, &runtime_settings, &sampler_runtime) {
            log::error!("failed to capture sample: {error:#}");
        }

        let _ = app.emit("sample-tick", ());
        thread::sleep(StdDuration::from_secs(3));
    });
}

fn spawn_scheduler(app: AppHandle, database: Database) {
    thread::spawn(move || {
        let mut last_cleanup_day = None::<String>;

        loop {
            if let Err(error) = scheduler_tick(&app, &database, &mut last_cleanup_day) {
                log::error!("failed scheduler tick: {error:#}");
            }

            thread::sleep(StdDuration::from_secs(5));
        }
    });
}

fn scheduler_tick(
    app: &AppHandle,
    database: &Database,
    last_cleanup_day: &mut Option<String>,
) -> Result<()> {
    let now = Local::now();
    let current_slot = floor_to_slot(now);
    database.ensure_completed_intervals(current_slot)?;

    let today = now.date_naive().to_string();
    if last_cleanup_day.as_deref() != Some(today.as_str()) {
        database.cleanup_expired_samples()?;
        *last_cleanup_day = Some(today);
    }

    if let Some(interval) = database.due_prompt_interval(current_slot, now)? {
        if !is_fullscreen_now()? {
            database.mark_prompted(&interval.slot_start)?;
            *app.state::<AppState>().countdown_slot.write() = Some(interval.slot_start.clone());
            show_countdown(app)?;
        }
    }

    Ok(())
}

fn sample_activity(
    database: &Database,
    runtime_settings: &Arc<RwLock<RuntimeSettings>>,
    sampler_runtime: &Arc<RwLock<SamplerRuntime>>,
) -> Result<()> {
    let now = Local::now();
    let slot_start = floor_to_slot(now);
    let settings = runtime_settings.read().clone();
    let force_away = update_resume_state(sampler_runtime, now);
    let info = windows_activity::active_window()?;

    let sample = if force_away {
        ActivitySampleRecord {
            captured_at: now,
            slot_start,
            window_title: "離席 / 不明".to_string(),
            process_name: "away".to_string(),
            classification: "away".to_string(),
        }
    } else if let Some(info) = info {
        let process_name = info.process_name;
        let window_title = info.window_title;
        let process_key = process_name.to_lowercase();
        let title_key = window_title.to_lowercase();
        let is_away = matches!(process_key.as_str(), "lockapp.exe" | "logonui.exe")
            || (process_name == "unknown" && window_title.is_empty());
        let is_excluded = settings
            .excluded_processes
            .iter()
            .any(|value| value.eq_ignore_ascii_case(&process_name))
            || settings
                .excluded_title_keywords
                .iter()
                .any(|value| title_key.contains(&value.to_lowercase()));

        if is_away {
            ActivitySampleRecord {
                captured_at: now,
                slot_start,
                window_title: "離席 / 不明".to_string(),
                process_name: "away".to_string(),
                classification: "away".to_string(),
            }
        } else if is_excluded {
            ActivitySampleRecord {
                captured_at: now,
                slot_start,
                window_title: "除外".to_string(),
                process_name: "除外".to_string(),
                classification: "excluded".to_string(),
            }
        } else {
            ActivitySampleRecord {
                captured_at: now,
                slot_start,
                window_title,
                process_name,
                classification: "active".to_string(),
            }
        }
    } else {
        ActivitySampleRecord {
            captured_at: now,
            slot_start,
            window_title: "離席 / 不明".to_string(),
            process_name: "away".to_string(),
            classification: "away".to_string(),
        }
    };

    database.insert_sample(&sample)?;
    Ok(())
}

fn update_resume_state(
    sampler_runtime: &Arc<RwLock<SamplerRuntime>>,
    now: DateTime<Local>,
) -> bool {
    let mut runtime = sampler_runtime.write();

    if let Some(previous) = runtime.last_sample_at {
        let gap = now.signed_duration_since(previous).num_seconds();
        if gap > SLEEP_RESUME_GAP_SECONDS.max(SAMPLE_INTERVAL_SECONDS * 4) {
            runtime.force_away_until = Some(now + Duration::seconds(POST_SLEEP_AWAY_SECONDS));
        }
    }

    runtime.last_sample_at = Some(now);

    if let Some(until) = runtime.force_away_until {
        if now <= until {
            return true;
        }
        runtime.force_away_until = None;
    }

    false
}

fn is_fullscreen_now() -> Result<bool> {
    Ok(windows_activity::active_window()?
        .map(|info| info.is_fullscreen)
        .unwrap_or(false))
}

fn floor_to_slot(now: DateTime<Local>) -> DateTime<Local> {
    let minute = if now.minute() < 30 { 0 } else { 30 };
    now.with_second(0)
        .and_then(|value| value.with_minute(minute))
        .and_then(|value| value.with_nanosecond(0))
        .unwrap_or(now)
}

fn next_slot_start(now: DateTime<Local>) -> DateTime<Local> {
    floor_to_slot(now) + Duration::minutes(30)
}

/// 作業領域に収まるサイズへ丸め、その中央に配置するための矩形 (x, y, width, height) を返す。
fn fit_rect_to_area(area: (f64, f64, f64, f64), desired: (f64, f64)) -> (f64, f64, f64, f64) {
    let (area_x, area_y, area_width, area_height) = area;
    let (desired_width, desired_height) = desired;
    let width = desired_width.min(area_width);
    let height = desired_height.min(area_height);
    (
        area_x + (area_width - width) / 2.0,
        area_y + (area_height - height) / 2.0,
        width,
        height,
    )
}

/// メインウィンドウをディスプレイの作業領域に収まるサイズへ調整し、中央に配置する。
/// 画面より大きいままだとタイトルバーが画面外に出て操作できなくなるため。
fn resize_main_window(window: &tauri::WebviewWindow) -> Result<()> {
    let monitor = match window.current_monitor()? {
        Some(monitor) => Some(monitor),
        None => window.primary_monitor()?,
    };
    let Some(monitor) = monitor else {
        window.set_size(LogicalSize::new(HISTORY_WINDOW_WIDTH, HISTORY_WINDOW_HEIGHT))?;
        window.center()?;
        return Ok(());
    };

    let scale_factor = monitor.scale_factor();
    let work_area = monitor.work_area();
    let (x, y, width, height) = fit_rect_to_area(
        (
            work_area.position.x as f64 / scale_factor,
            work_area.position.y as f64 / scale_factor,
            work_area.size.width as f64 / scale_factor,
            work_area.size.height as f64 / scale_factor,
        ),
        (HISTORY_WINDOW_WIDTH, HISTORY_WINDOW_HEIGHT),
    );
    window.set_size(LogicalSize::new(width, height))?;
    window.set_position(LogicalPosition::new(x, y))?;
    Ok(())
}

fn show_history(app: &AppHandle) -> Result<()> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| anyhow::anyhow!("main window not found"))?;
    window.set_always_on_top(false)?;
    window.show()?;
    window.unminimize()?;
    resize_main_window(&window)?;
    window.set_focus()?;
    app.emit("navigate", NavigatePayload { view: "history" })?;
    Ok(())
}

fn show_prompt(app: &AppHandle, interval: &WorkInterval) -> Result<()> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| anyhow::anyhow!("main window not found"))?;
    window.show()?;
    window.unminimize()?;
    resize_main_window(&window)?;
    window.set_focus()?;
    let _ = window.request_user_attention(Some(UserAttentionType::Critical));
    app.emit("navigate", NavigatePayload { view: "history" })?;
    app.emit("work-prompt", interval.clone())?;
    Ok(())
}

fn show_countdown(app: &AppHandle) -> Result<()> {
    if app.get_webview_window("countdown").is_some() {
        return Ok(());
    }

    let main_window = app
        .get_webview_window("main")
        .ok_or_else(|| anyhow::anyhow!("main window not found"))?;
    let monitor = main_window
        .primary_monitor()?
        .ok_or_else(|| anyhow::anyhow!("no primary monitor found"))?;
    let scale_factor = monitor.scale_factor();
    let origin_x = monitor.position().x as f64 / scale_factor;
    let origin_y = monitor.position().y as f64 / scale_factor;
    let width = monitor.size().width as f64 / scale_factor;
    let height = monitor.size().height as f64 / scale_factor;
    let x = origin_x + width - COUNTDOWN_WINDOW_WIDTH - COUNTDOWN_WINDOW_MARGIN;
    let y = origin_y + height - COUNTDOWN_WINDOW_HEIGHT - COUNTDOWN_WINDOW_MARGIN;

    WebviewWindowBuilder::new(
        app,
        "countdown",
        WebviewUrl::App(format!("countdown.html?seconds={COUNTDOWN_SECONDS}").into()),
    )
    .title("Work Pulse Checker")
    .inner_size(COUNTDOWN_WINDOW_WIDTH, COUNTDOWN_WINDOW_HEIGHT)
    .position(x, y)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .resizable(false)
    .shadow(false)
    .focused(false)
    .build()?;

    Ok(())
}

fn show_pending_or_history(app: &AppHandle) -> Result<()> {
    let state = app.state::<AppState>();
    let now = Local::now();
    let current_slot = floor_to_slot(now);
    state.db.ensure_completed_intervals(current_slot)?;

    if let Some(interval) = state.db.latest_pending_interval()? {
        show_prompt(app, &interval)
    } else {
        show_history(app)
    }
}

#[tauri::command]
fn get_snapshot(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<Snapshot, String> {
    let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);
    let now = Local::now();
    let current_slot = floor_to_slot(now);

    state
        .db
        .ensure_completed_intervals(current_slot)
        .and_then(|_| {
            Ok(Snapshot {
                intervals: state.db.recent_intervals(48)?,
                pending_prompt: state.db.latest_pending_interval()?,
                current_sample: state.db.latest_sample()?,
                settings: state.db.load_settings(autostart_enabled)?,
                current_slot_start: current_slot.to_rfc3339(),
                next_prompt_at: next_slot_start(now).to_rfc3339(),
            })
        })
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn get_daily_summary(
    state: tauri::State<'_, AppState>,
    date: String,
) -> Result<DailySummary, String> {
    let parsed_date =
        NaiveDate::parse_from_str(&date, "%Y-%m-%d").map_err(|error| error.to_string())?;

    let intervals = state
        .db
        .intervals_for_date(parsed_date)
        .map_err(|error| error.to_string())?;

    Ok(summarize_day(&date, &intervals))
}

fn summarize_day(date: &str, intervals: &[WorkInterval]) -> DailySummary {
    let mut order = Vec::new();
    let mut totals: HashMap<String, (i64, usize)> = HashMap::new();

    for interval in intervals {
        let label = interval
            .confirmed_text
            .clone()
            .unwrap_or_else(|| interval.predicted_text.clone());
        let minutes = 30;

        let entry = totals.entry(label.clone()).or_insert_with(|| {
            order.push(label.clone());
            (0, 0)
        });
        entry.0 += minutes;
        entry.1 += 1;
    }

    let mut items: Vec<DailySummaryItem> = order
        .into_iter()
        .map(|label| {
            let (minutes, slot_count) = totals[&label];
            DailySummaryItem {
                label,
                minutes,
                slot_count,
            }
        })
        .collect();

    items.sort_by(|left, right| {
        right
            .minutes
            .cmp(&left.minutes)
            .then_with(|| left.label.cmp(&right.label))
    });

    let total_minutes = items.iter().map(|item| item.minutes).sum();

    let slots = intervals
        .iter()
        .map(|interval| DailySummarySlot {
            slot_start: interval.slot_start.clone(),
            slot_end: interval.slot_end.clone(),
            status: interval.status.clone(),
            label: interval
                .confirmed_text
                .clone()
                .unwrap_or_else(|| interval.predicted_text.clone()),
        })
        .collect();

    DailySummary {
        date: date.to_string(),
        total_minutes,
        items,
        slots,
    }
}

#[tauri::command]
fn save_settings(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    input: SettingsInput,
) -> Result<(), String> {
    let runtime = state
        .db
        .save_settings(&input)
        .map_err(|error| error.to_string())?;
    *state.runtime_settings.write() = runtime;

    let autostart = app.autolaunch();
    if input.autostart_enabled {
        autostart.enable().map_err(|error| error.to_string())?;
    } else {
        autostart.disable().map_err(|error| error.to_string())?;
    }

    Ok(())
}

#[tauri::command]
fn confirm_interval(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    slot_start: String,
    text: String,
    from_prompt: bool,
) -> Result<(), String> {
    state
        .db
        .confirm_interval(&slot_start, &text)
        .map_err(|error| error.to_string())?;

    if from_prompt {
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.set_always_on_top(false);
            let _ = window.hide();
        }
    }

    Ok(())
}

#[tauri::command]
fn snooze_interval(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    slot_start: String,
    minutes: i64,
) -> Result<(), String> {
    state
        .db
        .snooze_interval(&slot_start, minutes)
        .map_err(|error| error.to_string())?;

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_always_on_top(false);
        let _ = window.hide();
    }

    Ok(())
}

#[tauri::command]
fn open_prompt_now(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("countdown") {
        let _ = window.close();
    }

    let slot_start = state.countdown_slot.read().clone();
    let interval = match slot_start {
        Some(slot_start) => state
            .db
            .interval_by_slot(&slot_start)
            .map_err(|error| error.to_string())?,
        None => None,
    };
    let interval = match interval {
        Some(interval) => Some(interval),
        None => state
            .db
            .latest_pending_interval()
            .map_err(|error| error.to_string())?,
    };

    if let Some(interval) = interval {
        show_prompt(&app, &interval).map_err(|error| error.to_string())?;
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{fit_rect_to_area, HISTORY_WINDOW_HEIGHT, HISTORY_WINDOW_WIDTH};

    const DESIRED: (f64, f64) = (HISTORY_WINDOW_WIDTH, HISTORY_WINDOW_HEIGHT);

    #[test]
    fn keeps_size_and_centers_on_a_large_display() {
        // 2560x1440 の作業領域なら 1300x1000 はそのまま中央に入る
        let (x, y, width, height) = fit_rect_to_area((0.0, 0.0, 2560.0, 1400.0), DESIRED);
        assert_eq!((width, height), DESIRED);
        assert_eq!((x, y), (630.0, 200.0));
    }

    #[test]
    fn clamps_to_a_display_smaller_than_the_window() {
        // 1920x1080 @125% = 論理 1536x864、タスクバーを除くと 1536x816
        let (x, y, width, height) = fit_rect_to_area((0.0, 0.0, 1536.0, 816.0), DESIRED);
        assert_eq!((width, height), (1300.0, 816.0));
        assert_eq!((x, y), (118.0, 0.0));
        assert!(y >= 0.0, "タイトルバーが画面上端より外に出てはいけない");
    }

    #[test]
    fn keeps_the_window_inside_a_secondary_display() {
        // 左側に並んだサブディスプレイ (原点が負) でも作業領域内に収める
        let (x, y, width, height) = fit_rect_to_area((-1280.0, 0.0, 1280.0, 700.0), DESIRED);
        assert_eq!((width, height), (1280.0, 700.0));
        assert_eq!((x, y), (-1280.0, 0.0));
    }
}
