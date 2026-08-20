# アプリ常駐の自動復活と死因記録 設計

## 背景・目的

常駐しているはずのアプリが不意に落ち、タスクトレイのアイコンごと消えて活動サンプリングが止まることがある。落ちても最大5分で自動復活し、かつ「なぜ落ちたか」が後から追える状態にする。

## 現状の問題

### 1. 自動起動が壊れたまま自己修復しない（実測で確認済み）

`configure_autostart`（[lib.rs:113](../../../src-tauri/src/lib.rs#L113)）は `tauri-plugin-autostart` の `is_enabled()` が false のときだけ `enable()` を呼ぶ。Windows ではこのプラグインはレジストリ `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` にフルパスを1回書き込むだけで、`is_enabled()` は**値の存在しか見ず、パスの妥当性は見ない**。

実機の登録値は次のとおりで、指しているファイルは存在しない。

```
Work Pulse Checker    REG_SZ    D:\GitWorkspace\github-copilot-app\copilot-worktrees\work-pulse-checker\perorin0418-fantastic-robot\build\exe\work-pulse-checker.exe
```

旧 worktree でビルドした exe のパスが固着している。`StartupApproved\Run` の値は `02` 始まり（有効側）なので、タスクマネージャーで無効化されているわけではない。つまり**ログオンしても起動していない**。「アイコンごと消えていた」の主要因はこれである可能性が高い。

exe を別フォルダにビルドし直すたびに同じ壊れ方をする構造的な欠陥であり、パスを書き直すだけでは再発する。

### 2. 落ちた後に復活する仕組みがない

レジストリ Run キーはログオン時に1回起動するだけ。ログオン後にプロセスが落ちたら、次のログオンまで監視は止まったままになる。

### 3. リリースビルドでログが一切出ない

`tauri_plugin_log` の初期化は `if cfg!(debug_assertions)`（[lib.rs:64](../../../src-tauri/src/lib.rs#L64)）の中にあり、リリースビルドでは登録されない。パニックフックも設定していないため、クラッシュの痕跡がどこにも残らない。

### 4. ワーカースレッドのパニック耐性がない

`spawn_sampler`（[lib.rs:178](../../../src-tauri/src/lib.rs#L178)）と `spawn_scheduler`（[lib.rs:194](../../../src-tauri/src/lib.rs#L194)）は `Result` のエラーはログに流してループを続けるが、パニックが起きるとスレッドごと終了する。プロセスは生き残りトレイアイコンも残るため、監視だけが静かに止まる。

## 新しい動き

復活を二段構えにする。

- 一段目（プロセス外）: Windows タスクスケジューラが5分ごとにアプリの起動を試みる。生きていれば何も起きず、死んでいれば復活する。監視役が OS 本体なので監視役自体が死なない。
- 二段目（プロセス内）: 各ワーカーのティックをパニック耐性のあるラッパーで包み、ウォッチドッグがティックの停止を検知してワーカーを作り直す。プロセスが生きたまま監視だけ止まる事象を潰す。

あわせて死因を残す。リリースビルドでもファイルログを出し、パニック内容とバックトレースを記録し、前回が異常終了だったかを起動時に判定して残す。

落ちていた間の30分枠は既存の `backfill_missed_intervals`（[db.rs:254](../../../src-tauri/src/db.rs#L254)）が pending として埋め、復活後に確認プロンプトが順に出る。ここは変更しない。

## アーキテクチャ

### 新規モジュール `src-tauri/src/keepalive.rs`

タスクスケジューラ連携を1箇所に閉じる。外に見せるのは次の3つ。

- `pub fn reconcile(desired_enabled: bool) -> Result<()>` — 望ましい状態にタスクを一致させる
- `pub fn build_task_xml(exe_path: &str, user_id: &str) -> String` — 登録用XMLを組み立てる純粋関数
- `pub fn remove_legacy_run_key() -> Result<()>` — 旧レジストリ Run キーを削除する

#### タスク定義

- タスク名: `WorkPulseChecker-Keepalive`
- トリガー: 2本。
  - `LogonTrigger` — ログオン直後に起動する。繰り返しは持たせない
  - `TimeTrigger` — `StartBoundary` を過去の固定日時（`2020-01-01T00:00:00`）にし、`<Repetition><Interval>PT5M</Interval></Repetition>` を持たせる。`Duration` を書かないことで無期限に5分ごと繰り返す
- 繰り返しを `LogonTrigger` ではなく `TimeTrigger` に持たせるのは、`Repetition` が「そのトリガーが発火した時点」から回り始めるため。既にログオン済みの状態でタスクを登録した直後は `LogonTrigger` が一度も発火しておらず、繰り返しも始まらない。実機で `NextRunTime` が空になることを確認済み。過去起点の `TimeTrigger` なら登録した瞬間から回る
- `BootTrigger` は使わない。トレイ常駐アプリには対話セッションが必要なため
- アクション: 現在の実行ファイルのフルパス（`std::env::current_exe()`）を引数なしで起動
- `<Principal><LogonType>InteractiveToken</LogonType><UserId>ドメイン\ユーザー</UserId></Principal>` — パスワード保存が不要で、管理者権限も不要
- `<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>` — タスクが起動したプロセスは常駐し続けるのでタスクインスタンスも動作中のままになる。生存中の再起動はここで弾かれる
- `<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>`、`<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>` — ノートPCでも止まらないように
- `<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>` — 無制限。既定の72時間で強制終了されるのを防ぐ
- `<IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd></IdleSettings>`

#### 登録と解除

`reconcile(true)`:

1. XML を一時ファイルへ **UTF-16LE + BOM** で書き出す。`schtasks /XML` は UTF-8 のファイルを読めない環境があるため
2. `schtasks /Create /TN WorkPulseChecker-Keepalive /XML <一時ファイル> /F` を実行
3. 一時ファイルを削除

`/F` による上書き登録を**毎回の起動時に無条件で実行する**。これにより exe パスが常に現在のパスへ追従し、現状のパス固着が構造的に起きなくなる。

`reconcile(false)`: `schtasks /Delete /TN WorkPulseChecker-Keepalive /F` を実行する。タスクが存在しなければ何もしない。

`/Change /DISABLE` ではなく削除を選ぶ理由は、有効・無効の判定に `schtasks /Query` の出力を解釈する必要がなくなるため。出力は UTF-16 かつロケール依存で、パースが壊れやすい。

#### 子プロセスのコンソール抑止

`schtasks` と `reg` の呼び出しはすべて `std::os::windows::process::CommandExt::creation_flags(0x08000000)`（`CREATE_NO_WINDOW`）を付ける。付けないと起動のたびにコンソールウィンドウが一瞬光る。

#### 旧 Run キーの削除

起動のたびに `reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Work Pulse Checker" /f` を実行する。値が無い場合は非ゼロ終了するがそれを無視することで冪等になり、「初回かどうか」を記録する必要がなくなる。壊れたパスのエントリを残しておく理由がない。

### 多重起動防止

`tauri-plugin-single-instance`（バージョン `2`）を追加する。二番目のインスタンスのコールバックでは**何もしない**（既存ウィンドウを前面に出す処理は書かない）。5分ごとにウィンドウが勝手に開いては困るため。二番目のプロセスはそのまま終了する。

`MultipleInstancesPolicy=IgnoreNew` と役割が重複するが、タスク経由以外の起動（ユーザーが exe を直接ダブルクリックする等）も塞ぐため両方入れる。

### 自動起動トグルの差し替え

`tauri-plugin-autostart` を依存から外し、`app.autolaunch()` の呼び出しをすべて削除する。トグルの意味は「タスクスケジューラのキープアライブタスクを登録するかどうか」に変わる。

望ましい状態は DB に持つ。OS 側の状態を真実とすると、`reconcile` が毎回タスクを作り直す仕様と衝突する（ユーザーが無効化しても次の起動で復活してしまう）ため。

- `initialize`（[db.rs:37](../../../src-tauri/src/db.rs#L37)）に `CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);` を追加
- `keepalive_enabled` キーに `"true"` / `"false"` を保存。行が無ければ `true` とみなす
- `load_settings`（[db.rs:101](../../../src-tauri/src/db.rs#L101)）の引数 `autostart_enabled: bool` を廃止し、DB から読む
- `save_settings`（[db.rs:111](../../../src-tauri/src/db.rs#L111)）のトランザクションで `keepalive_enabled` も更新する
- `save_settings` コマンド（[lib.rs:572](../../../src-tauri/src/lib.rs#L572)）の autolaunch 操作を `keepalive::reconcile(input.autostart_enabled)` に置き換える
- `setup` では DB の値を読んで `reconcile` を呼ぶ

フロントエンド（[main.ts:392](../../../src/main.ts#L392)）のチェックボックスはそのまま使う。ラベルだけ実態に合わせて調整する。`SettingsDto` / `SettingsInput` のフィールド名 `autostartEnabled` は変更しない。

### プロセス内耐性

#### パニックを飲み込むティックラッパー

```
fn guarded<F: FnOnce()>(label: &str, body: F)
```

`std::panic::catch_unwind(AssertUnwindSafe(body))` で包み、`Err` を受けたら `log::error!` に label 付きで記録して戻る。`spawn_sampler` と `spawn_scheduler` のループ本体をこれで包む。

前提として `Cargo.toml` の release プロファイルに `panic = "abort"` を**設定しない**。設定するとアンワインドが無効になり `catch_unwind` が機能しない。現状は未設定なのでそのままでよい。

#### ウォッチドッグ

- 各ワーカーは1ティックごとに自分の `Arc<AtomicI64>`（epoch 秒）を更新する
- 監視スレッドが30秒ごとに両方を確認し、`now - last_tick > 90` ならそのワーカーを停止扱いにしてログへ記録し、新しいスレッドを起動する
- 各ワーカーは `Arc<AtomicU64>` の世代番号を共有し、ループの先頭で自分の世代と一致しなければ `return` する。ウォッチドッグは再起動時に世代番号を進める。これによりハングした古いスレッドが復帰しても二重にサンプルを書かない
- 停止判定は純粋関数 `fn is_stale(last_tick: i64, now: i64, threshold_secs: i64) -> bool` に切り出す

サンプラーの間隔は3秒、スケジューラは5秒なので、90秒はどちらにとっても十分な余裕がある。

### 診断

#### ファイルログ

`tauri_plugin_log` の登録を `cfg!(debug_assertions)` の外へ出し、リリースでも有効にする。

- 出力先: `TargetKind::LogDir { file_name: Some("work-pulse-checker".into()) }`。デバッグビルドでは `Stdout` も追加する
- レベル: `LevelFilter::Info`
- ローテーション: `max_file_size` を 2 MiB、`RotationStrategy::KeepOne`

#### パニックフック

`run()` の先頭、`tauri::Builder` を組む前に `std::panic::set_hook` を設定する。パニックのメッセージ、発生位置、`std::backtrace::Backtrace::force_capture()` の結果を `log::error!` へ書く。`force_capture` は環境変数に依存せず常にバックトレースを取るため `RUST_BACKTRACE` の設定は不要。

ログプラグインの登録前にパニックした分は取りこぼすが、そこは Tauri 起動前の極小区間なので許容する。

#### 異常終了の検知

`app_data_dir` に `running.marker` を置く。

1. `setup` で marker の存在を確認する。存在していれば前回は正常終了していない。`log::warn!` に「前回が異常終了」と記録する
2. 確認後、marker を作成（または更新）する。中身は起動時刻の RFC3339 文字列
3. トレイメニューの `quit`（[lib.rs:158](../../../src-tauri/src/lib.rs#L158)）で `app.exit(0)` を呼ぶ前に marker を削除する

marker の操作は `CrashMarker` 構造体にまとめる。

- `fn check_and_arm(&self) -> Result<bool>` — 残留していたら `true` を返し、そのうえで marker を張り直す
- `fn disarm(&self) -> Result<()>` — 削除する。存在しない場合も成功扱い

## テスト

Rust のユニットテストで次を検証する。

- `build_task_xml` が exe パスを埋め込み、`PT5M` / `IgnoreNew` / `PT0S` / `InteractiveToken` を含むこと
- `build_task_xml` が exe パスとユーザー名に含まれる `&` `<` `>` をXMLエスケープすること
- `is_stale` の境界（閾値ちょうどでは false、閾値超過で true）
- `guarded` がパニックを飲み込んで呼び出し元へ正常に戻ること
- `CrashMarker` の状態遷移。一時ディレクトリを使い、初回 `check_and_arm` が false、再度呼ぶと true、`disarm` 後の `check_and_arm` が false になること

`schtasks` の実行そのもの、single-instance の挙動、ログファイルの生成は手動で確認する。手順は次のとおり。

1. リリースビルドして起動する
2. `schtasks /Query /TN WorkPulseChecker-Keepalive` でタスクが登録されていること
3. タスクマネージャーからプロセスを強制終了する
4. 5分以内にトレイアイコンが復活すること
5. `app_log_dir` のログに異常終了の警告が出ていること
6. 設定画面でトグルをオフにするとタスクが消え、オンにすると戻ること

## 対象外（スコープ外）

- 落ちていた区間を「アプリ停止中」として履歴上で区別する表示。既存の backfill が pending 枠として埋めるところまでで足りるため、DBスキーマとUIの変更は行わない
- Windows サービス化。セッション0分離によりトレイアイコンとウィンドウを出せないため採用しない
- MSI インストーラへのタスク登録の組み込み。配布は `build-exe.bat` による生 exe のコピーが中心で噛み合わないため、アプリ自身による登録に一本化する
- クラッシュダンプ（minidump）の取得。まずはパニックログで足りるかを見る
