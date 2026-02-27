---
name: scan-receipts
description: |
  スキャン済み領収書PDF・画像を読み取り、構造化JSONを生成する。
  「領収書を読み取って」「レシートをOCRして」「PDFからデータを抽出して」などの指示で使用。
  Claude Codeのマルチモーダル機能でPDF/画像を直接読み取り、バッチJSONを出力する。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: "[year_label] [source_directory]"
---

# 領収書スキャンデータ読取り（OCR Stage）

スキャン済み領収書のPDF・画像ファイルを読み取り、パイプライン用の構造化JSONを生成する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 処理手順

### 1. ソースファイルの探索

`years/{year_label}/sources/receipts/` 配下のPDF・画像ファイルを一覧取得する。
既にバッチJSONが存在する場合は、未処理ファイルのみを対象とする。

### 2. ファイル読取り

各ファイルを Read ツールで読み取り、以下の情報を抽出する：

| フィールド | 説明 | 必須 |
|-----------|------|------|
| `id` | 領収書番号（領収書に印字された番号）| Yes |
| `date` | 診療日・支払日（YYYY-MM-DD形式） | Yes |
| `patient` | 患者名 | Yes |
| `facility` | 医療機関名 | Yes |
| `department` | 診療科 | No |
| `insurance_type` | 保険種別（社保/国保/自費/国民年金/国民健康保険） | Yes |
| `copay_rate` | 負担割合（%） | Yes |
| `insurance_amount` | 保険診療費・窓口負担額（円） | Yes |
| `out_of_pocket` | 保険外自費（円） | No |
| `out_of_pocket_detail` | 自費内訳（オブジェクト） | No |
| `meal_cost` | 食事療養費（円） | No |
| `total` | 合計支払額（円） | Yes |
| `receipt_type` | 種別: hospital/pharmacy/dental/pension_bill/insurance_bill | Yes |
| `category` | 分類: medical/pharmacy/dental/pension/health_insurance/other | Yes |
| `notes` | 備考（特記事項、不鮮明箇所の注記等） | No |

### 3. 読取りルール

- **病院領収書**: 保険点数×単価（通常10円）で計算された金額と、負担割合から窓口負担額を読み取る
- **調剤薬局**: 調剤報酬点数と薬剤料を読み取る
- **国民年金納付書**: 対象期間、基礎年金番号、納付額を読み取る
- **国保税領収書**: 期別、通知書番号、納付額を読み取る
- **不鮮明な箇所**: `notes` に「不鮮明」と記載し、読み取れた範囲で最善の推定値を入力
- **金額不明の場合**: 0 を入力し `notes` に理由を記載

### 4. バッチ分割

複数のスキャンPDFに含まれる領収書をバッチ単位で分割する：
- 1つのスキャンPDF = 1バッチ（`batch_NN.json`）
- または月単位でバッチ分割（領収書が多い場合）

### 5. 出力

`years/{year_label}/data/batches/batch_NN.json` に出力する。

出力例は [templates/receipt-schema.json](templates/receipt-schema.json) を参照。

### 6. サマリー報告

処理完了後、以下を報告する：
- 処理ファイル数
- 抽出レコード数
- 読取り不鮮明・要確認の件数
- バッチファイル一覧

## 重要な注意

- 個人情報（氏名、住所、保険番号等）は正確に読み取るが、セキュリティに注意すること
- 金額は1円単位で正確に読み取ること（四捨五入しない）
- 領収書の種類（病院/薬局/年金/国保）を正確に判別すること
- 1ファイルに複数の領収書が含まれる場合は、それぞれ別レコードとして出力する
