---
name: run-pipeline
description: |
  確定申告パイプラインを全ステージ順に実行する。
  「パイプライン実行」「全ステージ実行」「確定申告処理を開始」などの指示で使用。
  個別ステージは各スキル（scan-receipts, organize-sources等）を使用すること。
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Bash, Glob, Grep
argument-hint: "[year_label] [--from stage_number]"
---

# 確定申告パイプライン実行

全ステージを順に実行する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## パイプライン全体フロー

```
[事前準備]
  docs/references/ にスキャンファイルを配置

[Stage 0] organize-sources
  ソースファイル整理・リネーム・manifest.json生成

[Stage 0.5] scan-receipts  ★新規
  領収書PDF/画像 → 構造化JSON（バッチファイル）

[Stage 1] merge-batches
  バッチJSON統合 → receipts.json

[Stage 2] match-and-judge
  領収書 × マイナポータル突合・控除判定

[Stage 3] apply-confirmations
  ユーザー確認結果の反映

[Stage 4] generate-xlsx
  医療費集計フォーム（xlsx）生成

[Stage 5] generate-reports
  証跡レポート一括生成

[Stage 6] prefiling-check  ★新規
  NTA QAベース事前チェックリスト

[e-Tax入力]
  output/etax_entry_guide.md に従ってe-Taxで申告
```

## 実行方法

### 全ステージ一括（Python部分）

```bash
python3 -m src.pipeline $0
```

### 新規ステージを含む全体フロー

1. まず `scan-receipts` スキルで領収書を読み取る
2. 次に Python パイプラインを Stage 0 から実行
3. 最後に `prefiling-check` スキルでe-Tax入力前チェック

### 個別ステージ

```bash
python3 -m src.pipeline $0 --stage N
```

## ステージ間の依存関係

| ステージ | 入力 | 出力 |
|---------|------|------|
| 0: organize-sources | docs/references/ | sources/, manifest.json |
| 0.5: scan-receipts | sources/receipts/*.pdf | data/batches/batch_*.json |
| 1: merge-batches | data/batches/*.json | data/receipts.json |
| 2: match-and-judge | receipts.json, mynaportal.json | match_results.json |
| 3: apply-confirmations | match_results.json | match_results.json (更新) |
| 4: generate-xlsx | match_results.json, reimbursements.json | medical_expense_form.xlsx |
| 5: generate-reports | match_results.json, mynaportal.json, receipts.json | *.md レポート群 |
| 6: prefiling-check | 全データ | prefiling_checklist.md |
