# クレジットカード明細 → freee インポート用 CSV 生成ツール

**v0.1.1**

## 1 プロジェクト概要

このプロジェクトは、**クレジットカード明細の月次 CSV を結合し、手動で「対象チェック」「備考」を付けたあと、freee に取り込める形式の Excel ファイルを生成する** Python ツールです。

- 主なスクリプト: `merge_csv.py`, `process_keihi.py`, `run_merge.py`, `run_keihi.py`
- 実行は常に **リポジトリ直下** を基準に動きます（絶対パスに依存しません）。

---

## 2 できること

1. **明細の結合**: `meisai/` に置いた月次 CSV（`YYYYMM.csv`）を1つのファイルにまとめる
2. **手動チェックの維持**: 結合後も Excel 等で入力した「対象チェック」「備考」を次回実行時に引き継ぐ
3. **経費振り分け**: `rules.yaml` のルールで店名・メモから勘定科目を自動付与
4. **開業費の扱い**: 開業日より前の支出を「開業費」に振り替え（資産は除外）
5. **freee 用 Excel 出力**: `freee_import.xlsx` を freee の経費インポートに利用可能

---

## 3 ディレクトリ構成

```
project_root
├── merge_csv.py
├── process_keihi.py
├── run_merge.py
├── run_keihi.py
├── rules.example.yaml
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
└── meisai
    └── .gitkeep
```

- `rules.yaml` と `meisai/*.csv`、各種生成 CSV は Git で管理しません（後述）。

---

## 4 セットアップ

### Python のバージョン

- Python 3.8 以上を推奨します。確認: `python3 --version`

### 依存ライブラリのインストール

リポジトリ直下で次を実行します。

```bash
pip install -r requirements.txt
```

仮想環境を使う場合の例:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5 rules.yaml の作り方

- `rules.yaml` は個人の勘定科目ルールが入るため、**Git には含めません**。
- 初回だけ、サンプルをコピーして `rules.yaml` を作成してください。

```bash
cp rules.example.yaml rules.yaml
```

エディタで `rules.yaml` を開き、次の項目を自分の環境に合わせて編集します。

- **open_date**: 開業日（YYYY-MM-DD）。この日より前の経費は「開業費」になります。
- **rules**: 店名のキーワードと勘定科目の対応
- **special_cases**: 店名＋メモで勘定科目を分岐する特例

---

## 6 明細CSVの置き方

- クレジットカードの利用明細を、月ごとの CSV で用意します。
- ファイル名は **`YYYYMM.csv`** にします（例: `202501.csv`, `202502.csv`）。
- それらのファイルを **`meisai/`** フォルダの中に置きます。

```
meisai/
├── 202501.csv
├── 202502.csv
└── ...
```

- カード会社によって列名や文字コードが違う場合があります。ツールは UTF-8 / CP932 などを自動判定して読みます。

---

## 7 run_merge.py の実行

リポジトリ直下で次を実行します。

```bash
python3 run_merge.py
```

- `meisai/` 内の `YYYYMM.csv` が結合され、次のファイルが **リポジトリ直下** に作られます。
  - **combined.csv**: 結合した生データ
  - **combined_clean.csv**: 重複整理・手入力列付き（ここを編集します）
  - **combined_duplicates.csv**: 重複として検出された行（あれば）
- `meisai/potential_issues.csv` に、読み込み時の注意点などが出力されることがあります。

---

## 8 Excel での手動チェック

1. **combined_clean.csv** を Excel または LibreOffice で開きます。
2. **対象チェック** 列に、経費として取り込みたい行には **1** を入れます。
3. 必要に応じて **備考** 列にメモを書きます（勘定科目の振り分けに使われます）。
4. 上書き保存して閉じます（UTF-8 BOM で保存されることを推奨）。

---

## 9 run_keihi.py の実行

手動チェックが終わったら、同じくリポジトリ直下で次を実行します。

```bash
python3 run_keihi.py
```

- `combined_clean.csv` を読み、`rules.yaml` のルールで勘定科目を付与します。
- 次のファイルが **リポジトリ直下** に出力されます。
  - **freee_import.xlsx**: freee の経費インポート用（Excel形式）
  - **need_review.csv**: 勘定科目が「要確認」の行だけ
  - **store_summary_with_account.csv**: 店名×勘定科目ごとの集計

freee には **freee_import.xlsx** をインポートして利用します。要確認の行は **need_review.csv** で確認し、必要なら `rules.yaml` を修正して再実行できます。

---

## 10 生成されるファイル

| ファイル | 説明 | Git管理 |
|----------|------|---------|
| combined.csv | 月次CSVをそのまま結合したもの | しない |
| combined_clean.csv | 重複整理済み＋対象チェック・備考列。手編集用 | しない |
| combined_duplicates.csv | 結合後に検出した全列一致の重複行 | しない |
| freee_import.xlsx | freee 経費インポート用（Excel） | しない |
| need_review.csv | 勘定科目が「要確認」の行のみ | しない |
| store_summary_with_account.csv | 店名×勘定科目の集計 | しない |
| meisai/potential_issues.csv | 読み込み時の警告・エラー情報 | しない |

これらはすべて **.gitignore で除外** されているため、Git にコミットされません。

---

## 11 Git 管理されないファイル

- **実データ**: `meisai/*.csv`（明細 CSV）は個人情報のためコミットしません。
- **個人設定**: `rules.yaml` は勘定科目ルールが含まれるためコミットしません。
- **生成物**: 上記の combined_*.csv / freee_import.xlsx などもコミットしません。

リポジトリをクローンした人が使うときは、

1. `rules.example.yaml` をコピーして `rules.yaml` を作成
2. 自分の明細 CSV を `meisai/` に配置

すれば、同じ手順で利用できます。

---

## 12 GitHub 公開前チェックリスト

GitHub に push する前に、以下を確認してください。

- [ ] rules.yaml をコミットしていない
- [ ] meisai/*.csv をコミットしていない
- [ ] freee_import.xlsx をコミットしていない
- [ ] combined_clean.csv をコミットしていない
- [ ] その他生成 CSV をコミットしていない
- [ ] 絶対パスが残っていない
- [ ] rules.example.yaml が存在する
- [ ] README.md が最新
- [ ] .gitignore が存在する

---

## GitHub push 手順

リポジトリを初めて GitHub に上げる場合の例です。`<repo>` は実際のリポジトリURLに置き換えてください。

```bash
git init
git add .
git status   # rules.yaml / meisai/*.csv / 生成CSV が含まれていないことを確認
git commit -m "Initial commit"
git branch -M main
git remote add origin <repo>
git push -u origin main
```

**注意**: `git add .` の前に、`.gitignore` が正しく設定されていることを確認してください。`rules.yaml` や `meisai/*.csv`、生成 CSV がステージされていたらコミットせず、`.gitignore` を確認・修正してから再度 `git add .` してください。

---

## ライセンス・注意

- 本ソフトウェアは MIT License で提供されます。詳細は [LICENSE](LICENSE) を参照してください。
- クレジットカード明細には個人情報が含まれるため、取り扱いには十分注意してください。
