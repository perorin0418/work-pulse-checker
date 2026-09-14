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

### 特定日のサマリーのみを非対話で取得する

対話プロンプトを開かず、指定日の作業サマリー（`confirmed_text` ごとの合計時間・降順、合計時間）だけを標準出力に出して即終了させたい場合は `--summary` を付ける。

```bash
python view.py --date 2026-08-26 --summary
```

出力例:

```
--- 作業サマリー ---
01:30  資料作成
00:30  会議
合計: 02:00
```

その日の記録が無い場合は `2026-08-26 の記録はありません`、記録はあるが `confirmed_text` が1件も無い場合は `2026-08-26 の確定済み作業内容はありません` とだけ出力する。スクリプトやcron的な自動処理から日次サマリーを取得する用途を想定している。

### 作業サマリーを日報管理アプリ入力形式のJSONで取得する

社内の日報管理アプリへの転記用に、作業サマリーを以下9項目のJSON配列として出力する。

`業務種別`, `ジョブコード`, `作業時間`, `詳細コード`, `作業場所`, `作業内容`, `状況`, `保留・宿題事項`, `課題・悩み`

作業サマリーの各行（`confirmed_text` ごとの合計時間）が1レコードに対応し、`業務種別` は固定値「直接原価」、`作業内容` に `confirmed_text`、`作業時間` に `HH:MM` 形式の合計時間が入る。`ジョブコード` と `詳細コード` は下記ルールで自動判定される。それ以外の項目は現状自動入力できないため空文字になる（手動で埋めて日報アプリに転記する想定）。

**ジョブコードの判定ルール（`src/workpulse/job_code.py`）:** 作業内容（`confirmed_text`）は表記ゆれがあり機械的な文字列一致では判定できないため、`claude -p ... --model haiku` に意味的な該当判定をさせている。

- 作業内容が「朝会」「課会」「部会」「日報入力」「庶務」「1on1ミーティング」のいずれか（表記ゆれ・類似表現を含む）に該当する場合: `2502046_【C25】標準準拠システム保守付帯作業`
- それ以外の場合: `2502044_【C25】標準準拠システム保守（共通機能）`

`claude -p` の呼び出しに失敗した場合（未ログイン・CLI未インストール等）は安全側として `2502044_【C25】標準準拠システム保守（共通機能）` にフォールバックする。

**詳細コードの判定ルール（`src/workpulse/detail_code.py`）:** 判定済みのジョブコードごとに選択可能な詳細コード（社内の「作業詳細コード」一覧より）を候補として提示し、`claude -p ... --model haiku` に作業内容から最適な1つを選ばせる。ジョブコードの判定と同様、作業内容の表記ゆれのため機械的な文字列一致では判定できない。

- `2502046_【C25】標準準拠システム保守付帯作業` の候補
  - `Z-01` 会社行事 / `Z-02` 会議体直接PJ以外 / `Z-04` 研修 / `Z-05` 一般事務 / `Z-06` 健康経営活動 / `Z-99` 部・課管理
- `2502044_【C25】標準準拠システム保守（共通機能）` の候補
  - `A-90` 品質向上活動 / `A-91` 障害分析 / `A-92` 各社協議・説明会への参加 / `A-93` 是正・ふりかえり / `A-94` 開発・業務スキル習得 / `A-95` ISO活動
  - `B-10` 課題・QA対応 / `B-11` RD / `B-12` 設計(UI-SS) / `B-13` PS・PG・PT / `B-14` 結合テスト(IT)

Haikuが候補外のコードを返した場合や呼び出しに失敗した場合は、付帯作業なら `Z-05`、共通機能なら `B-10` にフォールバックする。

```bash
python view.py --date 2026-08-26 --daily-report-json
```

出力例:

```json
[
  {
    "業務種別": "直接原価",
    "ジョブコード": "2502044_【C25】標準準拠システム保守（共通機能）",
    "作業時間": "01:30",
    "詳細コード": "B-10",
    "作業場所": "",
    "作業内容": "資料作成",
    "状況": "",
    "保留・宿題事項": "",
    "課題・悩み": ""
  },
  {
    "業務種別": "直接原価",
    "ジョブコード": "2502046_【C25】標準準拠システム保守付帯作業",
    "作業時間": "00:30",
    "詳細コード": "Z-02",
    "作業場所": "",
    "作業内容": "朝会",
    "状況": "",
    "保留・宿題事項": "",
    "課題・悩み": ""
  }
]
```

その日の記録が無い、または確定済み作業が無い場合は空配列 `[]` を出力する。

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

## 勤怠サービス連携（ラッパー層）

勤怠（日報）サービスへの入力は `src/workpulse/attendance/` のラッパー層経由で行う。
サービスが将来変わっても、呼び出し側のコードを変えずに差し替えられる構造にしている。

```
attendance/
  models.py      # Credentials / WorkEntry / DailyRecord / SubmitResult（サービス非依存）
  provider.py    # AttendanceProvider プロトコルと BaseProvider
  errors.py      # AuthenticationError / NavigationError / SubmitError など共通例外
  registry.py    # 名前 → 実装 の対応表（遅延 import）
  config.py      # config/attendance.json + 環境変数の読み込み
  service.py     # open_provider(): 設定に従って生成・ログイン・後始末
  providers/
    hrmos.py     # HRMOS勤怠（Playwright）
```

### 使い方

```python
from datetime import date, datetime
from workpulse.attendance import WorkEntry, open_provider

with open_provider() as provider:
    provider.submit_day(
        WorkEntry(
            work_date=date(2026, 9, 11),
            start_at=datetime(2026, 9, 11, 9, 0),
            end_at=datetime(2026, 9, 11, 18, 0),
            note="実装作業",
        )
    )
```

### 設定

`config/attendance.example.json` をコピーして `config/attendance.json` を作る。
パスワードはファイルに書かず、リポジトリ直下の `.env` か環境変数で渡す
（優先順位は 環境変数 > `.env` > 設定ファイル）。

```bash
cp .env.example .env   # 中身を自分の資格情報に書き換える
```

- `WORKPULSE_ATTENDANCE_LOGIN_ID`
- `WORKPULSE_ATTENDANCE_PASSWORD`

`.env` と `config/attendance.json` は `.gitignore` 済み。

HRMOS を使う場合は Playwright が必要。

```bash
pip install playwright
playwright install chromium
```

### 別サービスへの乗り換え手順

1. `attendance/providers/` に `BaseProvider` を継承したクラスを追加し、
   `login` / `fetch_day` / `submit_day` / `close` を実装する
2. `registry._BUILTIN` に `"名前": "モジュール:クラス"` を1行足す
3. `config/attendance.json` の `provider` をその名前に変える

同一サービスの画面変更だけなら、プロバイダーの `SELECTORS` か
設定の `options.selectors` を直せば済む。

### HRMOS の URL 構造（調査結果）

日報 URL は日付ではなく不透明な ID で、日付から計算できない
（月内は概ね連番だが月をまたぐと飛び、欠番もある）。
そのため `HrmosProvider` は「月次一覧 → 日報画面の日付セレクター」から
その月の `日付 → 日報ID` 対応表を作り、月単位でキャッシュする。

| 用途 | URL |
| --- | --- |
| 日次勤怠一覧（月次） | `/works/{YYYY-MM}`（`?d=` は効かない） |
| 勤怠編集 | `/works/{work_id}/edit?d={YYYY-MM}` |
| 日報 | `/daily_reports/{report_id}`（`/edit` で編集） |

```python
provider.month_url(2026, 9)               # /works/2026-09
provider.report_id(date(2026, 9, 11))     # "577425"
provider.report_url(date(2026, 9, 11))    # /daily_reports/577425
provider.report_ids_for_month(2026, 9)    # {date: id} 30件（キャッシュ）
provider.open_report(date(2026, 9, 11))   # 日報を開いて Page を返す
```

### 日報の読み書き

日報は「大分類・業務名・業務時間(予定)・業務時間(実績)・備考」を持つ複数行で、
1行が `ReportRow`、1日ぶんが `DailyReport` に対応する。時間は分単位で扱い、
画面上の `HH:MM` との変換はプロバイダーが行う。

```python
from datetime import date
from workpulse.attendance import DailyReport, ReportRow, open_provider

with open_provider() as provider:
    # 読み取り（空行は除かれる）
    report = provider.fetch_report(date(2026, 9, 11))

    # 書き込み（既定は置き換え。replace=False で追記）
    provider.submit_report(
        DailyReport(
            work_date=date(2026, 9, 11),
            rows=[
                ReportRow(
                    category="【共通】会議直接ＰＪ以外",  # 表示名でもID("2")でも可
                    service_name="定例会議",
                    result_minutes=90,
                    note="週次",
                ),
            ],
        )
    )
```

行数が足りなければ「追加」ボタンで自動的に増やし、`replace=True` で余った
既存行は空にしてから「登録する」を押す。

### 日報レコード（9項目）との対応

`view.py --daily-report-json` が出す9項目は、`report_format` で `ReportRow` に変換する。

| 日報レコード | HRMOS 日報の欄 |
| --- | --- |
| 業務種別 | 業務列の上段（セレクト） |
| ジョブコード | 業務列の下段（テキスト） |
| 作業時間 | 業務時間(実績) |
| 詳細コード / 作業場所 / 作業内容 / 状況 / 保留・宿題事項 / 課題・悩み | 備考 |

業務時間(予定) は入力しない。備考は次の形式で組み立てる。空欄は「なし」で補うが、
「状況」だけは空欄のままにする（`KEEP_EMPTY_FIELDS`）。

```
【詳細コード】Z-02
【作業場所】自宅（リモート）
【作業内容】朝会
【状況】完了
【保留・宿題事項】なし
【課題・悩み】なし
```

```python
from workpulse.attendance import open_provider, rows_from_records
from workpulse.attendance.models import DailyReport

rows = rows_from_records(records)   # records は --daily-report-json の出力
with open_provider() as provider:
    provider.submit_report(DailyReport(work_date=date(2026, 9, 11), rows=rows))
```

`row_to_record()` で逆変換もできるので、登録済み内容を9項目の形で確認できる。

### 勤怠実績からの自動判定

`fetch_day()` は日次勤怠一覧から勤務区分・打刻・実労働時間を読む。
`planner.plan_report()` はそれを見て「日報が要る日か」「何分計上するか」を決める。
判定はサービス非依存で、`planner.py` にまとまっている。

- 勤務区分に「休日」「全休」「欠勤」が含まれる日は行なし（`skipped=True`）
- 実労働時間が 0 の日も行なし
- 半休（`有休(PM)` など）は実労働時間ぶんの日報を作る
- 作業内容（`WorkItem`）が無ければ既定の1行にまとめる
- 作業内容があれば実労働時間を按分し、端数は最後の行で吸収して合計を一致させる
- `WorkItem.minutes` を指定した行は固定、残りを他の行で分ける

```python
from workpulse.attendance import PlanPolicy, WorkItem, open_provider, plan_report

policy = PlanPolicy(default_category="【共通】会議直接ＰＪ以外", default_service_name="通常業務")
items = [
    WorkItem(service_name="開発"),
    WorkItem(service_name="定例会議", minutes=30, note="週次"),
]

with open_provider() as provider:
    record = provider.fetch_day(date(2026, 9, 11))
    plan = plan_report(record, items=items, policy=policy)
    print(plan.reason)          # なぜその結果になったか
    if not plan.skipped:
        provider.submit_report(plan.report)
```

### bat から登録する（Windows）

`submit_report.bat` をダブルクリックすると対象日を聞かれ、内容を確認してから登録する。
既定は前営業日（月曜なら金曜）なので、そのまま Enter でもよい。

```
対象日を入力してください [YYYY-MM-DD] (既定: 2026-09-11):
■ 2026-09-11 に登録する内容（1件）
--- 1 ---
  業務種別    : 直接原価
  ジョブコード: 2502044_【C25】標準準拠システム保守（共通機能）
  作業時間    : 03:36
  ...
この内容で登録しますか？ [y/N]:
```

コマンドラインから使う場合は `submit_report.py` を直接呼ぶ。

```bash
python submit_report.py --date 2026-09-11              # 確認あり
python submit_report.py --date 2026-09-11 --dry-run    # 送信内容だけ表示
python submit_report.py --date 2026-09-11 --yes        # 確認を省略
python submit_report.py --date 2026-09-11 --append     # 既存行を残して追記
python submit_report.py --date 2026-09-11 --json records.json  # JSONから登録
```

`--json` を省略すると、その日の `work-content.parquet` から
`view.py --daily-report-json` と同じ9項目を生成して登録する。
bat に渡した引数はそのまま `submit_report.py` に渡る。

終了コードは 0=成功、1=中止または失敗、2=日付の形式誤り。

### bat から記録を編集する（Windows）

`edit_report.bat` をダブルクリックすると対象日を聞かれ、その日の作業記録を
一覧表示して番号を選んで編集できる（`view.py` と同じ対話）。

```
対象日を入力してください [YYYY-MM-DD] (既定: 2026-09-11):
[0] 09:00-09:30 (confirmed) 朝会
[1] 09:30-10:00 (confirmed) 実装作業
編集する番号を入力してください（何も入力せず終了する場合はEnter）
>
```

引数は `view.py` にそのまま渡るので、日付やオプションを指定した起動もできる。

```bash
python edit_report.py                              # 日付を聞いてから対話編集
python edit_report.py --date 2026-09-11            # 日付を指定して対話編集
python edit_report.py --date 2026-09-11 --summary  # サマリーのみ表示
```

`--date` を明示した場合は日付を聞かない。空入力なら前営業日を使う。

運用の流れは「`edit_report.bat` で内容を整える → `submit_report.bat` で登録」。
