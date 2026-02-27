---
name: manage-misc-income
description: |
  雑所得（副業収入・原稿料等）の管理。収入・経費の一覧表示、追加、入金確認、サマリー表示。
  「雑所得を管理」「副業収入を追加」「入金確認」「雑所得の一覧」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Edit, Bash, Glob, AskUserQuestion
argument-hint: "[year_label] [action]"
---

# 雑所得管理（misc_income.json）

副業収入・原稿料等の雑所得と必要経費を `misc_income.json` で一元管理する。

## 対象年度

年度ラベル: `$ARGUMENTS` の最初の引数（例: `2025_R7`）
アクション: `$ARGUMENTS` の2番目の引数（省略時は一覧表示）

## データファイル

`years/{year_label}/data/misc_income.json`

## アクション一覧

### 一覧表示（デフォルト）

収入と経費をテーブル形式で表示する。

**収入テーブル:**

| # | 取引先 | 種別 | 金額 | 源泉徴収 | 差引額 | 入金確認 | 請求書 |
|---|--------|------|------|---------|--------|---------|--------|

**経費テーブル:**

| # | 項目 | 金額(税込) | 按分率 | 控除額 |
|---|------|-----------|--------|--------|

**サマリー:**
- 収入合計 / 源泉徴収合計 / 経費控除合計 / 雑所得金額（収入 - 経費）

### 収入追加

ユーザーに以下を質問し、income 配列に追加する：

1. **payer** - 取引先名（例: 株式会社○○）
2. **payer_address** - 取引先住所（任意）
3. **amount** - 報酬額（税込、整数）
4. **income_type** - 種別（原稿料 / 謝金 / コンサルティング / その他）
5. **withholding** - 源泉徴収税額（0 の場合は省略可）
6. **date** - 請求日 or 取引日（YYYY-MM-DD）
7. **payment_date** - 支払日（YYYY-MM-DD、未定の場合は空）
8. **notes** - 備考

自動設定:
- `reference_id`: `YYYYMMDDNNN` を date + 連番から生成
- `payment_confirmed`: false
- `received_amount`: null
- `invoice_file`: null

### 経費追加

ユーザーに以下を質問し、expenses 配列に追加する：

1. **item** - 経費項目名
2. **amount_jpy** - 金額（円建て）
3. **allocation_rate** - 按分率（0.0-1.0）
4. **notes** - 備考

自動計算:
- `deductible`: `amount_jpy * allocation_rate`（整数に丸め）

USD 建ての場合は追加で質問:
- **amount_usd** - USD金額
- **exchange_rate** - 為替レート

### 入金確認

未確認（`payment_confirmed: false`）の収入一覧を表示し、
ユーザーが選択した項目の以下を更新：

- `payment_confirmed`: true
- `received_amount`: 実際の入金額（源泉徴収後）

### サマリー表示

確定申告用のサマリー情報を表示：

- 収入合計
- 源泉徴収合計
- 必要経費合計（控除額ベース）
- 雑所得金額 = 収入合計 - 必要経費合計
- 差引所得税額（概算）

## バリデーション

以下を検出して警告する：

- 源泉徴収額 > 報酬額
- 重複する reference_id
- `payment_confirmed: true` なのに `received_amount` が null
- `allocation_rate` が 0 以下または 1 超

## issuer ブロック

`misc_income.json` のトップレベルに `issuer` ブロックがあり、
請求書生成（`/generate-invoice`）で使用する発行者情報を格納する。
このスキルでは issuer の表示・編集もサポートする。
