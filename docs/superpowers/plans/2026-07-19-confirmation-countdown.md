# 確認画面 予告カウントダウン Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a small always-on-top countdown window in the bottom-right corner for 30 seconds before the existing 30-minute work-confirmation screen opens, so the user isn't interrupted without warning.

**Architecture:** The existing scheduler (`scheduler_tick` in `src-tauri/src/lib.rs`) already detects the exact moment a work interval becomes due. Instead of opening the full confirmation window immediately at that moment, it now opens a small borderless always-on-top "countdown" window positioned at the bottom-right of the primary monitor. That window runs its own 30-second countdown in the frontend and, when it reaches 0 (or the user clicks it), calls a new Tauri command that closes itself and opens the confirmation window exactly as before. The due-detection logic, fullscreen skip, and confirmation-window behavior are all unchanged.

**Tech Stack:** Tauri 2.11 (Rust backend) + Vite/TypeScript frontend (no framework), SQLite via `rusqlite`.

## Global Constraints

- Countdown lead time is fixed at 30 seconds (`COUNTDOWN_SECONDS`), per the approved spec — not user-configurable.
- The existing due-detection logic (`Database::due_prompt_interval`) and the fullscreen skip check (`is_fullscreen_now`) must not change.
- De-duplication of the countdown window uses Tauri's own window registry (`app.get_webview_window("countdown").is_some()`) — do not add a new state field for this.
- The countdown window is undecorated, always-on-top, skip-taskbar, non-resizable, unfocused on creation, sized 240x88 logical px, positioned at the bottom-right of the primary monitor with a 20px margin.
- This project has **no automated test framework** (no `#[cfg(test)]` modules in Rust, no JS test runner in `package.json`). Verification in this plan uses `cargo check`, `npm run check` (tsc), `npm run build`, and manual smoke testing via `npm run tauri dev` — do not introduce a new test framework as part of this change.
- Follow existing code style: 4-space indent in Rust, 2-space indent in TypeScript, no comments unless explaining a non-obvious constraint.

---

### Task 1: Countdown frontend page

**Files:**
- Create: `countdown.html`
- Create: `src/countdown.ts`

**Interfaces:**
- Produces: a page reachable at `/countdown.html?seconds=<N>` that displays a shrinking count from `N` to 0, and calls the Tauri command `open_prompt_now` (no arguments) either when the count reaches 0 or when the user clicks anywhere on the page.

- [ ] **Step 1: Create `countdown.html`**

```html
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Work Pulse Checker</title>
    <style>
      html,
      body {
        margin: 0;
        height: 100%;
        overflow: hidden;
      }

      body {
        display: flex;
        align-items: center;
        justify-content: center;
        background: #111827;
        color: #e8ecf3;
        font-family: 'Segoe UI', system-ui, sans-serif;
        cursor: pointer;
        user-select: none;
      }

      #app {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 4px;
      }

      #label {
        font-size: 13px;
        color: #a8b3c8;
      }

      #seconds {
        font-size: 30px;
        font-weight: 600;
        color: #8b5cf6;
      }
    </style>
  </head>
  <body>
    <div id="app">
      <div id="label">まもなく確認</div>
      <div id="seconds">--</div>
    </div>
    <script type="module" src="/src/countdown.ts"></script>
  </body>
</html>
```

- [ ] **Step 2: Create `src/countdown.ts`**

```ts
import { invoke } from '@tauri-apps/api/core'

const params = new URLSearchParams(window.location.search)
const initialSeconds = Number(params.get('seconds')) || 30

let secondsLeft = initialSeconds

const secondsEl = document.querySelector<HTMLDivElement>('#seconds')!

const render = () => {
  secondsEl.textContent = String(secondsLeft)
}

const openPromptNow = async () => {
  try {
    await invoke('open_prompt_now')
  } catch (error) {
    console.error('failed to open prompt', error)
  }
}

render()

const timerId = window.setInterval(() => {
  secondsLeft -= 1
  render()
  if (secondsLeft <= 0) {
    window.clearInterval(timerId)
    void openPromptNow()
  }
}, 1000)

document.body.addEventListener('click', () => {
  window.clearInterval(timerId)
  void openPromptNow()
})
```

- [ ] **Step 3: Type-check**

Run: `npm run check`
Expected: exits 0, no TypeScript errors.

- [ ] **Step 4: Manual smoke test in a plain browser tab**

Run: `npm run dev` (leave it running), then open `http://127.0.0.1:1420/countdown.html?seconds=5` in a regular browser tab.

Expected: the page shows "まもなく確認" and a number counting down 5, 4, 3, 2, 1, 0 once per second. After it hits 0, the browser devtools console shows a logged error from the `invoke` call (expected — there is no Tauri backend in a plain browser tab; this only confirms the countdown and command-call logic run correctly). Stop the dev server (Ctrl+C) after checking.

- [ ] **Step 5: Commit**

```bash
git add countdown.html src/countdown.ts
git commit -m "Add countdown page for the confirmation-prompt warning window"
```

---

### Task 2: Build config and window capability

**Files:**
- Modify: `vite.config.ts`
- Modify: `src-tauri/capabilities/default.json`

**Interfaces:**
- Consumes: `countdown.html` from Task 1.
- Produces: `dist/countdown.html` on `npm run build`; IPC permission for a window labeled `countdown` to call Tauri commands.

- [ ] **Step 1: Add a second build entry to `vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  clearScreen: false,
  server: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
  },
  preview: {
    host: '127.0.0.1',
    port: 1420,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        countdown: fileURLToPath(new URL('./countdown.html', import.meta.url)),
      },
    },
  },
})
```

- [ ] **Step 2: Add the `countdown` window to the default capability**

Edit `src-tauri/capabilities/default.json`:

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "enables the default permissions",
  "windows": [
    "main",
    "countdown"
  ],
  "permissions": [
    "core:default",
    "core:event:allow-listen",
    "core:event:allow-unlisten"
  ]
}
```

- [ ] **Step 3: Verify the production build**

Run: `npm run build`
Expected: exits 0, and `dist/countdown.html` exists alongside `dist/index.html`.

- [ ] **Step 4: Commit**

```bash
git add vite.config.ts src-tauri/capabilities/default.json
git commit -m "Build the countdown page and grant it IPC access"
```

---

### Task 3: Backend countdown window and command

**Files:**
- Modify: `src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: `countdown.html?seconds=<N>` served from the frontend build (Tasks 1-2); `AppState.db.latest_pending_interval()` and `show_prompt(app, interval)`, both already defined in this file.
- Produces: `fn show_countdown(app: &AppHandle) -> Result<()>`; Tauri command `open_prompt_now`.

- [ ] **Step 1: Add the new imports**

In `src-tauri/src/lib.rs`, change the `use tauri::{...}` block (currently lines 16-21):

```rust
use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, LogicalSize, Manager, UserAttentionType, WindowEvent,
};
```

to:

```rust
use tauri::{
    image::Image,
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, LogicalSize, Manager, UserAttentionType, WebviewUrl, WebviewWindowBuilder,
    WindowEvent,
};
```

- [ ] **Step 2: Add the new constants**

After the existing constants block (currently lines 24-28):

```rust
const SAMPLE_INTERVAL_SECONDS: i64 = 3;
const SLEEP_RESUME_GAP_SECONDS: i64 = 15;
const POST_SLEEP_AWAY_SECONDS: i64 = 15;
const HISTORY_WINDOW_WIDTH: f64 = 1300.0;
const HISTORY_WINDOW_HEIGHT: f64 = 1000.0;
```

add:

```rust
const COUNTDOWN_SECONDS: u32 = 30;
const COUNTDOWN_WINDOW_WIDTH: f64 = 240.0;
const COUNTDOWN_WINDOW_HEIGHT: f64 = 88.0;
const COUNTDOWN_WINDOW_MARGIN: f64 = 20.0;
```

- [ ] **Step 3: Replace the direct `show_prompt` call in `scheduler_tick` with `show_countdown`**

Change (currently lines 215-222):

```rust
    if let Some(interval) = database.due_prompt_interval(current_slot, now)? {
        if !is_fullscreen_now()? {
            database.mark_prompted(&interval.slot_start)?;
            if let Some(updated) = database.interval_by_slot(&interval.slot_start)? {
                show_prompt(app, &updated)?;
            }
        }
    }
```

to:

```rust
    if let Some(interval) = database.due_prompt_interval(current_slot, now)? {
        if !is_fullscreen_now()? {
            database.mark_prompted(&interval.slot_start)?;
            show_countdown(app)?;
        }
    }
```

- [ ] **Step 4: Add `show_countdown`**

Add this new function directly after `show_prompt` (which ends just before `fn show_pending_or_history`):

```rust
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
```

- [ ] **Step 5: Add the `open_prompt_now` command**

Add this after `snooze_interval` at the end of the file:

```rust
#[tauri::command]
fn open_prompt_now(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("countdown") {
        let _ = window.close();
    }

    if let Some(interval) = state
        .db
        .latest_pending_interval()
        .map_err(|error| error.to_string())?
    {
        show_prompt(&app, &interval).map_err(|error| error.to_string())?;
    }

    Ok(())
}
```

- [ ] **Step 6: Register the command**

Change the `invoke_handler` list (currently lines 94-100):

```rust
        .invoke_handler(tauri::generate_handler![
            get_snapshot,
            save_settings,
            confirm_interval,
            snooze_interval,
            get_daily_summary
        ])
```

to:

```rust
        .invoke_handler(tauri::generate_handler![
            get_snapshot,
            save_settings,
            confirm_interval,
            snooze_interval,
            get_daily_summary,
            open_prompt_now
        ])
```

- [ ] **Step 7: Compile-check**

Run: `cd src-tauri && cargo check`
Expected: exits 0, no compiler errors (warnings about unused `interval_by_slot`/`Database::interval_by_slot` are fine — that function may still be used elsewhere; if `cargo check` reports it as dead code, leave it, since removing it is out of scope for this change).

- [ ] **Step 8: Commit**

```bash
git add src-tauri/src/lib.rs
git commit -m "Show a countdown window before opening the confirmation prompt"
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the app in dev mode**

Run: `npm run tauri dev`

- [ ] **Step 2: Trigger a due interval**

The scheduler only shows the countdown once a work interval's 30-minute slot has actually ended. Two ways to get there:

  - **Easy path:** if you haven't run this app during the current or a previous 30-minute slot, `backfill_missed_intervals` (called at startup, `src-tauri/src/lib.rs:79`) will already have created a pending interval that's overdue, so the countdown should appear within about 5-10 seconds of launch.
  - **Deterministic fallback:** if nothing appears within ~30 seconds, close the app, then use the `sqlite3` CLI (or any SQLite browser) to insert an overdue pending row directly into the app's database at `%APPDATA%\com.perorin0418.work-pulse-checker\work-pulse-checker.sqlite3`:

    ```sql
    INSERT OR REPLACE INTO work_intervals
      (slot_start, slot_end, status, predicted_text, predicted_candidates, confirmed_text, summary, snooze_until, last_prompt_at, prompt_count, created_at, updated_at)
    VALUES (
      '2020-01-01T00:00:00+09:00',
      '2020-01-01T00:30:00+09:00',
      'pending',
      'test',
      '[]',
      NULL,
      '{"sampleCount":0,"awayCount":0,"excludedCount":0,"activeDurationSeconds":0,"topProcesses":[],"topTitles":[],"topTitleTokens":[]}',
      NULL,
      NULL,
      0,
      '2020-01-01T00:00:00+09:00',
      '2020-01-01T00:00:00+09:00'
    );
    ```

    Then relaunch `npm run tauri dev`.

- [ ] **Step 3: Confirm countdown behavior**

Expected, in order:
  - A small borderless window appears at the bottom-right of the primary monitor, showing "まもなく確認" and a number starting at 30.
  - The number decreases once per second.
  - The countdown window does not steal keyboard focus from whatever else you're doing.
  - When the number reaches 0, the countdown window closes and the full confirmation screen opens (same as the current behavior today).

- [ ] **Step 4: Confirm click-to-open-now behavior**

Repeat Step 2 to get a fresh due interval, then click anywhere on the countdown window while it's still counting down.

Expected: the countdown window closes immediately and the full confirmation screen opens right away, without waiting for the count to reach 0.

- [ ] **Step 5: Confirm no duplicate countdown windows**

While a countdown window is showing, wait through at least one more 5-second scheduler tick (`spawn_scheduler` in `src-tauri/src/lib.rs:186` runs every 5 seconds) without clicking it.

Expected: only one countdown window is ever visible — it is not recreated or duplicated on subsequent ticks.

- [ ] **Step 6: Clean up test data**

If you inserted the fallback test row in Step 2, delete it so it doesn't linger as a stray interval:

```sql
DELETE FROM work_intervals WHERE slot_start = '2020-01-01T00:00:00+09:00';
```
