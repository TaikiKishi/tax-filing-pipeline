"""
ふるさと納税 控除上限額シミュレーター

給与所得・雑所得・各種控除データから、ふるさと納税の控除上限額を算出する。
計算過程を教育的に解説するレポートを生成する。

2つのモード:
  - 事後確認モード: salary_income.json がある場合（源泉徴収票ベース）
  - 事前シミュレーション: salary_income.json がない場合（概算）

出力:
    - furusato_limit_report.md — 上限額レポート（計算過程付き）

参照:
    - 総務省「ふるさと納税のしくみ」
    - https://www.soumu.go.jp/main_sosiki/jichi_zeisei/czaisei/czaisei_seido/furusato/mechanism/deduction.html
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path


# ── 税率テーブル（令和2年分以降） ────────────────────────


def salary_income_deduction(salary: int) -> int:
    """給与所得控除額（令和2年分以降）。

    参照: No.1410 給与所得控除
    https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm
    """
    if salary <= 1_625_000:
        return 550_000
    elif salary <= 1_800_000:
        return salary * 40 // 100 - 100_000
    elif salary <= 3_600_000:
        return salary * 30 // 100 + 80_000
    elif salary <= 6_600_000:
        return salary * 20 // 100 + 440_000
    elif salary <= 8_500_000:
        return salary * 10 // 100 + 1_100_000
    else:
        return 1_950_000


def income_tax_rate(taxable_income: int) -> tuple[float, int]:
    """所得税の税率と控除額を返す → (rate, deduction)。

    参照: No.2260 所得税の税率
    https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/2260.htm
    """
    if taxable_income <= 1_950_000:
        return (0.05, 0)
    elif taxable_income <= 3_300_000:
        return (0.10, 97_500)
    elif taxable_income <= 6_950_000:
        return (0.20, 427_500)
    elif taxable_income <= 9_000_000:
        return (0.23, 636_000)
    elif taxable_income <= 18_000_000:
        return (0.33, 1_536_000)
    elif taxable_income <= 40_000_000:
        return (0.40, 2_796_000)
    else:
        return (0.45, 4_796_000)


def basic_deduction(total_income: int) -> int:
    """基礎控除額（所得税用）。

    参照: No.1199 基礎控除
    """
    if total_income <= 24_000_000:
        return 480_000
    elif total_income <= 24_500_000:
        return 320_000
    elif total_income <= 25_000_000:
        return 160_000
    else:
        return 0


def basic_deduction_residence(total_income: int) -> int:
    """基礎控除額（住民税用）— 所得税と金額が異なる。"""
    if total_income <= 24_000_000:
        return 430_000
    elif total_income <= 24_500_000:
        return 290_000
    elif total_income <= 25_000_000:
        return 150_000
    else:
        return 0


def life_insurance_deduction_income_tax(general: int, medical: int, pension: int) -> int:
    """新制度・生命保険料控除の所得税用計算。

    各区分ごとに上限4万円、合計上限12万円。
    参照: No.1140 生命保険料控除
    """
    def calc_one(premium: int) -> int:
        if premium <= 20_000:
            return premium
        elif premium <= 40_000:
            return premium // 2 + 10_000
        elif premium <= 80_000:
            return premium // 4 + 20_000
        else:
            return 40_000

    total = calc_one(general) + calc_one(medical) + calc_one(pension)
    return min(total, 120_000)


def life_insurance_deduction_residence_tax(general: int, medical: int, pension: int) -> int:
    """新制度・生命保険料控除の住民税用計算。

    各区分ごとに上限2.8万円、合計上限7万円。
    """
    def calc_one(premium: int) -> int:
        if premium <= 12_000:
            return premium
        elif premium <= 32_000:
            return premium // 2 + 6_000
        elif premium <= 56_000:
            return premium // 4 + 14_000
        else:
            return 28_000

    total = calc_one(general) + calc_one(medical) + calc_one(pension)
    return min(total, 70_000)


# ── 結果データ構造 ───────────────────────────────────────


@dataclass
class FurusatoLimitResult:
    """ふるさと納税上限額の計算結果。"""
    mode: str = ""                      # "post_confirmation" or "simulation"

    # 所得
    salary: int = 0                     # 給与収入
    salary_income_deduction: int = 0    # 給与所得控除額
    salary_income: int = 0              # 給与所得
    misc_income_net: int = 0            # 雑所得（収入-経費）
    total_income: int = 0               # 合計所得金額

    # 所得税用控除
    it_basic: int = 0                   # 基礎控除（所得税）
    it_social_insurance: int = 0        # 社会保険料控除
    it_life_insurance: int = 0          # 生命保険料控除（所得税）
    it_earthquake_insurance: int = 0    # 地震保険料控除
    it_medical_expense: int = 0         # 医療費控除
    it_spouse: int = 0                  # 配偶者控除
    it_dependent: int = 0               # 扶養控除
    it_total_deduction: int = 0         # 所得控除合計（所得税）
    it_taxable_income: int = 0          # 課税所得（所得税）
    it_rate: float = 0.0                # 所得税率
    it_rate_deduction: int = 0          # 税率控除額

    # 住民税用控除
    rt_basic: int = 0                   # 基礎控除（住民税）
    rt_social_insurance: int = 0        # 社会保険料控除（所得税と同額）
    rt_life_insurance: int = 0          # 生命保険料控除（住民税）
    rt_earthquake_insurance: int = 0    # 地震保険料控除（所得税と同額）
    rt_medical_expense: int = 0         # 医療費控除（所得税と同額）
    rt_spouse: int = 0                  # 配偶者控除（住民税）
    rt_dependent: int = 0               # 扶養控除（住民税）
    rt_total_deduction: int = 0         # 所得控除合計（住民税）
    rt_taxable_income: int = 0          # 課税所得（住民税）
    rt_income_rate_amount: int = 0      # 住民税所得割額

    # 調整控除
    adjustment_deduction: int = 2_500   # 調整控除（基本）

    # 住宅ローン控除
    housing_loan_credit: int = 0

    # ふるさと納税
    furusato_limit: int = 0             # 上限額
    furusato_already: int = 0           # 寄附済み額
    furusato_remaining: int = 0         # 残枠

    # 内訳（逆算確認用）
    breakdown_income_tax: int = 0       # ①所得税からの控除
    breakdown_residence_basic: int = 0  # ②住民税基本分
    breakdown_residence_special: int = 0  # ③住民税特例分


# ── データ読み込み ───────────────────────────────────────


def load_json_safe(path: Path):
    """JSONファイルを安全に読み込む。存在しなければNoneを返す。"""
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None


def load_deduction_data(data_dir: Path) -> dict:
    """各種控除データを読み込み、計算に必要な値を返す。"""
    result = {
        "extra_social_insurance": 0,     # 確定申告で追加する社保（国年+国保）
        "life_insurance_general": 0,     # 一般生命保険料（申告額合計）
        "life_insurance_medical": 0,     # 介護医療保険料（申告額合計）
        "life_insurance_pension": 0,     # 個人年金保険料（申告額合計）
        "earthquake_insurance": 0,       # 地震保険料
        "medical_expense_deduction": 0,  # 医療費控除額
        "furusato_already": 0,           # ふるさと納税既寄附額
    }

    # insurance_deductions.json
    ins = load_json_safe(data_dir / "insurance_deductions.json")
    if ins:
        # 社会保険料（確定申告で追加分 = 国民年金 + 国民健康保険）
        social = ins.get("社会保険料控除", {})
        result["extra_social_insurance"] = social.get("合計", 0)

        # 生命保険料（申告額ベース）
        life = ins.get("生命保険料控除", {})
        for key, val in life.items():
            if key.startswith("備考"):
                continue
            if not isinstance(val, dict) or "合計_申告額" not in val:
                continue
            if "一般生命保険料" in key:
                result["life_insurance_general"] += val["合計_申告額"]
            elif "介護医療保険料" in key:
                result["life_insurance_medical"] += val["合計_申告額"]
            elif "個人年金保険料" in key:
                result["life_insurance_pension"] += val["合計_申告額"]

        # 地震保険料
        earthquake = ins.get("地震保険料控除", {})
        result["earthquake_insurance"] = earthquake.get("地震保険料_年額", 0)

        # ふるさと納税
        furusato = ins.get("ふるさと納税", {})
        result["furusato_already"] = furusato.get("合計", 0)

    # match_results.json → 医療費控除
    match_data = load_json_safe(data_dir / "match_results.json")
    if match_data:
        entries = match_data.get("results", [])
        # 控除対象の医療費合計
        medical_total = 0
        reimbursement_total = 0
        for e in entries:
            if e.get("judgment") in ("deductible", "mynaportal_covered"):
                medical_total += e.get("deductible_amount", 0)
                reimbursement_total += e.get("reimbursement", 0)
        # 医療費控除 = 医療費合計 - 補填額 - 10万円（足切り）
        net_medical = medical_total - reimbursement_total
        result["medical_expense_deduction"] = max(0, net_medical - 100_000)

    # misc_income.json → 雑所得
    misc = load_json_safe(data_dir / "misc_income.json")
    if misc:
        incomes = misc.get("income", [])
        expenses = misc.get("expenses", [])
        total_income = sum(i.get("amount", 0) for i in incomes)
        total_expense = sum(e.get("deductible", 0) for e in expenses)
        result["misc_income_net"] = max(0, total_income - total_expense)
        result["misc_income_gross"] = total_income
        result["misc_expense"] = total_expense

    return result


# ── コア計算 ─────────────────────────────────────────


def calculate_furusato_limit(
    salary: int,
    salary_social_insurance: int,
    extra_social_insurance: int,
    life_insurance_deduction_it: int,
    life_insurance_deduction_rt: int,
    earthquake_insurance_deduction: int,
    medical_expense_deduction: int,
    misc_income_net: int,
    spouse_deduction: int = 0,
    dependent_deduction: int = 0,
    housing_loan_credit: int = 0,
    furusato_already: int = 0,
    mode: str = "post_confirmation",
) -> FurusatoLimitResult:
    """ふるさと納税の控除上限額を計算する。"""
    r = FurusatoLimitResult(mode=mode)

    # ── 1. 所得の計算 ──
    r.salary = salary
    r.salary_income_deduction = salary_income_deduction(salary)
    r.salary_income = salary - r.salary_income_deduction
    r.misc_income_net = misc_income_net
    r.total_income = r.salary_income + r.misc_income_net

    # ── 2. 所得控除（所得税用） ──
    r.it_basic = basic_deduction(r.total_income)
    r.it_social_insurance = salary_social_insurance + extra_social_insurance
    r.it_life_insurance = life_insurance_deduction_it
    r.it_earthquake_insurance = earthquake_insurance_deduction
    r.it_medical_expense = medical_expense_deduction
    r.it_spouse = spouse_deduction
    r.it_dependent = dependent_deduction

    r.it_total_deduction = (
        r.it_basic
        + r.it_social_insurance
        + r.it_life_insurance
        + r.it_earthquake_insurance
        + r.it_medical_expense
        + r.it_spouse
        + r.it_dependent
    )

    # 課税所得（千円未満切捨て）
    r.it_taxable_income = max(0, r.total_income - r.it_total_deduction)
    r.it_taxable_income = (r.it_taxable_income // 1000) * 1000
    r.it_rate, r.it_rate_deduction = income_tax_rate(r.it_taxable_income)

    # ── 3. 所得控除（住民税用） ──
    r.rt_basic = basic_deduction_residence(r.total_income)
    r.rt_social_insurance = r.it_social_insurance  # 同額
    r.rt_life_insurance = life_insurance_deduction_rt
    r.rt_earthquake_insurance = r.it_earthquake_insurance  # 同額
    r.rt_medical_expense = r.it_medical_expense  # 同額
    # 住民税の配偶者控除は所得税より5万円低い（一般）
    r.rt_spouse = max(0, spouse_deduction - 50_000) if spouse_deduction > 0 else 0
    r.rt_dependent = max(0, dependent_deduction - 50_000) if dependent_deduction > 0 else 0

    r.rt_total_deduction = (
        r.rt_basic
        + r.rt_social_insurance
        + r.rt_life_insurance
        + r.rt_earthquake_insurance
        + r.rt_medical_expense
        + r.rt_spouse
        + r.rt_dependent
    )

    # 住民税課税所得（千円未満切捨て）
    r.rt_taxable_income = max(0, r.total_income - r.rt_total_deduction)
    r.rt_taxable_income = (r.rt_taxable_income // 1000) * 1000

    # ── 4. 住民税所得割額 ──
    r.adjustment_deduction = 2_500  # 基本的な調整控除
    r.rt_income_rate_amount = max(0,
        int(r.rt_taxable_income * 0.10) - r.adjustment_deduction
    )

    # 住宅ローン控除の住民税影響
    r.housing_loan_credit = housing_loan_credit
    if housing_loan_credit > 0:
        r.rt_income_rate_amount = max(0,
            r.rt_income_rate_amount - housing_loan_credit
        )

    # ── 5. ふるさと納税上限額 ──
    # 上限額 = 住民税所得割額 × 20% ÷ (1 - 0.10 - 所得税率 × 1.021) + 2,000
    denominator = 1.0 - 0.10 - r.it_rate * 1.021
    if denominator > 0:
        r.furusato_limit = int(
            r.rt_income_rate_amount * 0.20 / denominator + 2000
        )
    else:
        r.furusato_limit = 0

    r.furusato_already = furusato_already
    r.furusato_remaining = max(0, r.furusato_limit - furusato_already)

    # ── 控除3段階の内訳（上限額で逆算確認） ──
    donation = r.furusato_limit
    if donation > 2000:
        net = donation - 2000
        r.breakdown_income_tax = int(net * r.it_rate * 1.021)
        r.breakdown_residence_basic = int(net * 0.10)
        r.breakdown_residence_special = int(
            net * (1.0 - 0.10 - r.it_rate * 1.021)
        )

    return r


# ── レポート生成 ─────────────────────────────────────────


def generate_report(result: FurusatoLimitResult, year_label: str) -> str:
    """計算過程を解説するMarkdownレポートを生成する。"""
    parts = year_label.split("_")
    fiscal_year = parts[0] if len(parts) >= 1 else year_label
    era = parts[1] if len(parts) >= 2 else ""

    mode_label = "事後確認（源泉徴収票ベース）" if result.mode == "post_confirmation" else "事前シミュレーション（概算）"
    r = result

    lines = []
    lines.append(f"# ふるさと納税 控除上限額レポート（{era}・{fiscal_year}年分）\n")
    lines.append(f"モード: **{mode_label}**\n")

    if result.mode == "simulation":
        lines.append("> このレポートは概算値です。源泉徴収票入手後に再計算してください。\n")

    # ── 1. 所得の計算 ──
    lines.append("---\n")
    lines.append("## 1. 所得の計算\n")
    lines.append("| 項目 | 金額 |")
    lines.append("|------|-----:|")
    lines.append(f"| 給与収入（支払金額） | {r.salary:,} 円 |")
    lines.append(f"| 給与所得控除 | -{r.salary_income_deduction:,} 円 |")
    lines.append(f"| **給与所得** | **{r.salary_income:,} 円** |")
    if r.misc_income_net > 0:
        lines.append(f"| 雑所得（収入-経費） | {r.misc_income_net:,} 円 |")
    lines.append(f"| **合計所得金額** | **{r.total_income:,} 円** |")
    lines.append("")

    # ── 2. 所得控除の内訳 ──
    lines.append("## 2. 所得控除の内訳\n")
    lines.append("所得税と住民税では控除額が異なる項目があります。\n")
    lines.append("| 控除項目 | 所得税 | 住民税 | 差異の理由 |")
    lines.append("|----------|-------:|-------:|-----------|")
    lines.append(f"| 基礎控除 | {r.it_basic:,} | {r.rt_basic:,} | 所得税48万/住民税43万 |")
    lines.append(f"| 社会保険料控除 | {r.it_social_insurance:,} | {r.rt_social_insurance:,} | 同額 |")

    if r.it_life_insurance > 0 or r.rt_life_insurance > 0:
        lines.append(f"| 生命保険料控除 | {r.it_life_insurance:,} | {r.rt_life_insurance:,} | 上限: 所得税12万/住民税7万 |")

    if r.it_earthquake_insurance > 0:
        lines.append(f"| 地震保険料控除 | {r.it_earthquake_insurance:,} | {r.rt_earthquake_insurance:,} | 同額 |")

    if r.it_medical_expense > 0:
        lines.append(f"| 医療費控除 | {r.it_medical_expense:,} | {r.rt_medical_expense:,} | 同額 |")

    if r.it_spouse > 0:
        lines.append(f"| 配偶者控除 | {r.it_spouse:,} | {r.rt_spouse:,} | 所得税38万/住民税33万 |")

    if r.it_dependent > 0:
        lines.append(f"| 扶養控除 | {r.it_dependent:,} | {r.rt_dependent:,} | 差額あり |")

    lines.append(f"| **所得控除合計** | **{r.it_total_deduction:,}** | **{r.rt_total_deduction:,}** | |")
    lines.append("")

    # ── 3. 課税所得と所得税率 ──
    lines.append("## 3. 課税所得と所得税率\n")
    lines.append("| 項目 | 金額 |")
    lines.append("|------|-----:|")
    lines.append(f"| 合計所得金額 | {r.total_income:,} 円 |")
    lines.append(f"| 所得控除合計（所得税） | -{r.it_total_deduction:,} 円 |")
    lines.append(f"| **課税所得（所得税）** | **{r.it_taxable_income:,} 円** |")
    lines.append(f"| 適用税率 | {r.it_rate:.0%}（控除額 {r.it_rate_deduction:,}円） |")
    lines.append("")

    # ── 4. 住民税所得割額 ──
    lines.append("## 4. 住民税所得割額\n")
    lines.append("> ふるさと納税の上限額は「住民税所得割額」に基づきます。")
    lines.append("> 住民税は一律10%ですが、所得税とは控除額が異なるため別計算します。\n")
    lines.append("| 項目 | 金額 |")
    lines.append("|------|-----:|")
    lines.append(f"| 合計所得金額 | {r.total_income:,} 円 |")
    lines.append(f"| 所得控除合計（住民税） | -{r.rt_total_deduction:,} 円 |")
    lines.append(f"| 課税所得（住民税） | {r.rt_taxable_income:,} 円 |")
    lines.append(f"| 住民税率 | 10%（市民税6% + 県民税4%） |")
    lines.append(f"| 税額 | {int(r.rt_taxable_income * 0.10):,} 円 |")
    lines.append(f"| 調整控除 | -{r.adjustment_deduction:,} 円 |")
    if r.housing_loan_credit > 0:
        lines.append(f"| 住宅ローン控除 | -{r.housing_loan_credit:,} 円 |")
    lines.append(f"| **住民税所得割額** | **{r.rt_income_rate_amount:,} 円** |")
    lines.append("")

    # ── 5. 上限額の算出 ──
    lines.append("## 5. ふるさと納税 控除上限額の算出\n")
    lines.append("> ふるさと納税の控除は3段階で構成されています：")
    lines.append("> 1. **所得税からの控除**: (寄附金-2,000) x 所得税率 x 1.021（復興税含む）")
    lines.append("> 2. **住民税基本分**: (寄附金-2,000) x 10%")
    lines.append("> 3. **住民税特例分**: (寄附金-2,000) x (100%-10%-所得税率x1.021)")
    lines.append(">")
    lines.append("> 3の住民税特例分が住民税所得割額の20%を超えないように、上限額が決まります。\n")

    lines.append("**計算式:**")
    lines.append("```")
    lines.append(f"上限額 = 住民税所得割額 × 20% ÷ (1 - 10% - 所得税率 × 1.021) + 2,000円")
    lines.append(f"       = {r.rt_income_rate_amount:,} × 0.20 ÷ (1 - 0.10 - {r.it_rate} × 1.021) + 2,000")
    denominator = 1.0 - 0.10 - r.it_rate * 1.021
    lines.append(f"       = {r.rt_income_rate_amount * 0.20:,.0f} ÷ {denominator:.6f} + 2,000")
    lines.append(f"       = {r.furusato_limit:,} 円")
    lines.append("```\n")

    # 控除内訳の検算
    if r.furusato_limit > 2000:
        lines.append("**上限額での控除内訳（検算）:**\n")
        lines.append("| 控除段階 | 金額 | 説明 |")
        lines.append("|----------|-----:|------|")
        lines.append(f"| ①所得税からの控除 | {r.breakdown_income_tax:,} 円 | ({r.furusato_limit:,}-2,000) x {r.it_rate:.0%} x 1.021 |")
        lines.append(f"| ②住民税基本分 | {r.breakdown_residence_basic:,} 円 | ({r.furusato_limit:,}-2,000) x 10% |")
        lines.append(f"| ③住民税特例分 | {r.breakdown_residence_special:,} 円 | 所得割額の20%以内 |")
        total_benefit = r.breakdown_income_tax + r.breakdown_residence_basic + r.breakdown_residence_special
        lines.append(f"| **控除合計** | **{total_benefit:,} 円** | 寄附額 - 自己負担2,000円 ≒ {r.furusato_limit - 2000:,}円 |")
        lines.append("")

    # ── 6. サマリー ──
    lines.append("## 6. 寄附状況サマリー\n")
    lines.append("```")
    lines.append("┌──────────────────────────────┐")
    lines.append(f"│ 上限額:      {r.furusato_limit:>9,} 円   │")
    lines.append(f"│ 寄附済み:    {r.furusato_already:>9,} 円   │")
    lines.append(f"│ 残枠:        {r.furusato_remaining:>9,} 円   │")
    lines.append(f"│ 自己負担:        2,000 円   │")
    lines.append("└──────────────────────────────┘")
    lines.append("```\n")

    if r.furusato_already > r.furusato_limit:
        over = r.furusato_already - r.furusato_limit
        lines.append(f"**警告**: 寄附済み額が上限を **{over:,}円** 超過しています。")
        lines.append("超過分は自己負担となります。\n")
    elif r.furusato_remaining > 0:
        lines.append(f"あと **{r.furusato_remaining:,}円** の寄附枠があります。\n")
    else:
        lines.append("上限額に達しています。追加の寄附は自己負担が増加します。\n")

    # ── 7. 注意事項 ──
    lines.append("## 7. 注意事項\n")
    notes = []

    if result.mode == "simulation":
        notes.append("- この計算は **概算** です。実際の上限額は源泉徴収票の金額で確定します")
        notes.append("- 特に社会保険料は年末調整額と異なる可能性があります")

    notes.append("- 住民税は翌年度（翌年6月〜）に課税されます。上限額は当年の所得に基づく翌年度住民税で計算されます")

    if r.it_medical_expense > 0:
        notes.append(f"- 医療費控除 {r.it_medical_expense:,}円 を適用しています。医療費控除が増えると課税所得が減り、ふるさと納税の上限額も下がります")

    notes.append("- 復興特別所得税（2.1%）は2037年分まで課税されます。上限額の計算式に含まれています")
    notes.append("- 確定申告を行う場合、ワンストップ特例は適用されません。全ての寄附先を申告する必要があります")

    for note in notes:
        lines.append(note)

    return "\n".join(lines)


# ── エントリポイント ─────────────────────────────────────


def run(year_dir: Path, year_label: str, salary: int | None = None) -> FurusatoLimitResult:
    """計算を実行しレポートを出力する。

    Args:
        year_dir: 年度ディレクトリ (years/2025_R7)
        year_label: 年度ラベル (2025_R7)
        salary: 給与収入（事前シミュレーション用。Noneの場合はsalary_income.jsonを使用）

    Returns:
        FurusatoLimitResult
    """
    data_dir = year_dir / "data"
    output_dir = year_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 既存データの読み込み
    deduction_data = load_deduction_data(data_dir)

    # モード判定
    salary_data = load_json_safe(data_dir / "salary_income.json")

    if salary_data:
        # 事後確認モード（源泉徴収票ベース）
        mode = "post_confirmation"
        salary_amount = salary_data["支払金額"]

        # 源泉徴収票の社保（年末調整済み）
        salary_social_insurance = salary_data.get("社会保険料等の金額", 0)

        # 生命保険料・地震保険料: 源泉徴収票に値があれば使用（年末調整済み）
        # 値が0の場合は年末調整未処理のため、insurance_deductions.json から計算
        life_insurance_it = salary_data.get("生命保険料の控除額", 0)
        if life_insurance_it > 0:
            life_insurance_rt = min(life_insurance_it, 70_000)
        else:
            # 年末調整未処理 → 保険料原価から控除額を計算
            life_insurance_it = life_insurance_deduction_income_tax(
                deduction_data["life_insurance_general"],
                deduction_data["life_insurance_medical"],
                deduction_data["life_insurance_pension"],
            )
            life_insurance_rt = life_insurance_deduction_residence_tax(
                deduction_data["life_insurance_general"],
                deduction_data["life_insurance_medical"],
                deduction_data["life_insurance_pension"],
            )

        earthquake_insurance = salary_data.get("地震保険料の控除額", 0)
        if earthquake_insurance == 0:
            earthquake_insurance = deduction_data["earthquake_insurance"]
        spouse_deduction = salary_data.get("配偶者控除等の額", 0)
        dependent_deduction = salary_data.get("扶養控除の額", 0)
        housing_loan_credit = salary_data.get("住宅借入金等特別控除の額", 0)

        # 確定申告で追加する社保（国年+国保。年末調整で未処理分）
        extra_social = deduction_data["extra_social_insurance"]

    elif salary is not None:
        # 事前シミュレーション（給与収入を引数で指定）
        mode = "simulation"
        salary_amount = salary
        salary_social_insurance = 0  # スキル側で対話入力を期待

        # insurance_deductions.json から全項目を計算
        extra_social = deduction_data["extra_social_insurance"]
        life_insurance_it = life_insurance_deduction_income_tax(
            deduction_data["life_insurance_general"],
            deduction_data["life_insurance_medical"],
            deduction_data["life_insurance_pension"],
        )
        life_insurance_rt = life_insurance_deduction_residence_tax(
            deduction_data["life_insurance_general"],
            deduction_data["life_insurance_medical"],
            deduction_data["life_insurance_pension"],
        )
        earthquake_insurance = deduction_data["earthquake_insurance"]
        spouse_deduction = 0
        dependent_deduction = 0
        housing_loan_credit = 0
    else:
        raise ValueError(
            "salary_income.json が見つからず、salary 引数も指定されていません。"
            "スキル（/furusato-limit）経由で給与収入を指定してください。"
        )

    result = calculate_furusato_limit(
        salary=salary_amount,
        salary_social_insurance=salary_social_insurance,
        extra_social_insurance=extra_social,
        life_insurance_deduction_it=life_insurance_it,
        life_insurance_deduction_rt=life_insurance_rt,
        earthquake_insurance_deduction=earthquake_insurance,
        medical_expense_deduction=deduction_data["medical_expense_deduction"],
        misc_income_net=deduction_data.get("misc_income_net", 0),
        spouse_deduction=spouse_deduction,
        dependent_deduction=dependent_deduction,
        housing_loan_credit=housing_loan_credit,
        furusato_already=deduction_data["furusato_already"],
        mode=mode,
    )

    # レポート生成・保存
    report = generate_report(result, year_label)
    output_path = output_dir / "furusato_limit_report.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"ふるさと納税上限額レポートを {output_path} に生成しました")

    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.furusato_limit 2025_R7 [salary]")
        print("  salary: 給与収入（省略時は salary_income.json を使用）")
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent
    label = sys.argv[1]
    yr_dir = base / "years" / label
    if not yr_dir.exists():
        print(f"Error: {yr_dir} が見つかりません")
        sys.exit(1)

    sal = int(sys.argv[2]) if len(sys.argv) >= 3 else None
    run(yr_dir, label, salary=sal)
