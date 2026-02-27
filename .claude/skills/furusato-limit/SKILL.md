---
name: furusato-limit
description: |
  ふるさと納税の控除上限額シミュレーター。
  給与所得・雑所得・各種控除データから上限額を算出し、計算過程を解説するレポートを生成する。
  「ふるさと納税の上限」「寄附枠を確認」「furusato limit」などの指示で使用。
user-invocable: true
disable-model-invocation: false
allowed-tools: Read, Write, Edit, Bash, Glob, AskUserQuestion
argument-hint: "[year_label]"
---

# ふるさと納税 控除上限額シミュレーター

ふるさと納税の控除上限額を計算し、計算過程を教育的に解説するレポートを出力する。

## 対象年度

年度ラベル: `$ARGUMENTS`（例: `2025_R7`）。省略時はユーザーに確認する。

## データファイル

- `years/{year_label}/data/salary_income.json` — 源泉徴収票データ（事後確認モード）
- `years/{year_label}/data/insurance_deductions.json` — 各種控除データ
- `years/{year_label}/data/match_results.json` — 医療費控除データ
- `years/{year_label}/data/misc_income.json` — 雑所得データ

## モード自動判定

### 事後確認モード（salary_income.json あり）

源泉徴収票の金額をベースに正確な上限額を計算する。

1. `salary_income.json` を読み込む
2. 二重計上チェック: 源泉徴収票の生命保険料控除・地震保険料控除は年末調整済みなので、
   `insurance_deductions.json` からは**追加の社会保険料**（国年・国保）と**ふるさと納税実績**のみ取得
3. 計算実行:
   ```bash
   python3 -c "
   from pathlib import Path
   from src.furusato_limit import run
   run(Path('years/{year_label}'), '{year_label}')
   "
   ```
4. `output/furusato_limit_report.md` の内容を表示する

### 事前シミュレーションモード（salary_income.json なし）

ユーザーに対話的に質問して概算する。

1. ユーザーに以下を質問する:
   - **給与収入（見込み額 or 前年参考額）**: 源泉徴収票の「支払金額」に相当する年収額
   - **源泉徴収票の社会保険料等の金額**: 共済組合・厚生年金・健康保険の合計（前年参考値でも可）
   - **配偶者控除の有無**: 配偶者の年間所得が48万円以下なら38万円
   - **扶養控除の有無**: 16歳以上の扶養親族の人数と種別

2. 概算である旨を明示して計算:
   ```bash
   python3 -c "
   from pathlib import Path
   from src.furusato_limit import run
   run(Path('years/{year_label}'), '{year_label}', salary={入力額})
   "
   ```
   注: シミュレーションモードでは源泉徴収票の社保を別途指定する必要がある場合、
   `calculate_furusato_limit()` を直接呼び出す。

3. レポートを表示し、「概算のため±1〜2万円の誤差がありえます」と付記する

## salary_income.json スキーマ

源泉徴収票から転記するデータ:

```json
{
  "対象年分": "令和7年（2025年）",
  "支払者": "（勤務先名）",
  "支払金額": 0,
  "給与所得控除後の金額": 0,
  "所得控除の額の合計額": 0,
  "源泉徴収税額": 0,
  "社会保険料等の金額": 0,
  "生命保険料の控除額": 0,
  "地震保険料の控除額": 0,
  "住宅借入金等特別控除の額": 0,
  "配偶者控除等の額": 0,
  "扶養控除の額": 0,
  "備考": ""
}
```

## 出力

- `years/{year_label}/output/furusato_limit_report.md`
  - 計算過程をステップごとに解説
  - 所得税と住民税の控除額差異
  - 3段階控除（所得税/住民税基本/住民税特例）の内訳
  - 寄附状況サマリー（上限額・寄附済み・残枠）

## 二重計上防止

`insurance_deductions.json` の「備考_年末調整」に以下の記載あり:
> 「明治安田の団体保険は共済組合経由のため、源泉徴収票の生命保険料控除欄に既に反映されている可能性あり」

- **事後確認モード**: 源泉徴収票の控除額をそのまま使用（年末調整処理済み）
- **事前シミュレーション**: `insurance_deductions.json` から保険料原価で再計算
