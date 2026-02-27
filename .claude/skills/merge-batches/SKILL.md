---
name: merge-batches
description: |
  バッチJSON統合（Stage 1）。scan-receiptsで生成したバッチJSONをreceipts.jsonに統合する。
  「バッチ統合」「receipts.json生成」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob
argument-hint: "[year_label]"
---

# バッチJSON統合（Stage 1）

`data/batches/batch_*.json` を統合して `data/receipts.json` を生成する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 1
```

## 処理内容

1. `years/{year_label}/data/batches/batch_*.json` を全て読み込み
2. ID重複チェック
3. 日付順にソート
4. `years/{year_label}/data/receipts.json` に統合出力

## 前提条件

- `scan-receipts` スキルでバッチJSONが生成済みであること

## 出力

- `years/{year_label}/data/receipts.json` — 全領収書の統合データ
