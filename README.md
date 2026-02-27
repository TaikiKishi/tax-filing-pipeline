# 確定申告バックデータ管理パイプライン

日本の確定申告（所得税の確定申告）における医療費控除・社会保険料控除の証跡管理ツール。

領収書のスキャンデータ、マイナポータル通知データ、集計結果を一元管理し、
e-Tax提出用の医療費集計フォーム（xlsx）と各種レポートを自動生成します。

## 主な機能

- **領収書OCR**: Claude Code のマルチモーダル機能で PDF/画像の領収書を構造化JSON に変換
- **マイナポータル突合**: 領収書とマイナポータル医療費通知を自動突合・控除判定
- **医療費集計フォーム**: NTA公式テンプレートベースの xlsx 自動生成
- **証跡レポート**: 判定根拠・サマリー・照合チェックリストの自動生成
- **社会保険料控除**: 国民年金・国保税の管理
- **雑所得管理**: 副業収入・経費の管理・請求書PDF生成
- **ふるさと納税**: 控除上限額シミュレーター（源泉徴収票ベースの事後確認対応）
- **事前チェック**: NTA QA ベースの e-Tax 入力前チェックリスト

## セットアップ

```bash
git clone https://github.com/YOUR_USERNAME/tax-filing-pipeline.git
cd tax-filing-pipeline
pip install -r requirements.txt

# pre-commit フック（gitleaks）
pip install pre-commit
pre-commit install

# 請求書PDF生成を使う場合（pandoc + XeLaTeX）
bash templates/pandoc/deploy.sh
```

## 使い方

### 1. 年度ディレクトリの作成

`years/sample/` をコピーして年度ディレクトリを作成:

```bash
cp -r years/sample years/2025_R7
```

### 2. 設定ファイルの編集

- `years/2025_R7/source_config.json` — スキャナー設定
- `years/2025_R7/data/year_config.json` — 除外患者等

### 3. パイプライン実行

```bash
# 全ステージ実行
python3 -m src.pipeline 2025_R7

# 個別ステージ
python3 -m src.pipeline 2025_R7 --stage 2
```

### Claude Code スキル

Claude Code 環境では以下のスキルが利用可能:

| スキル | 説明 |
|--------|------|
| `/scan-receipts` | 領収書PDF/画像 → 構造化JSON |
| `/run-pipeline` | パイプライン実行ガイド |
| `/generate-invoice` | 請求書PDF生成 |
| `/manage-misc-income` | 雑所得管理 |
| `/furusato-limit` | ふるさと納税上限額シミュレーター |
| `/prefiling-check` | e-Tax入力前チェック |

## パイプラインステージ

| # | ステージ | 説明 |
|---|---------|------|
| 0 | organize_sources | ソースファイル整理・manifest.json 生成 |
| 0.5 | `/scan-receipts` | 領収書OCR（Claude Code スキル） |
| 1 | merge_batches | バッチJSON統合 → receipts.json |
| 2 | match_and_judge | 領収書 × マイナポータル突合・控除判定 |
| 3 | apply_confirmations | ユーザー確認結果の反映 |
| 4 | generate_xlsx | 医療費集計フォーム生成 |
| 5 | generate_reports | 証跡レポート一括生成 |
| 6 | prefiling_check | NTA QA ベース事前チェック |

## 技術スタック

- Python 3.10+
- openpyxl（xlsx読み書き）
- Claude Code（領収書OCR・スキル実行）
- pandoc + XeLaTeX（請求書PDF、オプション）

## ライセンス

個人利用を想定したツールです。NTA公式テンプレート (`templates/iryouhi_form_v3.1.xlsx`) は国税庁の著作物です。
