# work-pulse-checker (rebuild)

Windowsタスクスケジューラーに駆動される、常駐なしの作業監視・記録ツール。

## セットアップ

1. Python 3.11以上をインストールする
2. 仮想環境を作成し、依存関係をインストールする

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

3. [Claude Code CLI](https://docs.claude.com/) をインストールし、`claude` コマンドが使える状態にする（`prompt.py` が `claude -p ... --model haiku` を呼び出す）
4. タスクスケジューラーにタスクを登録する

   ```bash
   python install_tasks.py
   ```

   これにより以下の2つのタスクが登録される。

   - `WorkPulseChecker_Monitor`: `monitor.py` を平日7:00〜22:00の間、1分間隔で実行
   - `WorkPulseChecker_Prompt`: `prompt.py` を平日7:00〜22:00の間、30分間隔で実行

   いずれも多重起動時は新規開始しない（`MultipleInstancesPolicy=IgnoreNew`）。

   タスク実行時にコマンドプロンプトの黒いウィンドウが表示されないよう、登録時に同じ場所の
   `pythonw.exe`（存在する場合）へ自動的に差し替える。`prompt.py` から呼び出す `claude -p`
   サブプロセスも `CREATE_NO_WINDOW` フラグ付きで起動するため、コンソールは開かない。

## データ

```
data/YYYY/MM/DD/audit.parquet          # 1分ごとの監視ログ
data/YYYY/MM/DD/work-content.parquet   # 30分ごとの作業内容
data/YYYY/MM/DD/screenshots/HHMM.png   # プロンプト時のスクリーンショット
logs/                                   # 実行時エラーログ
```

## 記録の閲覧・編集

```bash
python view.py --date 2026-08-26
```

その日の作業内容一覧が表示される。番号を入力すると `confirmed_text` を編集できる。監視ログ（`audit.parquet`）は本ツールでは扱わない。

記録済みスロットの最初〜最後の範囲内で、確認ダイアログへの応答が無いなどの理由で作業内容を入力できなかった30分枠は `status=missing` として一覧に補完表示され、他のスロットと同様に番号を入力して内容を確定できる（確定するとファイルに新規行として保存され `status=confirmed` になる）。

## 作業内容確認ダイアログの本日履歴機能

`prompt.py` の確認ダイアログには、本日すでに確定済みの作業内容（新しい順・重複除去・最大8件）がボタンとして表示される。クリックすると入力欄にそのテキストが差し込まれ、同じ作業の継続時に再入力せず確定できる。

Haiku（`claude -p`）への推定依頼にも同じ本日履歴を渡しており、直前の作業内容を踏まえた推定文が得られやすくなっている。

## テスト

```bash
pytest -v
```

## 手動検証チェックリスト（自動テスト対象外の項目）

- [ ] `python monitor.py` を実行し、`data/YYYY/MM/DD/audit.parquet` に1行追記されることを確認する
- [ ] `python prompt.py` を実行し、右下に予告カウントダウンの小窓が表示され、クリックまたは30秒経過で確認ダイアログに進むことを確認する
- [ ] 確認ダイアログにHaikuの推定テキストが初期値として表示され、編集して確定すると `work-content.parquet` に `status=confirmed` で保存されることを確認する
- [ ] 確認ダイアログを放置し、5分後に `status=auto_confirmed` で自動保存されることを確認する
- [ ] `python install_tasks.py` を実行し、タスクスケジューラー（`taskschd.msc`）に2つのタスクが登録されることを確認する
- [ ] 登録されたタスクが平日7:00〜22:00の時間帯設定になっていることをタスクスケジューラーのGUIで確認する
