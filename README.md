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
