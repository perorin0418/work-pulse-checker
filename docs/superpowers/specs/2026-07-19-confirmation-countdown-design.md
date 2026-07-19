# 確認画面 予告カウントダウン 設計

## 背景・目的

30分ごとの作業確認画面は、現在いきなり表示され、入力作業中のユーザーを不意打ちで邪魔することがある。確認画面が開く前に画面右下へ短いカウントダウンを表示し、心構えができるようにする。

## 現状の動き

- `spawn_scheduler`（[lib.rs:186](../../../src-tauri/src/lib.rs#L186)）が5秒おきに`scheduler_tick`（[lib.rs:200](../../../src-tauri/src/lib.rs#L200)）を実行。
- `scheduler_tick`は`database.due_prompt_interval`（[db.rs:311](../../../src-tauri/src/db.rs#L311)）で「確定待ちのスロットが終了済みか」を判定し、該当すれば`mark_prompted`を呼んで二重発火を防いだ上で`show_prompt`（[lib.rs:358](../../../src-tauri/src/lib.rs#L358)）を呼び、メインウィンドウ（`main`）をリサイズ・中央配置・表示・フォーカスして確認画面（`renderConfirmation`, [main.ts:199](../../../src/main.ts#L199)）を表示する。
- 予告や前段階の表示は一切ない。

## 新しい動き

1. `scheduler_tick`の判定ロジック（いつ「確定待ちが確定した」とみなすか）は変更しない。
2. 条件が揃った瞬間、今まで直接`show_prompt`を呼んでいた箇所を、代わりに新規の小さな「カウントダウンウィンドウ」を画面右下に表示する処理に差し替える。
3. カウントダウンウィンドウは30秒→0秒まで1秒ごとに残り秒数を表示する。
4. 0になったら、そのウィンドウから確認画面を開くコマンドを呼び、カウントダウンウィンドウを閉じ、今まで通り`show_prompt`相当の処理でメインウィンドウの確認画面を開く。
5. カウントダウン表示中にユーザーがカウントダウンウィンドウをクリックした場合、待たずに即座に同じコマンドで確認画面を開く。

結果として、確認画面が実際に開くタイミングは今までより最大30秒後ろ倒しになるが、その間ユーザーは右下の表示で心構えができる。

## アーキテクチャ

### バックエンド（Rust/Tauri）

- 定数追加: `const COUNTDOWN_SECONDS: i64 = 30;`、カウントダウンウィンドウのサイズ定数。
- `scheduler_tick`（[lib.rs:215-221](../../../src-tauri/src/lib.rs#L215-L221)）内の`show_prompt(app, &updated)?`呼び出しを`show_countdown(app, &updated)?`に置き換える。フルスクリーン判定（`is_fullscreen_now`）と`mark_prompted`はそのまま維持する。
- 新関数`show_countdown(app, interval)`:
  - 既に`label: "countdown"`のウィンドウが存在する場合は何もしない（`app.get_webview_window("countdown").is_some()`で判定。Tauriのウィンドウ管理をそのまま二重表示防止に使うため、追加の状態管理は不要）。
  - 存在しなければ`tauri::WebviewWindowBuilder`で新規ウィンドウを作成: `decorations(false)`, `always_on_top(true)`, `skip_taskbar(true)`, `resizable(false)`, `shadow(false)`, 固定サイズ（例: 240x88）、プライマリモニターの作業領域右下に余白（例: 20px）を空けて配置。URLは`countdown.html`。
  - ウィンドウ作成後、`slot_start`と秒数を含むペイロードを、そのウィンドウ宛てにイベント（例: `countdown-start`）で送る。
- 新規Tauriコマンド`open_prompt_now(slot_start: String)`:
  - `slot_start`から該当インターバルを取得し、既存の`show_prompt`を呼んでメインウィンドウの確認画面を開く。
  - `countdown`ウィンドウが存在すれば閉じる（`close()`）。
- `src-tauri/capabilities/default.json`の`"windows"`配列に`"countdown"`を追加し、新コマンドを`invoke_handler`に登録する。

### フロントエンド

- 新規エントリ`countdown.html`（ルート直下、`index.html`と同構成の最小限のHTML）と`src/countdown.ts`（`main.ts`の状態機械には組み込まない、独立した小さいスクリプト）。
- `countdown.ts`の役割:
  - `countdown-start`イベントを受信し、残り秒数を`state`として保持、1秒ごとに`setInterval`で表示を更新。
  - 0になったら`invoke('open_prompt_now', { slotStart })`を呼ぶ。
  - 画面（ウィンドウ全体）のクリックで即座に同じ`invoke('open_prompt_now', { slotStart })`を呼ぶ。
  - 表示は「まもなく確認 (30)」のようなシンプルな数字カウントのみ。アニメーションは作らない。
- `vite.config.ts`に`build.rollupOptions.input`を追加し、`index.html`と`countdown.html`の2エントリをビルド対象にする。

## 対象外（スコープ外）

- スヌーズ中の再通知タイミングへの影響: スヌーズは確認画面を開いた後のみ選択可能な操作であり、今回の変更では触れない。スヌーズ満了時も同じ`due_prompt_interval`判定を通るため、結果的に同じカウントダウンが自然に適用されるが、専用の考慮は行わない。
- フルスクリーン判定を「カウントダウン開始時」以外の追加タイミング（例: カウントダウン終了時の再判定）で行うことはしない。既存通り、カウントダウン開始をゲートする一度きりのチェックのみ。
- マルチモニター環境でのモニター選択UIなど、凝った位置調整は行わない。プライマリモニター基準のみ。

## テスト・検証方針

- 実機で30分待つのは非現実的なため、開発時は`COUNTDOWN_SECONDS`やスロット判定を一時的に短縮するか、`due_prompt_interval`が真になるタイミングを手動で作れるDBレコードを用意して動作確認する。
- 確認項目:
  - スロット終了時に右下にカウントダウンウィンドウが表示される
  - 1秒ごとに数字が減る
  - 0になったら確認画面が開き、カウントダウンウィンドウが閉じる
  - カウントダウン中にクリックすると即座に確認画面が開く
  - フルスクリーンアプリ使用中はカウントダウンが表示されない（既存の`is_fullscreen_now`ガードの動作確認）
  - 同じスロットに対してカウントダウンウィンドウが多重生成されない
