"""
レポート生成

1. output/judgment_report.md - 全件の判定根拠一覧
2. output/tax_summary.md     - 確定申告全体サマリー

患者名・家族構成は mynaportal.json から動的に取得する。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_data(data_dir: Path):
    match_data = json.loads((data_dir / "match_results.json").read_text("utf-8"))
    mynaportal = json.loads((data_dir / "mynaportal.json").read_text("utf-8"))
    return match_data, mynaportal


def load_misc_income(data_dir: Path) -> dict | None:
    """雑所得データを読み込む。ファイルがなければ None。"""
    path = data_dir / "misc_income.json"
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None


def load_year_config(data_dir: Path) -> dict:
    """年度設定を読み込む。"""
    config_path = data_dir / "year_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text("utf-8"))
    return {"excluded_patients": [], "excluded_patient_reason": ""}


def get_patient_info(mynaportal: dict, year_config: dict) -> tuple[dict, dict]:
    """マイナポータルから患者情報を取得。

    Returns:
        (included_patients, excluded_patients): それぞれ {氏名: 窓口負担相当額} のdict
    """
    excluded_names = set(year_config.get("excluded_patients", []))
    included = {}
    excluded = {}
    for key, value in mynaportal.items():
        if isinstance(value, dict) and "明細" in value:
            full_name = value["氏名"]
            copay = value["合計"]["窓口負担相当額"]
            if key in excluded_names:
                excluded[full_name] = copay
            else:
                included[full_name] = copay
    return included, excluded


# ── 判定根拠レポート ───────────────────────────────────────

def generate_judgment_report(match_data: dict, output_dir: Path,
                             year_label: str = "") -> None:
    results = match_data["results"]

    parts = year_label.split("_") if year_label else []
    era = parts[1] if len(parts) >= 2 else ""
    fiscal_year = parts[0] if len(parts) >= 1 else ""
    title_year = f"令和{era[1:]}年（{fiscal_year}年）分" if era else year_label

    lines = [
        "# 判定根拠レポート",
        "",
        f"生成日: {date.today().isoformat()}",
        f"対象年度: {title_year}",
        f"総件数: {len(results)}件",
        "",
    ]

    # 判定別に分類
    by_judgment = {}
    for r in results:
        j = r["judgment"]
        by_judgment.setdefault(j, []).append(r)

    judgment_labels = {
        "mynaportal_covered": "マイナポータル連携で処理",
        "deductible": "控除対象（集計フォーム/社会保険料）",
        "not_deductible": "控除対象外",
        "conditional": "要確認",
    }

    for j_key, label in judgment_labels.items():
        items = by_judgment.get(j_key, [])
        if not items:
            continue

        lines.append(f"## {label}（{len(items)}件）")
        lines.append("")

        for r in items:
            rid = r.get("receipt_id") or "(通知のみ)"
            patient = r["patient"]
            facility = r["facility"]
            ym = r.get("year_month", "")
            receipt_date = r.get("date", ym)

            lines.append(f"### {rid} - {patient} / {facility}")
            lines.append(f"- 日付: {receipt_date}")
            lines.append(f"- 突合状態: {r['match_status']}")

            if "receipt_total" in r:
                lines.append(f"- 領収書合計: {r['receipt_total']:,}円")
            if "receipt_insurance_amount" in r:
                lines.append(f"- 保険診療窓口負担: {r['receipt_insurance_amount']:,}円")
            if r.get("receipt_out_of_pocket", 0) > 0:
                lines.append(f"- 保険適用外: {r['receipt_out_of_pocket']:,}円")
                if r.get("out_of_pocket_detail"):
                    for item, amt in r["out_of_pocket_detail"].items():
                        lines.append(f"  - {item}: {amt:,}円")
            if "portal_copay" in r:
                lines.append(f"- マイナポータル窓口負担: {r['portal_copay']:,}円")
            if "amount_diff" in r and r["amount_diff"] > 0:
                lines.append(f"- 金額差異: {r['amount_diff']:,}円")

            lines.append(f"- **判定: {r['judgment']}**")
            lines.append(f"- 根拠: {r['judgment_reason']}")

            if r.get("tax_answer_ref"):
                lines.append(f"- 参照: 国税庁タックスアンサー {r['tax_answer_ref']}")

            if r.get("deductible_amount", 0) > 0:
                lines.append(f"- 控除対象額: {r['deductible_amount']:,}円")

            if "oop_judgment" in r:
                oop = r["oop_judgment"]
                lines.append(f"- 保険適用外判定（計{oop['total']:,}円 → 控除対象{oop['deductible_total']:,}円）:")
                for item in oop["items"]:
                    lines.append(f"  - {item['item']}: {item['amount']:,}円 → {item['judgment']}（{item['reason']}）")

            lines.append("")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "judgment_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"判定根拠レポートを {path} に出力しました")


# ── 確定申告サマリー ───────────────────────────────────────

def generate_tax_summary(match_data: dict, mynaportal: dict,
                         data_dir: Path = None, output_dir: Path = None,
                         year_label: str = "") -> None:
    if data_dir is None:
        data_dir = BASE / "data"
    if output_dir is None:
        output_dir = BASE / "output"

    year_config = load_year_config(data_dir)
    summary = match_data["summary"]
    results = match_data["results"]

    parts = year_label.split("_") if year_label else []
    era = parts[1] if len(parts) >= 2 else ""
    fiscal_year = parts[0] if len(parts) >= 1 else ""
    title_year = f"令和{era[1:]}年分" if era else year_label

    # マイナポータル合計（除外患者を除く）
    included_patients, excluded_patients = get_patient_info(mynaportal, year_config)
    portal_medical_total = sum(included_patients.values())

    # 集計フォーム分（include_in_xlsx の項目 + OOP控除対象）
    xlsx_total = summary["medical_expense"]["xlsx_total"]
    oop_total = summary["medical_expense"].get("oop_deductible_total", 0)
    form_total = xlsx_total + oop_total

    # 補填される金額
    compensation_total = summary["medical_expense"].get("compensation_total", 0)

    # 医療費控除合計
    medical_total = portal_medical_total + form_total - compensation_total

    # 社会保険料
    pension = summary["social_insurance"]["pension"]
    health_ins = summary["social_insurance"]["health_insurance"]
    social_total = pension + health_ins

    # 医療費控除の計算（10万円 or 所得5%の少ない方を差し引く）
    medical_threshold = 100_000
    medical_deduction = max(0, medical_total - medical_threshold)

    lines = [
        f"# {title_year} 確定申告サマリー",
        "",
        f"生成日: {date.today().isoformat()}",
        "",
        "---",
        "",
        "## 1. 医療費控除",
        "",
        "### マイナポータル連携分（e-Tax自動読込）",
    ]

    for name, copay in included_patients.items():
        lines.append(f"- {name}: {copay:,}円")
    lines.append(f"- **小計: {portal_medical_total:,}円**")
    lines.append("")

    # 補填される金額の表示
    compensation_items = summary["medical_expense"].get("compensation_items", [])
    if compensation_items:
        lines.append("### 補填される金額（民間保険給付金等）")
        for comp in compensation_items:
            lines.append(f"- {comp['source']}: -{comp['amount']:,}円（対象: {comp['target_date']} {comp['receipt_id']}）")
        lines.append(f"- **小計: -{compensation_total:,}円**")
        lines.append("")

    lines.append("### 医療費集計フォーム分（手入力/読込）")

    # xlsx と同じグループ化ロジックを使用
    from src.generate_xlsx import collect_xlsx_rows
    form_rows = collect_xlsx_rows(results)

    if form_rows:
        for row in form_rows:
            lines.append(f"- {row['patient']} / {row['facility']}: {row['amount']:,}円")
        lines.append(f"- **小計: {form_total:,}円**")
    else:
        lines.append("- （該当なし — 全てマイナポータル連携で処理済み）")

    lines.extend([
        "",
        "### 医療費控除の計算",
        f"- 医療費合計: {medical_total:,}円",
        f"- 足切り額: {medical_threshold:,}円",
        f"- **医療費控除額: {medical_deduction:,}円**",
        "",
    ])

    # 除外患者に関する注記
    if excluded_patients:
        excluded_reason = year_config.get(
            "excluded_patient_reason",
            "控除対象外としています"
        )
        for name, copay in excluded_patients.items():
            lines.append(
                f"> 注: {name}の医療費（マイナポータル窓口負担{copay:,}円）は"
            )
            lines.append(f"> {excluded_reason}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 2. 社会保険料控除",
        "",
    ])

    si_items = summary["social_insurance"]["items"]
    for item in si_items:
        notes = f"（{item['notes']}）" if item.get("notes") else ""
        lines.append(f"- {item['type']}: {item['amount']:,}円{notes}")

    lines.extend([
        f"- **社会保険料控除合計: {social_total:,}円**",
        "",
        "---",
        "",
    ])

    # ── 雑所得セクション ──
    section_num = 3
    misc = load_misc_income(data_dir)
    if misc:
        incomes = misc.get("income", [])
        expenses = misc.get("expenses", [])
        total_income = sum(i["amount"] for i in incomes)
        total_withholding = sum(i.get("withholding", 0) for i in incomes)
        total_expense = sum(e.get("deductible", 0) for e in expenses)
        misc_income_net = total_income - total_expense

        lines.extend([
            f"## {section_num}. 雑所得",
            "",
            "### 収入",
            "",
            "| 支払元 | 種別 | 収入金額 | 源泉徴収税額 | 備考 |",
            "|--------|------|----------|-------------|------|",
        ])
        for i in incomes:
            notes = i.get("notes", "")
            lines.append(
                f"| {i['payer']} | {i['income_type']} | {i['amount']:,}円 "
                f"| {i.get('withholding', 0):,}円 | {notes} |"
            )
        lines.append(f"| **合計** | | **{total_income:,}円** | **{total_withholding:,}円** | |")
        lines.append("")

        if expenses:
            lines.extend([
                "### 必要経費",
                "",
                "| 項目 | 金額(税込) | 按分率 | 経費計上額 | 備考 |",
                "|------|-----------|--------|----------|------|",
            ])
            for e in expenses:
                amt_str = f"{e['amount_jpy']:,}円"
                if e.get("amount_usd"):
                    amt_str += f" (${e['amount_usd']:.2f})"
                rate = f"{e['allocation_rate']:.0%}" if e.get("allocation_rate") else "-"
                notes = e.get("notes", "")
                lines.append(
                    f"| {e['item']} | {amt_str} | {rate} "
                    f"| {e.get('deductible', 0):,}円 | {notes} |"
                )
            lines.append(f"| **合計** | | | **{total_expense:,}円** | |")
            lines.append("")

        lines.extend([
            "### 雑所得の計算",
            f"- 収入金額: {total_income:,}円",
            f"- 必要経費: {total_expense:,}円",
            f"- **雑所得: {misc_income_net:,}円**",
            f"- 源泉徴収済み: {total_withholding:,}円",
            "",
        ])

        if misc.get("exchange_rate_source"):
            lines.append(f"> 為替レート: {misc['exchange_rate_source']}")
            if misc.get("exchange_rate_date"):
                lines.append(f"> 基準日: {misc['exchange_rate_date']}")
            lines.append("")

        lines.extend(["---", ""])
        section_num += 1

    lines.extend([
        f"## {section_num}. 要確認事項",
        "",
    ])

    conditional = summary["conditional_items"]
    if conditional:
        for item in conditional:
            lines.append(f"- [{item['receipt_id']}] {item['patient']} / {item['facility']}: {item['reason']}")
    else:
        lines.append("- （要確認事項なし）")

    section_num += 1
    etax_steps = [
        "1. **e-Taxにログイン** → 確定申告書等作成コーナー",
        "2. **マイナポータル連携** → 医療費通知データを自動取得",
        "3. **医療費集計フォーム読込** → `output/medical_expense_form.xlsx` をアップロード",
        "4. **社会保険料控除** → 国民年金・国保税の金額を手入力",
    ]
    if misc:
        etax_steps.append("5. **雑所得** → 収入金額と経費を入力")
        etax_steps.append("6. **確認・送信**")
    else:
        etax_steps.append("5. **確認・送信**")

    lines.extend([
        "",
        "---",
        "",
        f"## {section_num}. 申告手順",
        "",
    ])
    lines.extend(etax_steps)

    section_num += 1
    lines.extend([
        "",
        "---",
        "",
        f"## {section_num}. 突合統計",
        "",
        f"- 総処理件数: {summary['total_items']}",
        f"- マイナポータル突合: {summary['matched']}件",
        f"- 領収書のみ: {summary['receipt_only']}件",
        f"- 通知のみ: {summary['notification_only']}件",
    ])

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "tax_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"確定申告サマリーを {path} に出力しました")


def main():
    import sys
    if len(sys.argv) >= 2:
        year_dir = BASE / "years" / sys.argv[1]
        data_dir = year_dir / "data"
        output_dir = year_dir / "output"
    else:
        data_dir = BASE / "data"
        output_dir = BASE / "output"
    match_data, mynaportal = load_data(data_dir)
    year_label = sys.argv[1] if len(sys.argv) >= 2 else ""
    generate_judgment_report(match_data, output_dir, year_label)
    generate_tax_summary(match_data, mynaportal, data_dir, output_dir, year_label)


if __name__ == "__main__":
    main()
