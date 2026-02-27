---
name: generate-reports
description: |
  証跡レポート一括生成（Stage 5）。判定根拠、サマリー、チェックリストを出力する。
  「レポート生成」「サマリー出力」「チェックリスト作成」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob
argument-hint: "[year_label]"
---

# 証跡レポート一括生成（Stage 5）

判定根拠レポート、税務サマリー、照合チェックリストを一括生成する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 5
```

## 出力ファイル

| ファイル | 内容 |
|---------|------|
| `judgment_report.md` | 全件の判定根拠一覧（receipt_id, 突合結果, 控除判定, 理由） |
| `tax_summary.md` | 確定申告全体サマリー（控除額合計、区分別内訳） |
| `verification_checklist.md` | 照合チェックリスト（ソースファイル↔JSON↔xlsxの突合確認用） |

## 処理内容

1. `match_results.json`, `mynaportal.json`, `receipts.json` を読み込み
2. `generate_report.py`: judgment_report.md, tax_summary.md を生成
3. `generate_checklist.py`: verification_checklist.md を生成（manifest.json参照）
