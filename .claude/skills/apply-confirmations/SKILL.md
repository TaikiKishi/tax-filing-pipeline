---
name: apply-confirmations
description: |
  ユーザー確認結果の反映（Stage 3）。突合結果に対するユーザー判断を反映する。
  「確認結果を反映して」「判定を修正して」などの指示で使用。
user-invocable: true
disable-model-invocation: true
allowed-tools: Read, Write, Bash, Glob
argument-hint: "[year_label]"
---

# ユーザー確認反映（Stage 3）

match_results.json に対するユーザー確認結果を反映する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 3
```

## 処理内容

1. `match_results.json` の `conditional`（要確認）項目を読み込み
2. `src/apply_confirmations.py` の年度固有ロジックを適用
3. 確認済み結果で `match_results.json` を更新

## 注意

- このモジュールは**年度固有のロジック**（receipt_id直接参照）を含む
- 来年度は新しい確認内容に書き換える必要がある
- 変更前に必ず `match_results.json` のバックアップを取ること

## 出力

- `years/{year_label}/data/match_results.json`（更新）
