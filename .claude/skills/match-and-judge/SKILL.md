---
name: match-and-judge
description: |
  領収書×マイナポータル突合・控除判定（Stage 2）。
  「突合して」「控除判定して」「マイナポータルと照合して」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Bash, Glob, Grep
argument-hint: "[year_label]"
---

# 突合・控除判定（Stage 2）

receipts.json と mynaportal.json を突合し、各項目に控除判定を付与する。

## 対象年度

年度ラベル: `$ARGUMENTS` （例: `2025_R7`）

## 実行

```bash
python3 -m src.pipeline $ARGUMENTS --stage 2
```

## 処理内容

1. `receipts.json` と `mynaportal.json` を読み込み
2. (患者名, 年月, 施設名) をキーに突合
3. 突合ステータス付与: matched / receipt_only / notification_only / partial
4. 控除判定: deductible / not_deductible / conditional / mynaportal_covered
5. 医療費集計フォーム出力対象フラグ（`include_in_xlsx`）設定

## 判定ルール

- マイナポータル通知でカバーされる分は `mynaportal_covered`（xlsxには非記載）
- 保険外自費で医療行為に該当するものは `deductible`
- 国民年金・国保は `social_insurance`（医療費控除ではなく社会保険料控除）
- 美容目的・予防接種等は `not_deductible`

## 出力

- `years/{year_label}/data/match_results.json`
