# アプリ常駐の自動復活と死因記録 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** アプリが落ちても最大5分で自動復活し、プロセスが生きたまま監視だけ止まる事象も自己修復し、落ちた原因がログに残る状態にする。

**Architecture:** 復活を二段構えにする。一段目は Windows タスクスケジューラで、ログオントリガと5分間隔の繰り返しを持つ時刻トリガの2本を備えた1タスクがアプリの起動を試み続ける。監視役が OS 本体なので監視役自体が死なない。二段目はプロセス内で、各ワーカースレッドのティックを `catch_unwind` で包み、ウォッチドッグがティック停止を検知してワーカーを世代番号付きで作り直す。あわせてリリースビルドでもファイルログを出し、パニックフックとマーカーファイルで死因を残す。

**Tech Stack:** Tauri 2.11 (Rust backend) + Vite/TypeScript frontend (no framework), SQLite via `rusqlite`, Windows タスクスケジューラ (`schtasks.exe`)。

## Global Constraints

- 対象は Windows のみ。`keepalive` モジュールは `schtasks.exe` と `reg.exe` を子プロセスとして呼ぶ。
- タスク名は `WorkPulseChecker-Keepalive` で固定。ユーザー設定にしない。
- キープアライブ間隔は5分（`PT5M`）で固定。ユーザー設定にしない。
- ウォッチドッグは30秒ごとに確認し、最終ティックから90秒超で停止とみなす。定数 `WATCHDOG_CHECK_SECONDS = 30`、`WATCHDOG_STALE_SECONDS = 90`。
- サンプリング間隔3秒、スケジューラ間隔5秒は現状から変更しない。
- `src-tauri/Cargo.toml` の release プロファイルに `panic = "abort"` を**設定してはいけない**。設定すると `catch_unwind` が機能せず、この計画の耐性機構が丸ごと無効になる。
- `schtasks` と `reg` の呼び出しには必ず `creation_flags(0x0800_0000)`（`CREATE_NO_WINDOW`）を付ける。付けないと起動のたびにコンソールウィンドウが一瞬光る。
- `SettingsDto` / `SettingsInput` の公開フィールド名 `autostartEnabled` は変更しない。フロントエンドとの契約を維持するため。
- 既存の `backfill_missed_intervals` / `due_prompt_interval` / `ensure_completed_intervals` のロジックは変更しない。
- コードスタイル: Rust は4スペースインデント、TypeScript は2スペース。コメントは自明でない制約を説明する場合のみ日本語で書く。
- ビルド環境: 既定ツールチェーンは `stable-x86_64-pc-windows-msvc`、MSVC ビルドツールはインストール済み。テストは素の `cargo test` で動く。`build-exe.bat` の GNU ツールチェーンは配布用 exe を作るときだけ使う。
- **`cargo test` の前に `npm ci && npm run build` を1回通しておくこと。** `tauri::generate_context!` が `tauri.conf.json` の `frontendDist`（`../dist`）の実在を要求するため、`dist/` が無いと `error: proc macro panicked ... this path doesn't exist` でテストがコンパイルできない。
- **初回の `cargo test` は Tauri と `rusqlite`（bundled SQLite の C コンパイル込み）を全部ビルドするため10分以上かかる。** タイムアウトさせないこと。2回目以降は差分ビルドで速い。
- タスク1〜5で追加したモジュールは、タスク6〜8で配線されるまで `dead_code` 警告を出す。この警告は想定内なので `#[allow(dead_code)]` を足して隠さない。

---

### Task 1: 異常終了マーカー

前回のプロセスが正常終了したかを、データディレクトリに置くマーカーファイルで判定するモジュールを作る。

**Files:**
- Create: `src-tauri/src/crash_marker.rs`
- Modify: `src-tauri/Cargo.toml`
- Modify: `src-tauri/src/lib.rs:1-4`（モジュール宣言の追加のみ）

**Interfaces:**
- Produces:
  - `pub struct CrashMarker`
  - `pub fn CrashMarker::new(data_dir: &std::path::Path) -> CrashMarker`
  - `pub fn CrashMarker::check_and_arm(&self, started_at: &str) -> anyhow::Result<bool>` — マーカーが残っていれば `true`（前回は異常終了）を返し、どちらの場合もマーカーを張り直す
  - `pub fn CrashMarker::disarm(&self) -> anyhow::Result<()>` — マーカーを消す。存在しなくても成功

- [ ] **Step 1: `tempfile` を dev-dependency に追加**

`src-tauri/Cargo.toml` の末尾（`[dependencies]` ブロックの後ろ）に新しいセクションを追加する。

```toml
[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 2: 失敗するテストを書く**

`src-tauri/src/crash_marker.rs` を新規作成し、**テストだけ**を書く。

```rust
#[cfg(test)]
mod tests {
    use super::CrashMarker;
    use tempfile::tempdir;

    #[test]
    fn reports_a_clean_start_when_no_marker_exists() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        assert!(!marker.check_and_arm("2026-08-20T09:00:00+09:00").unwrap());
    }

    #[test]
    fn reports_an_unclean_start_when_a_marker_is_left_behind() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        marker.check_and_arm("first").unwrap();

        assert!(marker.check_and_arm("second").unwrap());
    }

    #[test]
    fn disarm_makes_the_next_start_clean() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());
        marker.check_and_arm("first").unwrap();

        marker.disarm().unwrap();

        assert!(!marker.check_and_arm("second").unwrap());
    }

    #[test]
    fn disarm_succeeds_when_the_marker_is_already_gone() {
        let dir = tempdir().unwrap();
        let marker = CrashMarker::new(dir.path());

        marker.disarm().unwrap();
    }
}
```

`src-tauri/src/lib.rs` の先頭にあるモジュール宣言へ1行足す。アルファベット順を保つ。

```rust
mod crash_marker;
mod db;
mod models;
mod prediction;
mod windows_activity;
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml crash_marker`
Expected: コンパイルエラー。`cannot find type CrashMarker in this scope` 相当。

- [ ] **Step 4: 最小の実装を書く**

`src-tauri/src/crash_marker.rs` の `#[cfg(test)] mod tests` の**手前**に追記する。

```rust
use std::{
    fs,
    io::ErrorKind,
    path::{Path, PathBuf},
};

use anyhow::Result;

const MARKER_FILE_NAME: &str = "running.marker";

/// 前回のプロセスが正常終了したかを、データディレクトリ内のマーカーファイルの
/// 残留有無で判定する。正常終了時だけ消す運用にすることで、残っていれば異常終了とわかる。
pub struct CrashMarker {
    path: PathBuf,
}

impl CrashMarker {
    pub fn new(data_dir: &Path) -> Self {
        Self {
            path: data_dir.join(MARKER_FILE_NAME),
        }
    }

    /// マーカーが残っていれば true を返し、いずれの場合もマーカーを張り直す。
    pub fn check_and_arm(&self, started_at: &str) -> Result<bool> {
        let was_unclean = self.path.exists();

        if let Some(parent) = self.path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&self.path, started_at)?;

        Ok(was_unclean)
    }

    /// 正常終了時にマーカーを消す。既に無い場合も成功扱いにして冪等にする。
    pub fn disarm(&self) -> Result<()> {
        match fs::remove_file(&self.path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error.into()),
        }
    }
}
```

- [ ] **Step 5: テストが通ることを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml crash_marker`
Expected: `test result: ok. 4 passed`

- [ ] **Step 6: コミット**

```bash
git add src-tauri/src/crash_marker.rs src-tauri/src/lib.rs src-tauri/Cargo.toml src-tauri/Cargo.lock
git commit -m "異常終了を検知するマーカーファイルを追加"
```

---

### Task 2: ワーカー耐性の純粋部品

パニックを飲み込むラッパー、停止判定、世代番号付きワーカーループを作る。この時点では誰も使わない。

**Files:**
- Create: `src-tauri/src/resilience.rs`
- Modify: `src-tauri/src/lib.rs:1-5`（モジュール宣言の追加のみ）

**Interfaces:**
- Produces:
  - `pub fn guarded<F: FnOnce()>(label: &str, body: F)`
  - `pub fn is_stale(last_tick: i64, now: i64, threshold_secs: i64) -> bool`
  - `pub struct WorkerPulse { pub last_tick: AtomicI64, pub generation: AtomicU64 }`
  - `pub fn WorkerPulse::new(now: i64) -> WorkerPulse`
  - `pub fn run_worker_loop<F: FnMut()>(pulse: Arc<WorkerPulse>, my_generation: u64, label: &str, interval: Duration, now_secs: fn() -> i64, body: F)`

- [ ] **Step 1: 失敗するテストを書く**

`src-tauri/src/resilience.rs` を新規作成し、**テストだけ**を書く。

```rust
#[cfg(test)]
mod tests {
    use std::{
        sync::{
            atomic::{AtomicU64, Ordering},
            Arc,
        },
        time::Duration,
    };

    use super::{guarded, is_stale, run_worker_loop, WorkerPulse};

    #[test]
    fn guarded_swallows_a_panic_and_returns_to_the_caller() {
        let mut ran = false;

        guarded("test", || {
            ran = true;
            panic!("boom");
        });

        assert!(ran);
    }

    #[test]
    fn guarded_runs_the_body_when_it_does_not_panic() {
        let mut ran = false;

        guarded("test", || ran = true);

        assert!(ran);
    }

    #[test]
    fn is_stale_is_false_exactly_at_the_threshold() {
        assert!(!is_stale(0, 90, 90));
    }

    #[test]
    fn is_stale_is_true_past_the_threshold() {
        assert!(is_stale(0, 91, 90));
    }

    #[test]
    fn worker_loop_exits_when_its_generation_is_superseded() {
        let pulse = Arc::new(WorkerPulse::new(0));
        let calls = Arc::new(AtomicU64::new(0));
        let body_pulse = pulse.clone();
        let body_calls = calls.clone();

        run_worker_loop(
            pulse.clone(),
            0,
            "test",
            Duration::from_millis(0),
            || 42,
            move || {
                if body_calls.fetch_add(1, Ordering::SeqCst) == 2 {
                    body_pulse.generation.store(1, Ordering::SeqCst);
                }
            },
        );

        assert_eq!(calls.load(Ordering::SeqCst), 3);
        assert_eq!(pulse.last_tick.load(Ordering::SeqCst), 42);
    }

    #[test]
    fn worker_loop_does_not_run_at_all_when_already_superseded() {
        let pulse = Arc::new(WorkerPulse::new(0));
        pulse.generation.store(5, Ordering::SeqCst);
        let calls = Arc::new(AtomicU64::new(0));
        let body_calls = calls.clone();

        run_worker_loop(
            pulse,
            0,
            "test",
            Duration::from_millis(0),
            || 42,
            move || {
                body_calls.fetch_add(1, Ordering::SeqCst);
            },
        );

        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }
}
```

`src-tauri/src/lib.rs` のモジュール宣言に1行足す。

```rust
mod crash_marker;
mod db;
mod models;
mod prediction;
mod resilience;
mod windows_activity;
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml resilience`
Expected: コンパイルエラー。`unresolved imports super::guarded, super::is_stale, ...` 相当。

- [ ] **Step 3: 最小の実装を書く**

`src-tauri/src/resilience.rs` の `#[cfg(test)] mod tests` の**手前**に追記する。

```rust
use std::{
    panic::{catch_unwind, AssertUnwindSafe},
    sync::{
        atomic::{AtomicI64, AtomicU64, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};

/// ワーカー1ティック分の処理をパニックから隔離する。
/// パニックでスレッドごと死ぬと、プロセスは生きたまま監視だけ静かに止まるため。
pub fn guarded<F: FnOnce()>(label: &str, body: F) {
    if catch_unwind(AssertUnwindSafe(body)).is_err() {
        log::error!("worker tick panicked: {label}");
    }
}

/// 最後のティックからの経過が閾値を超えたか。閾値ちょうどはまだ停止とみなさない。
pub fn is_stale(last_tick: i64, now: i64, threshold_secs: i64) -> bool {
    now - last_tick > threshold_secs
}

/// ウォッチドッグとワーカーが共有する、ワーカー1本ぶんの状態。
pub struct WorkerPulse {
    pub last_tick: AtomicI64,
    pub generation: AtomicU64,
}

impl WorkerPulse {
    pub fn new(now: i64) -> Self {
        Self {
            last_tick: AtomicI64::new(now),
            generation: AtomicU64::new(0),
        }
    }
}

/// 世代番号が進むまでループし、1ティックごとに last_tick を更新する。
/// ハングした古いスレッドが後から復帰しても二重に動かないよう、
/// ループ先頭で自分の世代を確認して不一致なら抜ける。
pub fn run_worker_loop<F>(
    pulse: Arc<WorkerPulse>,
    my_generation: u64,
    label: &str,
    interval: Duration,
    now_secs: fn() -> i64,
    mut body: F,
) where
    F: FnMut(),
{
    loop {
        if pulse.generation.load(Ordering::SeqCst) != my_generation {
            return;
        }

        guarded(label, &mut body);
        pulse.last_tick.store(now_secs(), Ordering::SeqCst);
        thread::sleep(interval);
    }
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml resilience`
Expected: `test result: ok. 6 passed`

`guarded_swallows_a_panic_and_returns_to_the_caller` はテスト出力に `thread ... panicked at 'boom'` を出す。これは意図した動作なので無視してよい。

- [ ] **Step 5: コミット**

```bash
git add src-tauri/src/resilience.rs src-tauri/src/lib.rs
git commit -m "ワーカーのパニック耐性と停止判定の部品を追加"
```

---

### Task 3: タスクスケジューラ用XMLの組み立て

`schtasks /Create /XML` に渡すタスク定義XMLを組み立てる純粋関数を作る。

**Files:**
- Create: `src-tauri/src/keepalive.rs`
- Modify: `src-tauri/src/lib.rs:1-6`（モジュール宣言の追加のみ）

**Interfaces:**
- Produces:
  - `pub const TASK_NAME: &str = "WorkPulseChecker-Keepalive"`
  - `pub fn build_task_xml(exe_path: &str, user_id: &str) -> String`
  - `pub fn format_user_id(domain: Option<&str>, user: &str) -> String`

- [ ] **Step 1: 失敗するテストを書く**

`src-tauri/src/keepalive.rs` を新規作成し、**テストだけ**を書く。

```rust
#[cfg(test)]
mod tests {
    use super::{build_task_xml, format_user_id};

    const EXE: &str = r"C:\Apps\work-pulse-checker.exe";
    const USER: &str = r"CONTOSO\taro";

    #[test]
    fn embeds_the_executable_path_and_the_user() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains(r"<Command>C:\Apps\work-pulse-checker.exe</Command>"));
        assert!(xml.contains(r"<UserId>CONTOSO\taro</UserId>"));
    }

    #[test]
    fn repeats_every_five_minutes_without_a_duration() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<Interval>PT5M</Interval>"));
        assert!(!xml.contains("<Duration>"));
    }

    /// LogonTrigger の Repetition はそのトリガーが発火するまで回り始めないため、
    /// 登録直後から効く繰り返しは過去起点の TimeTrigger 側に持たせる必要がある。
    #[test]
    fn carries_the_repetition_on_a_time_trigger_starting_in_the_past() {
        let xml = build_task_xml(EXE, USER);

        let (before_time_trigger, from_time_trigger) = xml.split_once("<TimeTrigger>").unwrap();
        assert!(before_time_trigger.contains("<LogonTrigger>"));
        assert!(!before_time_trigger.contains("<Repetition>"));
        assert!(from_time_trigger.contains("<StartBoundary>2020-01-01T00:00:00</StartBoundary>"));
        assert!(from_time_trigger.contains("<Interval>PT5M</Interval>"));
    }

    #[test]
    fn never_expires_and_ignores_duplicate_launches() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>"));
        assert!(xml.contains("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"));
    }

    #[test]
    fn runs_without_elevation_using_an_interactive_token() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<LogonType>InteractiveToken</LogonType>"));
        assert!(xml.contains("<RunLevel>LeastPrivilege</RunLevel>"));
    }

    #[test]
    fn keeps_running_on_battery() {
        let xml = build_task_xml(EXE, USER);

        assert!(xml.contains("<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"));
        assert!(xml.contains("<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"));
    }

    #[test]
    fn escapes_xml_special_characters() {
        let xml = build_task_xml(r"C:\a & b\<x>.exe", r"CON&TOSO\taro");

        assert!(xml.contains(r"<Command>C:\a &amp; b\&lt;x&gt;.exe</Command>"));
        assert!(xml.contains(r"<UserId>CON&amp;TOSO\taro</UserId>"));
        assert!(!xml.contains("& b"));
    }

    #[test]
    fn qualifies_the_user_with_its_domain_when_present() {
        assert_eq!(format_user_id(Some("CONTOSO"), "taro"), r"CONTOSO\taro");
    }

    #[test]
    fn falls_back_to_the_bare_user_name() {
        assert_eq!(format_user_id(None, "taro"), "taro");
        assert_eq!(format_user_id(Some(""), "taro"), "taro");
    }
}
```

`src-tauri/src/lib.rs` のモジュール宣言に1行足す。

```rust
mod crash_marker;
mod db;
mod keepalive;
mod models;
mod prediction;
mod resilience;
mod windows_activity;
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml keepalive`
Expected: コンパイルエラー。`unresolved imports super::build_task_xml, super::format_user_id` 相当。

- [ ] **Step 3: 最小の実装を書く**

`src-tauri/src/keepalive.rs` の `#[cfg(test)] mod tests` の**手前**に追記する。`<Settings>` 内の要素順はタスクスケジューラのスキーマで決まっているため、並べ替えないこと。

```rust
pub const TASK_NAME: &str = "WorkPulseChecker-Keepalive";

/// TimeTrigger の起点。過去の固定日時にしておくことで、登録した瞬間から
/// 5分間隔の繰り返しが有効になる。日時そのものに意味は無い。
const KEEPALIVE_START_BOUNDARY: &str = "2020-01-01T00:00:00";

fn escape_xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// 環境変数から得たドメインとユーザー名を `DOMAIN\user` 形式にまとめる。
/// ドメインが無いローカルアカウントではユーザー名だけを使う。
pub fn format_user_id(domain: Option<&str>, user: &str) -> String {
    match domain {
        Some(domain) if !domain.is_empty() => format!("{domain}\\{user}"),
        _ => user.to_string(),
    }
}

/// `schtasks /Create /XML` に渡すタスク定義。
///
/// トリガーを2本持つ。LogonTrigger はログオン直後に起動するためのもの。
/// 5分ごとの生存確認は TimeTrigger 側に持たせる。Repetition は
/// 「そのトリガーが発火した時点」から回り始めるので、LogonTrigger だけだと
/// 既にログオン済みの状態でタスクを作った直後は次回ログオンまで一度も走らない。
/// 過去の StartBoundary を与えた TimeTrigger なら登録直後から回り続ける。
pub fn build_task_xml(exe_path: &str, user_id: &str) -> String {
    let exe_path = escape_xml(exe_path);
    let user_id = escape_xml(user_id);

    format!(
        r#"<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Work Pulse Checker keepalive</Description>
    <URI>\{TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user_id}</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <Enabled>true</Enabled>
      <StartBoundary>{KEEPALIVE_START_BOUNDARY}</StartBoundary>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user_id}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{exe_path}</Command>
    </Exec>
  </Actions>
</Task>
"#
    )
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml keepalive`
Expected: `test result: ok. 9 passed`

- [ ] **Step 5: コミット**

```bash
git add src-tauri/src/keepalive.rs src-tauri/src/lib.rs
git commit -m "キープアライブタスクのXML組み立てを追加"
```

---

### Task 4: タスクの登録・解除と旧レジストリの掃除

`schtasks` / `reg` を実際に叩く部分を実装する。

**Files:**
- Modify: `src-tauri/src/keepalive.rs`

**Interfaces:**
- Consumes: `TASK_NAME`, `build_task_xml`, `format_user_id`（Task 3）
- Produces:
  - `pub fn reconcile(desired_enabled: bool) -> anyhow::Result<()>` — `true` なら `/F` で上書き登録、`false` なら削除
  - `pub fn remove_legacy_run_key()` — 旧レジストリ Run キーの値を削除。失敗は無視

- [ ] **Step 1: UTF-16LE 書き出しの失敗するテストを書く**

`src-tauri/src/keepalive.rs` の `mod tests` の中、既存テストの後ろに追記する。

```rust
    #[test]
    fn writes_utf16le_with_a_byte_order_mark() {
        use super::write_utf16le_with_bom;
        use tempfile::tempdir;

        let dir = tempdir().unwrap();
        let path = dir.path().join("task.xml");

        write_utf16le_with_bom(&path, "A<").unwrap();

        assert_eq!(
            std::fs::read(&path).unwrap(),
            vec![0xFF, 0xFE, b'A', 0x00, b'<', 0x00]
        );
    }
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml keepalive::tests::writes_utf16le`
Expected: コンパイルエラー。`cannot find function write_utf16le_with_bom in module super` 相当。

- [ ] **Step 3: 実装を書く**

`src-tauri/src/keepalive.rs` の先頭（`pub const TASK_NAME` の手前）に `use` を追加する。

```rust
use std::{
    env, fs,
    os::windows::process::CommandExt,
    path::{Path, PathBuf},
    process::Command,
};

use anyhow::{anyhow, Context, Result};
```

`build_task_xml` の**後ろ**に以下を追記する。

```rust
/// コンソールウィンドウを出さずに子プロセスを起動するためのフラグ。
/// 付けないと起動のたびに黒い窓が一瞬光る。
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const LEGACY_RUN_KEY: &str = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run";
const LEGACY_RUN_VALUE: &str = "Work Pulse Checker";

fn quiet_command(program: &str) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

fn current_user_id() -> Result<String> {
    let user = env::var("USERNAME").context("USERNAME is not set")?;
    let domain = env::var("USERDOMAIN").ok();
    Ok(format_user_id(domain.as_deref(), &user))
}

fn temp_xml_path() -> PathBuf {
    env::temp_dir().join(format!("{TASK_NAME}-{}.xml", std::process::id()))
}

/// schtasks /XML は UTF-8 のファイルを読めない環境があるため UTF-16LE + BOM で書く。
fn write_utf16le_with_bom(path: &Path, content: &str) -> Result<()> {
    let mut bytes = vec![0xFF, 0xFE];
    for unit in content.encode_utf16() {
        bytes.extend_from_slice(&unit.to_le_bytes());
    }
    fs::write(path, bytes)?;
    Ok(())
}

/// タスクを望ましい状態に一致させる。
pub fn reconcile(desired_enabled: bool) -> Result<()> {
    if desired_enabled {
        register()
    } else {
        unregister()
    }
}

/// 毎回 /F で上書き登録する。こうすることで exe パスが常に現在のパスへ追従し、
/// 旧レジストリ方式で起きていた「古いパスが固着して起動しない」状態を構造的に防ぐ。
fn register() -> Result<()> {
    let exe_path = env::current_exe().context("failed to resolve the current executable")?;
    let xml = build_task_xml(&exe_path.to_string_lossy(), &current_user_id()?);
    let xml_path = temp_xml_path();
    write_utf16le_with_bom(&xml_path, &xml)?;

    let status = quiet_command("schtasks")
        .args(["/Create", "/TN", TASK_NAME, "/XML"])
        .arg(&xml_path)
        .arg("/F")
        .status()
        .context("failed to run schtasks /Create");
    let _ = fs::remove_file(&xml_path);

    let status = status?;
    if !status.success() {
        return Err(anyhow!("schtasks /Create exited with {status}"));
    }

    Ok(())
}

/// 未登録なら schtasks は非ゼロで終わるが、登録されていない状態が望みなので成功扱いにする。
fn unregister() -> Result<()> {
    let _ = quiet_command("schtasks")
        .args(["/Delete", "/TN", TASK_NAME, "/F"])
        .status();
    Ok(())
}

/// tauri-plugin-autostart が残した旧レジストリ値を消す。
/// 値が無いときも reg は非ゼロで終わるため、結果を捨てることで冪等にする。
pub fn remove_legacy_run_key() {
    let _ = quiet_command("reg")
        .args(["delete", LEGACY_RUN_KEY, "/v", LEGACY_RUN_VALUE, "/f"])
        .status();
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml keepalive`
Expected: `test result: ok. 10 passed`

- [ ] **Step 5: 実機でタスク登録が通ることを確認**

`reconcile` はまだアプリから呼ばれていないので、XMLだけ手で検証する。次のスクラッチテストを一時的に `mod tests` へ追加する。

```rust
    #[test]
    #[ignore]
    fn manually_registers_and_deletes_the_task() {
        super::reconcile(true).unwrap();
        super::reconcile(false).unwrap();
    }
```

Run: `cargo test --manifest-path src-tauri/Cargo.toml keepalive::tests::manually_registers -- --ignored --nocapture`
Expected: PASS。失敗する場合、`schtasks /Create exited with exit code: 1` のように出る。

**XMLが拒否された場合のトラブルシュート:** タスクスケジューラは `<Settings>` 内の要素順をスキーマで固定しており、順序違反は「タスク XML に、書式が正しくない値、または範囲外の値が含まれています」で弾かれる。その場合は GUI で適当なタスクを1つ作り、`schtasks /Query /TN "<そのタスク名>" /XML` の出力と要素順を突き合わせて `build_task_xml` を直す。

確認できたら `#[ignore]` 付きのこのテストは**削除する**（実機の状態を変えるテストを残さない）。

- [ ] **Step 6: コミット**

```bash
git add src-tauri/src/keepalive.rs
git commit -m "キープアライブタスクの登録・解除と旧Runキー削除を追加"
```

---

### Task 5: キープアライブ有効フラグの永続化

「キープアライブを有効にするか」の望ましい状態を DB に持つ。OS 側を真実にすると、毎回 `/F` で上書き登録する仕様と衝突してユーザーが無効化しても次回起動で復活してしまうため。

**Files:**
- Modify: `src-tauri/src/db.rs:37`（`initialize`）
- Modify: `src-tauri/src/db.rs:101`（`load_settings`）
- Modify: `src-tauri/src/db.rs:111`（`save_settings`）

**Interfaces:**
- Produces:
  - `pub fn Database::load_keepalive_enabled(&self) -> anyhow::Result<bool>` — 行が無ければ `true`
  - `Database::load_settings(&self) -> Result<SettingsDto>` — 引数 `autostart_enabled: bool` を**廃止**し、DB から読むよう変更
  - `Database::save_settings` は `SettingsInput::autostart_enabled` を `app_settings` へ保存するようになる（シグネチャは不変）

- [ ] **Step 1: 失敗するテストを書く**

`src-tauri/src/db.rs` の**末尾**に追記する。

```rust
#[cfg(test)]
mod tests {
    use tempfile::TempDir;

    use super::Database;
    use crate::models::SettingsInput;

    fn database() -> (TempDir, Database) {
        let dir = tempfile::tempdir().unwrap();
        let database = Database::new(dir.path().join("test.sqlite3"));
        database.initialize().unwrap();
        (dir, database)
    }

    fn settings_input(autostart_enabled: bool) -> SettingsInput {
        SettingsInput {
            excluded_processes: Vec::new(),
            excluded_title_keywords: Vec::new(),
            autostart_enabled,
        }
    }

    #[test]
    fn keepalive_defaults_to_enabled_on_a_fresh_database() {
        let (_dir, database) = database();

        assert!(database.load_keepalive_enabled().unwrap());
    }

    #[test]
    fn keepalive_remembers_that_it_was_turned_off() {
        let (_dir, database) = database();

        database.save_settings(&settings_input(false)).unwrap();

        assert!(!database.load_keepalive_enabled().unwrap());
    }

    #[test]
    fn keepalive_can_be_turned_back_on() {
        let (_dir, database) = database();
        database.save_settings(&settings_input(false)).unwrap();

        database.save_settings(&settings_input(true)).unwrap();

        assert!(database.load_keepalive_enabled().unwrap());
    }

    #[test]
    fn load_settings_reports_the_persisted_keepalive_state() {
        let (_dir, database) = database();
        database.save_settings(&settings_input(false)).unwrap();

        assert!(!database.load_settings().unwrap().autostart_enabled);
    }
}
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml db::tests`
Expected: コンパイルエラー。`no method named load_keepalive_enabled` および `load_settings takes 2 arguments but 1 was supplied` 相当。

- [ ] **Step 3: テーブルを追加する**

`src-tauri/src/db.rs` の `initialize` 内 `execute_batch` の SQL、`CREATE TABLE IF NOT EXISTS excluded_title_keywords (...)` の**後ろ**に追記する。

```sql
            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
```

- [ ] **Step 4: 読み書きを実装する**

`src-tauri/src/db.rs` の `pub const SAMPLE_RETENTION_DAYS: i64 = 90;` の直後にキー名の定数を足す。

```rust
const KEEPALIVE_ENABLED_KEY: &str = "keepalive_enabled";
```

`load_settings` を丸ごと差し替える。

```rust
    pub fn load_settings(&self) -> Result<SettingsDto> {
        let runtime = self.load_runtime_settings()?;
        Ok(SettingsDto {
            excluded_processes: runtime.excluded_processes,
            excluded_title_keywords: runtime.excluded_title_keywords,
            autostart_enabled: self.load_keepalive_enabled()?,
            retention_days: SAMPLE_RETENTION_DAYS,
        })
    }

    /// キープアライブタスクを登録すべきかどうか。行が無い既存DBでは有効とみなす。
    pub fn load_keepalive_enabled(&self) -> Result<bool> {
        let connection = self.connection()?;
        let value: Option<String> = connection
            .query_row(
                "SELECT value FROM app_settings WHERE key = ?",
                params![KEEPALIVE_ENABLED_KEY],
                |row| row.get(0),
            )
            .optional()?;

        Ok(value.map(|value| value == "true").unwrap_or(true))
    }
```

`save_settings` の `transaction.commit()?;` の**手前**に追記する。

```rust
        transaction.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            params![
                KEEPALIVE_ENABLED_KEY,
                if input.autostart_enabled { "true" } else { "false" }
            ],
        )?;
```

- [ ] **Step 5: 呼び出し側を暫定で直す**

`src-tauri/src/lib.rs:572` 付近の `get_snapshot` 内、`settings: state.db.load_settings(autostart_enabled)?,` を引数なしに変える。同じ関数の先頭にある `let autostart_enabled = app.autolaunch().is_enabled().unwrap_or(false);` はまだ残っているので、未使用変数の警告を避けるためこの行も削除する。`app: AppHandle` 引数がこれで未使用になるため、`get_snapshot` のシグネチャから `app: AppHandle,` を削除する。Tauri のコマンドは宣言された引数だけを自動注入するため、`invoke_handler` の登録もフロントエンドの `invoke` 呼び出しも変更不要。

変更後の `get_snapshot` は次のとおり。

```rust
#[tauri::command]
fn get_snapshot(state: tauri::State<'_, AppState>) -> Result<Snapshot, String> {
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
                settings: state.db.load_settings()?,
                current_slot_start: current_slot.to_rfc3339(),
                next_prompt_at: next_slot_start(now).to_rfc3339(),
            })
        })
        .map_err(|error| error.to_string())
}
```

- [ ] **Step 6: テストが通ることを確認**

Run: `cargo test --manifest-path src-tauri/Cargo.toml db::tests`
Expected: `test result: ok. 4 passed`

Run: `cargo test --manifest-path src-tauri/Cargo.toml`
Expected: 全テスト PASS（Task 1〜5 で追加した 24 件 + 既存の `fit_rect_to_area` 3 件 = 27 件）

- [ ] **Step 7: コミット**

```bash
git add src-tauri/src/db.rs src-tauri/src/lib.rs
git commit -m "キープアライブ有効フラグをDBに永続化"
```

---

### Task 6: リリースログ・パニックフック・異常終了検知の配線

死因が残る状態にする。

**Files:**
- Modify: `src-tauri/src/lib.rs`（`run`、`AppState`、`setup`、トレイの `quit` ハンドラ）

**Interfaces:**
- Consumes: `crash_marker::CrashMarker`（Task 1）
- Produces: `AppState` に `crash_marker: Arc<CrashMarker>` フィールドが増える

- [ ] **Step 1: `use` とパニックフックを追加**

`src-tauri/src/lib.rs` の `use` ブロックへ追加する。

```rust
use crash_marker::CrashMarker;
```

`pub fn run()` の**手前**に関数を追加する。

```rust
/// パニックの内容と発生位置、バックトレースをログへ流す。
/// これが無いとリリースビルドではクラッシュの痕跡がどこにも残らない。
fn install_panic_hook() {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let backtrace = std::backtrace::Backtrace::force_capture();
        log::error!("panic: {info}\nbacktrace:\n{backtrace}");
        default_hook(info);
    }));
}
```

- [ ] **Step 2: `run` の先頭でフックを仕込む**

`pub fn run()` の本体1行目、`tauri::Builder::default()` の**手前**に入れる。

```rust
pub fn run() {
    install_panic_hook();

    tauri::Builder::default()
```

- [ ] **Step 3: ログをリリースでも有効にする**

`setup` 内の次のブロックを

```rust
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
```

これに差し替える。

```rust
            let mut log_builder = tauri_plugin_log::Builder::default()
                .clear_targets()
                .level(log::LevelFilter::Info)
                .max_file_size(2 * 1024 * 1024)
                .rotation_strategy(tauri_plugin_log::RotationStrategy::KeepOne)
                .target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::LogDir {
                        file_name: Some("work-pulse-checker".into()),
                    },
                ));
            if cfg!(debug_assertions) {
                log_builder = log_builder.target(tauri_plugin_log::Target::new(
                    tauri_plugin_log::TargetKind::Stdout,
                ));
            }
            app.handle().plugin(log_builder.build())?;
```

- [ ] **Step 4: `AppState` にマーカーを持たせ、起動時に判定する**

`AppState` の定義にフィールドを足す。

```rust
#[derive(Clone)]
struct AppState {
    db: Database,
    runtime_settings: Arc<RwLock<RuntimeSettings>>,
    countdown_slot: Arc<RwLock<Option<String>>>,
    crash_marker: Arc<CrashMarker>,
}
```

`setup` 内、`let runtime_settings = ...` の**手前**に判定を入れる。

```rust
            let crash_marker = Arc::new(CrashMarker::new(&data_dir));
            match crash_marker.check_and_arm(&Local::now().to_rfc3339()) {
                Ok(true) => log::warn!("前回のプロセスは正常終了していない"),
                Ok(false) => {}
                Err(error) => log::error!("failed to update the running marker: {error:#}"),
            }
```

`AppState` の初期化にフィールドを足す。

```rust
            let state = AppState {
                db: database.clone(),
                runtime_settings: runtime_settings.clone(),
                countdown_slot: Arc::new(RwLock::new(None)),
                crash_marker,
            };
```

- [ ] **Step 5: 正常終了時にマーカーを消す**

`configure_tray` の `on_menu_event` にある `"quit"` の分岐を差し替える。

```rust
            "quit" => {
                if let Err(error) = app.state::<AppState>().crash_marker.disarm() {
                    log::error!("failed to clear the running marker: {error:#}");
                }
                app.exit(0);
            }
```

- [ ] **Step 6: ビルドとテストを通す**

Run: `cargo check --manifest-path src-tauri/Cargo.toml`
Expected: エラー無し。

`clear_targets` / `max_file_size` / `rotation_strategy` / `RotationStrategy` / `Target` / `TargetKind` のいずれかが解決できないというエラーが出た場合は、依存の実物を見て名前を合わせる。

```bash
cargo doc --manifest-path src-tauri/Cargo.toml -p tauri-plugin-log --no-deps
```

Run: `cargo test --manifest-path src-tauri/Cargo.toml`
Expected: 全テスト PASS。

- [ ] **Step 7: 実機で確認**

Run: `npm run tauri dev`

起動後、トレイメニューの「終了」でアプリを閉じる。次に、もう一度 `npm run tauri dev` で起動し、コンソールに `前回のプロセスは正常終了していない` が**出ないこと**を確認する。

続いて起動中のプロセスをタスクマネージャーから強制終了し、再度起動して同じ警告が**出ること**を確認する。

- [ ] **Step 8: コミット**

```bash
git add src-tauri/src/lib.rs
git commit -m "リリースビルドのログとパニック記録、異常終了検知を配線"
```

---

### Task 7: ワーカーのウォッチドッグ配線

サンプラーとスケジューラを世代番号付きのループに載せ替え、停止を検知して作り直すウォッチドッグを追加する。

**Files:**
- Modify: `src-tauri/src/lib.rs`（定数、`spawn_sampler`、`spawn_scheduler`、`setup`）

**Interfaces:**
- Consumes: `resilience::{is_stale, run_worker_loop, WorkerPulse}`（Task 2）
- Produces: `spawn_workers(sampler: SamplerDeps, scheduler: SchedulerDeps)` — サンプラー・スケジューラ・ウォッチドッグの3スレッドを起動する

- [ ] **Step 1: `use` と定数を追加**

`src-tauri/src/lib.rs` の `use` ブロックへ追加する。既存の `use std::{...}` は次のとおり広げる。

```rust
use std::{
    collections::HashMap,
    sync::{atomic::Ordering, Arc},
    thread,
    time::Duration as StdDuration,
};
```

`resilience` の取り込みを追加する。

```rust
use resilience::{is_stale, run_worker_loop, WorkerPulse};
```

`const COUNTDOWN_WINDOW_MARGIN: f64 = 20.0;` の後ろに定数を足す。

```rust
const SCHEDULER_TICK_SECONDS: u64 = 5;
const SAMPLER_TICK_SECONDS: u64 = 3;
const WATCHDOG_CHECK_SECONDS: u64 = 30;
const WATCHDOG_STALE_SECONDS: i64 = 90;
```

- [ ] **Step 2: ワーカーの依存をまとめる型を追加**

ウォッチドッグがワーカーを作り直せるよう、必要な依存を複製可能な構造体にまとめる。`struct SamplerRuntime` の定義の後ろに追記する。

```rust
#[derive(Clone)]
struct SamplerDeps {
    app: AppHandle,
    database: Database,
    runtime_settings: Arc<RwLock<RuntimeSettings>>,
    sampler_runtime: Arc<RwLock<SamplerRuntime>>,
}

#[derive(Clone)]
struct SchedulerDeps {
    app: AppHandle,
    database: Database,
}

fn now_secs() -> i64 {
    Local::now().timestamp()
}
```

- [ ] **Step 3: `spawn_sampler` と `spawn_scheduler` を差し替える**

既存の `fn spawn_sampler(...)` と `fn spawn_scheduler(...)` を丸ごと消し、代わりに次を置く。

```rust
fn start_sampler(deps: SamplerDeps, pulse: Arc<WorkerPulse>, generation: u64) {
    thread::spawn(move || {
        run_worker_loop(
            pulse,
            generation,
            "sampler",
            StdDuration::from_secs(SAMPLER_TICK_SECONDS),
            now_secs,
            move || {
                if let Err(error) = sample_activity(
                    &deps.database,
                    &deps.runtime_settings,
                    &deps.sampler_runtime,
                ) {
                    log::error!("failed to capture sample: {error:#}");
                }
                let _ = deps.app.emit("sample-tick", ());
            },
        );
        log::warn!("sampler worker generation {generation} exited");
    });
}

fn start_scheduler(deps: SchedulerDeps, pulse: Arc<WorkerPulse>, generation: u64) {
    thread::spawn(move || {
        let mut last_cleanup_day = None::<String>;

        run_worker_loop(
            pulse,
            generation,
            "scheduler",
            StdDuration::from_secs(SCHEDULER_TICK_SECONDS),
            now_secs,
            move || {
                if let Err(error) =
                    scheduler_tick(&deps.app, &deps.database, &mut last_cleanup_day)
                {
                    log::error!("failed scheduler tick: {error:#}");
                }
            },
        );
        log::warn!("scheduler worker generation {generation} exited");
    });
}

/// ワーカー3本（サンプラー・スケジューラ・ウォッチドッグ）を起動する。
fn spawn_workers(sampler: SamplerDeps, scheduler: SchedulerDeps) {
    let now = now_secs();
    let sampler_pulse = Arc::new(WorkerPulse::new(now));
    let scheduler_pulse = Arc::new(WorkerPulse::new(now));

    start_sampler(sampler.clone(), sampler_pulse.clone(), 0);
    start_scheduler(scheduler.clone(), scheduler_pulse.clone(), 0);

    thread::spawn(move || loop {
        thread::sleep(StdDuration::from_secs(WATCHDOG_CHECK_SECONDS));
        let now = now_secs();

        if is_stale(
            sampler_pulse.last_tick.load(Ordering::SeqCst),
            now,
            WATCHDOG_STALE_SECONDS,
        ) {
            let generation = sampler_pulse.generation.fetch_add(1, Ordering::SeqCst) + 1;
            log::error!("sampler stalled; restarting as generation {generation}");
            sampler_pulse.last_tick.store(now, Ordering::SeqCst);
            start_sampler(sampler.clone(), sampler_pulse.clone(), generation);
        }

        if is_stale(
            scheduler_pulse.last_tick.load(Ordering::SeqCst),
            now,
            WATCHDOG_STALE_SECONDS,
        ) {
            let generation = scheduler_pulse.generation.fetch_add(1, Ordering::SeqCst) + 1;
            log::error!("scheduler stalled; restarting as generation {generation}");
            scheduler_pulse.last_tick.store(now, Ordering::SeqCst);
            start_scheduler(scheduler.clone(), scheduler_pulse.clone(), generation);
        }
    });
}
```

- [ ] **Step 4: `setup` の呼び出しを差し替える**

`setup` 内の次の2つの呼び出しを

```rust
            spawn_sampler(
                app.handle().clone(),
                database.clone(),
                runtime_settings.clone(),
                sampler_runtime,
            );
            spawn_scheduler(app.handle().clone(), database);
```

これに差し替える。

```rust
            spawn_workers(
                SamplerDeps {
                    app: app.handle().clone(),
                    database: database.clone(),
                    runtime_settings: runtime_settings.clone(),
                    sampler_runtime,
                },
                SchedulerDeps {
                    app: app.handle().clone(),
                    database,
                },
            );
```

- [ ] **Step 5: ビルドとテストを通す**

Run: `cargo check --manifest-path src-tauri/Cargo.toml`
Expected: エラー無し。

Run: `cargo test --manifest-path src-tauri/Cargo.toml`
Expected: 全テスト PASS。

- [ ] **Step 6: 実機で確認**

Run: `npm run tauri dev`

トレイアイコンから履歴を開き、「現在の記録」が3秒ごとに更新され続けることを確認する。2分ほど放置して、コンソールに `sampler stalled` / `scheduler stalled` が**出ないこと**を確認する（誤検知していない）。

- [ ] **Step 7: コミット**

```bash
git add src-tauri/src/lib.rs
git commit -m "ワーカーの停止を検知して作り直すウォッチドッグを追加"
```

---

### Task 8: 自動起動をタスクスケジューラへ差し替え

`tauri-plugin-autostart` を撤去し、キープアライブタスクに置き換える。多重起動も塞ぐ。

**Files:**
- Modify: `src-tauri/Cargo.toml`
- Modify: `src-tauri/src/lib.rs`（`use`、プラグイン登録、`configure_autostart`、`save_settings`）
- Modify: `src/main.ts:392-393`

**Interfaces:**
- Consumes: `keepalive::{reconcile, remove_legacy_run_key}`（Task 4）、`Database::load_keepalive_enabled`（Task 5）
- Produces: `configure_keepalive(app: &tauri::App) -> anyhow::Result<()>`

- [ ] **Step 1: 依存を入れ替える**

`src-tauri/Cargo.toml` の `[dependencies]` から次の行を**削除**する。

```toml
tauri-plugin-autostart = "2"
```

同じブロックに次の行を**追加**する（`tauri-plugin-log` の手前、アルファベット順）。

```toml
tauri-plugin-single-instance = "2"
```

- [ ] **Step 2: `use` を差し替える**

`src-tauri/src/lib.rs` から次の行を削除する。

```rust
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
```

- [ ] **Step 3: プラグイン登録を差し替える**

`pub fn run()` 内の次のブロックを

```rust
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None::<Vec<&str>>,
        ))
```

これに差し替える。single-instance プラグインは他のプラグインより先に登録する必要がある。二番目のインスタンスでは意図的に何もしない（5分ごとにウィンドウが勝手に開いては困るため）。

```rust
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_app, _argv, _cwd| {}))
```

- [ ] **Step 4: `configure_autostart` を差し替える**

既存の関数を丸ごと消して次を置く。

```rust
/// キープアライブタスクを DB の設定に合わせる。
/// 有効時は毎回 /F で上書き登録するので、exe を別フォルダへ置き直しても追従する。
fn configure_keepalive(app: &tauri::App) -> Result<()> {
    keepalive::remove_legacy_run_key();

    let enabled = app.state::<AppState>().db.load_keepalive_enabled()?;
    if let Err(error) = keepalive::reconcile(enabled) {
        log::error!("failed to reconcile the keepalive task: {error:#}");
    }

    Ok(())
}
```

`setup` 内の `configure_autostart(app)?;` を `configure_keepalive(app)?;` に変える。`app.manage(state);` より後ろで呼ばれている必要があるため、`configure_window(app)?;` の手前という現在の位置のままでよい（`app.manage(state)` はその前にある）。

- [ ] **Step 5: `save_settings` コマンドを差し替える**

`#[tauri::command] fn save_settings(...)` を丸ごと差し替える。`app: AppHandle` 引数は不要になるので削除する。

```rust
#[tauri::command]
fn save_settings(state: tauri::State<'_, AppState>, input: SettingsInput) -> Result<(), String> {
    let runtime = state
        .db
        .save_settings(&input)
        .map_err(|error| error.to_string())?;
    *state.runtime_settings.write() = runtime;

    keepalive::reconcile(input.autostart_enabled).map_err(|error| error.to_string())
}
```

- [ ] **Step 6: UIの文言を実態に合わせる**

`src/main.ts:393` の1行を差し替える。

変更前:

```html
          <span>Windows ログイン時に自動起動する</span>
```

変更後:

```html
          <span>自動起動と、落ちたときの自動復活を有効にする</span>
```

同じ `<article>` の見出し（`src/main.ts:389`）も合わせる。

変更前:

```html
          <h2>収集と自動起動</h2>
```

変更後:

```html
          <h2>収集と常駐</h2>
```

- [ ] **Step 7: ビルドとテストを通す**

Run: `cargo check --manifest-path src-tauri/Cargo.toml`
Expected: エラー無し。`tauri_plugin_autostart` への参照が残っているとここで落ちる。

Run: `npm run check`
Expected: エラー無し。

Run: `cargo test --manifest-path src-tauri/Cargo.toml`
Expected: 全テスト PASS。

- [ ] **Step 8: 実機で受け入れ確認**

Run: `npm run build && cargo build --release --manifest-path src-tauri/Cargo.toml`

ビルドした `src-tauri/target/release/work-pulse-checker.exe` を起動して、順に確認する。

1. 旧レジストリ値が消えていること

```bash
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Work Pulse Checker"
```

Expected: `ERROR: The system was unable to find the specified registry key or value.`

2. タスクが登録され、exe パスが今起動しているものになっていること

```bash
schtasks /Query /TN WorkPulseChecker-Keepalive /XML
```

Expected: `<Command>` に `src-tauri\target\release\work-pulse-checker.exe` のフルパス、`<Interval>PT5M</Interval>` が出る。

3. exe をもう一度ダブルクリックしても二重起動しないこと（タスクマネージャーで `work-pulse-checker.exe` が1つだけ）

4. タスクマネージャーからプロセスを強制終了し、5分以内にトレイアイコンが復活すること

5. 復活後、ログに前回異常終了の警告が出ていること。ログの場所は `%APPDATA%\com.perorin0418.work-pulse-checker\logs\work-pulse-checker.log`

```bash
grep "正常終了していない" "$LOCALAPPDATA/com.perorin0418.work-pulse-checker/logs/work-pulse-checker.log"
```

Expected: 1行以上ヒットする。

6. 設定画面のチェックボックスをオフにして保存すると、タスクが消えること

```bash
schtasks /Query /TN WorkPulseChecker-Keepalive
```

Expected: `ERROR: The system cannot find the file specified.`

7. チェックボックスを戻すとタスクが復活すること。アプリを再起動してもオフのままにならないこと（DBに永続化されている）

- [ ] **Step 9: コミット**

```bash
git add src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/src/lib.rs src/main.ts
git commit -m "自動起動をタスクスケジューラのキープアライブタスクへ差し替え"
```
