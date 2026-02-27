# 確定申告バックデータ管理ツール

日本の確定申告（所得税の確定申告）における医療費控除・社会保険料控除の証跡管理ツール。
領収書のスキャンデータ、マイナポータル通知データ、集計結果を一元管理し、
e-Tax提出用の医療費集計フォーム（xlsx）と各種レポートを自動生成する。

## ディレクトリ構成

```
tax-filing-pipeline/
  src/                  # パイプラインスクリプト（年度非依存）
  templates/            # NTA公式テンプレート等
    pandoc/             # pandoc プロファイル（請求書PDF生成用）
  years/                # 年度別ディレクトリ（証跡保管の単位）
    sample/             # テンプレート年度ディレクトリ
    {YYYY}_{RX}/        # 年度ディレクトリ（例: 2025_R7）
      sources/          # リネーム済みソースファイル（5年保存）
      data/             # 中間データ（JSON）
      output/           # 最終出力（xlsx, md）
        invoices/       # 請求書（.gitignore対象、個人情報含む）
      source_config.json # スキャナー設定
      manifest.json     # ファイルトレーサビリティ
  docs/                 # 参考資料・ガイド（年度非依存）
```

## パイプライン

全ステージを順に実行：
```bash
python3 -m src.pipeline {YYYY}_{RX}
```

個別ステージのみ：
```bash
python3 -m src.pipeline {YYYY}_{RX} --stage 3
```

### ステージ一覧

| # | モジュール / スキル | 説明 |
|---|-------------------|------|
| 0 | organize_sources | ソースファイル整理・リネーム・manifest.json 生成 |
| 0.5 | `/scan-receipts` (スキル) | 領収書PDF/画像 → 構造化JSON（Claude Codeで実行） |
| 1 | merge_batches | バッチJSON統合 → receipts.json |
| 2 | match_and_judge | 領収書 × マイナポータル突合・控除判定 |
| 3 | apply_confirmations | ユーザー確認結果の反映（confirmation_rules.json 駆動） |
| 4 | generate_xlsx | 医療費集計フォーム（NTA公式テンプレートベース）生成 |
| 5 | generate_reports | judgment_report.md, tax_summary.md, verification_checklist.md 生成 |
| 6 | prefiling_check | NTA QAベース事前チェックリスト（e-Tax入力前に実行） |

各Pythonモジュールは `run(year_dir: Path, year_label: str)` インターフェースを持つ。
Stage 0.5 は Claude Code スキル（`/scan-receipts`）として実行する。

### Claude Code スキル・エージェント

| 種類 | 名前 | 説明 |
|------|------|------|
| スキル | `/scan-receipts` | 領収書PDF/画像をClaude Codeで読み取り→バッチJSON |
| スキル | `/prefiling-check` | NTA QAベース事前チェックリスト |
| スキル | `/run-pipeline` | パイプライン全体の実行ガイド |
| スキル | `/organize-sources` | Stage 0 実行 |
| スキル | `/merge-batches` | Stage 1 実行 |
| スキル | `/match-and-judge` | Stage 2 実行 |
| スキル | `/apply-confirmations` | Stage 3 実行 |
| スキル | `/generate-xlsx` | Stage 4 実行 |
| スキル | `/generate-reports` | Stage 5 実行 |
| スキル | `/generate-invoice` | 請求書 Markdown 生成 → PDF 変換 |
| スキル | `/manage-misc-income` | 雑所得（副業収入・経費）の管理 |
| スキル | `/furusato-limit` | ふるさと納税 控除上限額シミュレーター |
| エージェント | receipt-reader | 1件の領収書を読み取る自律エージェント |

## 年度ディレクトリの命名規則

`{西暦}_{元号略称}` 形式（例: `2025_R7`）。西暦を先頭にすることで元号が変わっても正しくソートされる。

## 年度設定ファイル

各年度ディレクトリに以下の設定ファイルを配置する:

- **`source_config.json`**: スキャナープレフィックス、インポートディレクトリ、補填書類パス
- **`data/year_config.json`**: 除外患者（子ども医療費助成等）の設定
- **`data/confirmation_rules.json`**: Stage 3 のユーザー確認ルール（JSON駆動）
- **`data/salary_income.json`**: 源泉徴収票データ（ふるさと納税上限額の事後確認で使用）

テンプレートは `years/sample/` を参照。

## 重要な注意

- **NTAテンプレート**: `templates/iryouhi_form_v3.1.xlsx` は国税庁公式テンプレートを使用。
  openpyxl でシート保護を一時解除し、unlocked セル（B-I列, 9行目以降）のみに書き込む。
- **補填される金額**: `reimbursements.json` で管理。`(patient, facility)` キーで xlsx 行にマッチング。
  個々の医療費を超えない範囲でのみ差し引く（税法上のルール）。
- **apply_confirmations.py**: `confirmation_rules.json` でルールを定義。
  "updates" / "new_entries" / "compensations" / "resolved_ids" の 4 セクションで構成。
- **manifest.json**: original_name → stored_path → receipt_id のトレーサビリティを提供。
  generate_checklist.py が参照してファイル名を解決する。
- **misc_income.json**: `data/` 内に配置。雑所得（副業収入・原稿料等）と必要経費を管理。
  `issuer` ブロック（発行者情報）、`income[]`（収入・入金確認）、`expenses[]`（経費・按分計算）を格納。
  Stage 5 のレポート生成・Stage 6 のプレファイリングチェック・請求書PDF生成で使用。
- **請求書PDF**: `src/generate_invoice.py` で Markdown 生成 → `md2pdf --profile invoice` で PDF 変換。
  pandoc + XeLaTeX（IPAMincho）を使用。初回は `bash templates/pandoc/deploy.sh` でプロファイルをデプロイ。
  生成物（`output/invoices/`）には住所・銀行口座情報が含まれるため `.gitignore` で除外。
- **salary_income.json**: `data/` 内に配置。源泉徴収票データを転記。
  ふるさと納税上限額の事後確認モード（`/furusato-limit`）で使用。
  ファイルが存在しない場合はシミュレーションモード（対話入力）に自動切替。

## 技術スタック

- Python 3.10+
- openpyxl（xlsx読み書き）
- 標準ライブラリのみ（openpyxl以外の外部依存なし）

## クレデンシャル検知

- コミット前に gitleaks による自動スキャンが実行される（pre-commit フック）
- `.env` ファイルや API キー等のクレデンシャルをコードにハードコードしないこと

## git 管理上の注意

- `docs/references/` と `years/*/sources/` は `.gitignore` で除外（個人情報含む領収書スキャン等）
- `years/*/data/` と `years/*/output/` はコミット対象（JSON集計データ・レポート）
- テンプレート (`templates/`) はコミット対象
