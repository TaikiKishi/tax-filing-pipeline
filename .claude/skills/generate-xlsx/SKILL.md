---
name: generate-xlsx
description: |
  医療費集計フォーム（xlsx）生成（Stage 4）。NTA公式テンプレートにデータを記入する。
  「xlsx生成」「医療費集計フォーム作成」「エクセル出力」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob
argument-hint: "[year_label]"
---

# 医療費集計フォーム生成（Stage 4）

NTA公式テンプレート（iryouhi_form_v3.1.xlsx）にデータを記入して出力する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 4
```

## 処理内容

1. `match_results.json` から `include_in_xlsx=true` のレコードを抽出
2. (患者名, 施設名, 医療費区分) でグルーピング
3. `reimbursements.json` の補填金額をマッチング・差し引き
4. NTA公式テンプレート（`templates/iryouhi_form_v3.1.xlsx`）のB-I列、9行目以降に記入
5. シート保護を一時解除→記入→再保護

## テンプレート列マッピング

| 列 | 内容 |
|----|------|
| B | 医療を受けた人 |
| C | 病院・薬局などの名称 |
| D | 診療・治療（チェック） |
| E | 医薬品購入（チェック） |
| F | 介護保険サービス（チェック） |
| G | その他の医療費（チェック） |
| H | 支払った医療費の金額 |
| I | 補填される金額 |

## 出力

- `years/{year_label}/output/medical_expense_form.xlsx`
