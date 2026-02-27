"""
照合チェックリスト生成

全領収書の照合結果と、集計フォーム記載分については
診療内容の推定根拠・医療費控除該当理由を記載した保管用資料を生成する。

患者名・家族構成は mynaportal.json から動的に取得する。

出力: output/verification_checklist.md
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def rid_to_stored_path(receipt_id: str, manifest: dict | None) -> str:
    """receipt_id → manifest内の stored_path を返す。"""
    if manifest:
        for entry in manifest.get("files", []):
            if entry.get("receipt_id") == receipt_id:
                return entry.get("stored_path", receipt_id)
    return receipt_id


def load_data(data_dir: Path):
    match_data = json.loads((data_dir / "match_results.json").read_text("utf-8"))
    receipts = json.loads((data_dir / "receipts.json").read_text("utf-8"))
    mynaportal = json.loads((data_dir / "mynaportal.json").read_text("utf-8"))
    return match_data, receipts, mynaportal


def load_year_config(data_dir: Path) -> dict:
    config_path = data_dir / "year_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text("utf-8"))
    return {"excluded_patients": [], "excluded_patient_reason": ""}


def get_patient_keys(mynaportal: dict) -> list[str]:
    """マイナポータルデータから患者キー一覧を取得。"""
    return [k for k, v in mynaportal.items() if isinstance(v, dict) and "明細" in v]


def fmt(amount: int) -> str:
    return f"{amount:,}"


def generate_checklist(match_data: dict = None, receipts: list = None,
                       mynaportal: dict = None, output_dir: Path = None,
                       year_dir: Path = None, year_label: str = "") -> None:
    if match_data is None or receipts is None or mynaportal is None:
        data_dir = BASE / "data"
        match_data, receipts, mynaportal = load_data(data_dir)
    if output_dir is None:
        output_dir = BASE / "output"

    data_dir = year_dir / "data" if year_dir else BASE / "data"
    year_config = load_year_config(data_dir)
    excluded_names = set(year_config.get("excluded_patients", []))

    # manifest.json があれば読み込む（ファイル名解決用）
    manifest = None
    if year_dir:
        manifest_path = year_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text("utf-8"))

    results = match_data["results"]
    receipt_map = {r["id"]: r for r in receipts}

    # 患者情報を動的取得
    patient_keys = get_patient_keys(mynaportal)
    included_keys = [k for k in patient_keys if k not in excluded_names]

    parts = year_label.split("_") if year_label else []
    era = parts[1] if len(parts) >= 2 else ""
    fiscal_year = parts[0] if len(parts) >= 1 else ""
    title_year = f"令和{era[1:]}年分" if era else (year_label or "")

    lines = [
        f"# {title_year} 医療費 照合チェックリスト・控除根拠一覧",
        "",
        "保管用資料 — 確定申告の根拠として領収書とともに5年間保存",
        "",
        "---",
        "",
    ]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション1: 全体サマリー
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    portal_total = sum(
        mynaportal[k]["合計"]["窓口負担相当額"]
        for k in included_keys
    )
    form_items = []
    for r in results:
        if r.get("include_in_xlsx") and r.get("deductible_amount", 0) > 0:
            form_items.append(r)
    oop_total = 0
    for r in results:
        oop = r.get("oop_judgment")
        if oop and not r.get("include_in_xlsx"):
            oop_total += oop.get("deductible_total", 0)
    form_total_amount = sum(r["deductible_amount"] for r in form_items) + oop_total

    lines.extend([
        "## 全体サマリー",
        "",
        "| 区分 | 金額 | 備考 |",
        "|---|---|---|",
        f"| マイナポータル連携 | {fmt(portal_total)}円 | e-Tax自動取得（XML原本） |",
        f"| 集計フォーム追加分 | {fmt(form_total_amount)}円 | xlsx手入力（領収書5年保存要） |",
        f"| **医療費合計** | **{fmt(portal_total + form_total_amount)}円** | |",
        f"| 足切り後控除額 | {fmt(max(0, portal_total + form_total_amount - 100000))}円 | |",
        "",
        "---",
        "",
    ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション2: 集計フォーム記載分（控除根拠付き詳細）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    lines.extend([
        "## 集計フォーム記載分（確定申告で追加入力する項目）",
        "",
        "以下の項目はマイナポータル連携に含まれないため、",
        "医療費集計フォーム（xlsx）で手入力/読込する。領収書の5年間保存が必要。",
        "",
    ])

    for r in form_items:
        rid = r["receipt_id"]
        receipt = receipt_map.get(rid, {})
        _write_form_item(lines, r, receipt, manifest)

    # oop_judgment の deductible 項目（matched分）
    oop_entries = []
    for r in results:
        oop = r.get("oop_judgment")
        if not oop or oop.get("deductible_total", 0) == 0:
            continue
        if r.get("include_in_xlsx"):
            continue
        for item in oop["items"]:
            if item["judgment"] == "deductible":
                oop_entries.append((r, item))

    # カテゴリ別にグループ化して表示
    by_category: dict[str, list] = defaultdict(list)
    for r, item in oop_entries:
        cat = _categorize(item["item"])
        by_category[cat].append((r, item))

    for cat, entries in by_category.items():
        subtotal = sum(item["amount"] for _, item in entries)
        lines.extend([
            f"### {cat}（小計: {fmt(subtotal)}円）",
            "",
        ])

        lines.append("| PDF | 日付 | 内容 | 金額 | 保険診療 | 根拠詳細 |")
        lines.append("|---|---|---|---|---|---|")

        for r, item in sorted(entries, key=lambda x: x[0].get("date", "")):
            rid = r.get("receipt_id", "")
            pdf = rid_to_stored_path(rid, manifest) if rid else "-"
            dt = r.get("date", "")
            receipt = receipt_map.get(rid, {})
            ins_amt = r.get("receipt_insurance_amount", receipt.get("insurance_amount", 0))
            portal_copay = r.get("portal_copay")
            portal_note = f"（ポータル窓口負担{fmt(portal_copay)}円に含まれる受診）" if portal_copay else ""
            detail = _infer_treatment(item["item"], ins_amt, receipt, r)

            lines.append(
                f"| `{rid}` | {dt} | {item['item']} | {fmt(item['amount'])}円 "
                f"| {fmt(ins_amt)}円{portal_note} | {detail} |"
            )

        lines.extend(["", ""])

    lines.extend(["---", ""])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション3: マイナポータル連携済み一覧
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    lines.extend([
        "## マイナポータル連携済み（e-Tax自動取得分）",
        "",
        "以下はe-Taxのマイナポータル連携で自動取得されるため、",
        "確定申告で個別に入力する必要はない。XMLデータが原本となる。",
        "",
    ])

    matched_items = [r for r in results if r["match_status"] == "matched"]
    by_patient_month: dict[tuple, list] = defaultdict(list)
    for r in matched_items:
        key = (r["patient"], r["year_month"])
        by_patient_month[key].append(r)

    # 全患者を動的に取得して表示
    all_patient_names = []
    for key in patient_keys:
        all_patient_names.append(mynaportal[key]["氏名"])

    for patient_name in all_patient_names:
        patient_entries = {k: v for k, v in by_patient_month.items() if k[0] == patient_name}
        if not patient_entries:
            continue

        lines.append(f"### {patient_name}")
        lines.append("")
        lines.append("| 年月 | PDF | 日付 | 施設 | 保険診療 | ポータル窓口負担 | 保険適用外 | 適用外判定 |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for (_, ym), items in sorted(patient_entries.items()):
            portal_copay = items[0].get("portal_copay", 0) if items else 0
            for r in sorted(items, key=lambda x: x.get("date", "")):
                rid = r.get("receipt_id", "")
                pdf_short = f"`{rid}`" if rid else "-"
                dt = r.get("date", "")
                facility = r["facility"]
                ins_amt = r.get("receipt_insurance_amount", 0)
                oop = r.get("oop_judgment")
                oop_total_val = oop["total"] if oop else 0
                oop_verdict = ""
                if oop:
                    verdicts = []
                    for item in oop["items"]:
                        symbol = "○" if item["judgment"] == "deductible" else "×"
                        verdicts.append(f"{symbol}{item['item']}{fmt(item['amount'])}円")
                    oop_verdict = " / ".join(verdicts)

                lines.append(
                    f"| {ym} | {pdf_short} | {dt} | {facility} "
                    f"| {fmt(ins_amt)}円 | {fmt(portal_copay)}円 "
                    f"| {fmt(oop_total_val)}円 | {oop_verdict} |"
                )

        lines.extend(["", ""])

    lines.extend(["---", ""])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション4: 控除対象外項目
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    lines.extend([
        "## 控除対象外と判定した項目",
        "",
        "| PDF | 日付 | 患者 | 施設 | 内容 | 金額 | 対象外理由 |",
        "|---|---|---|---|---|---|---|",
    ])

    for r in results:
        if r["judgment"] == "not_deductible" and r.get("receipt_id"):
            rid = r["receipt_id"]
            lines.append(
                f"| `{rid}` | {r.get('date', '')} | {r['patient']} | {r['facility']} "
                f"| {r['judgment_reason'][:30]} | {fmt(r.get('receipt_total', r.get('portal_copay', 0)))}円 "
                f"| {r['judgment_reason']} |"
            )

    for r in results:
        oop = r.get("oop_judgment")
        if not oop:
            continue
        for item in oop["items"]:
            if item["judgment"] == "not_deductible":
                rid = r.get("receipt_id", "")
                lines.append(
                    f"| `{rid}` | {r.get('date', '')} | {r['patient']} | {r['facility']} "
                    f"| {item['item']} | {fmt(item['amount'])}円 "
                    f"| {item['reason']} |"
                )

    lines.extend(["", "---", ""])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション5: 社会保険料控除
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    si_items = [r for r in results if r.get("deduction_type") == "social_insurance"]
    if si_items:
        si_total = sum(r["deductible_amount"] for r in si_items)
        lines.extend([
            "## 社会保険料控除",
            "",
            "| PDF | 日付 | 種別 | 金額 | 備考 |",
            "|---|---|---|---|---|",
        ])
        for r in si_items:
            rid = r["receipt_id"]
            lines.append(
                f"| `{rid}` | {r['date']} | {r.get('insurance_type', '')} "
                f"| {fmt(r['deductible_amount'])}円 | {r.get('notes', '')[:50]} |"
            )
        lines.extend([
            f"| | | **合計** | **{fmt(si_total)}円** | |",
            "",
            "---",
            "",
        ])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # セクション6: 領収書保存チェックリスト
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    lines.extend([
        "## 領収書保存チェックリスト",
        "",
        "集計フォーム記載分・社会保険料控除分の領収書は5年間保存が必要です。",
        "",
        "| ☐ | PDF | 患者 | 施設 | 日付 | 金額 | 控除区分 |",
        "|---|---|---|---|---|---|---|",
    ])

    need_save = []
    for r in results:
        rid = r.get("receipt_id")
        if not rid:
            continue
        if r.get("include_in_xlsx") or r.get("deduction_type") == "social_insurance":
            need_save.append(r)
        elif r.get("oop_judgment", {}).get("deductible_total", 0) > 0:
            need_save.append(r)

    for r in sorted(need_save, key=lambda x: x.get("date", "")):
        rid = r["receipt_id"]
        oop = r.get("oop_judgment", {})
        oop_ded = oop.get("deductible_total", 0) if oop else 0
        amount = r.get("deductible_amount", 0) or oop_ded
        dtype = r.get("deduction_type", "medical_expense")
        label = "社会保険料" if dtype == "social_insurance" else "医療費"
        lines.append(
            f"| ☐ | `{rid}` | {r['patient']} | {r['facility']} "
            f"| {r.get('date', '')} | {fmt(amount)}円 | {label} |"
        )

    lines.extend(["", ""])

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "verification_checklist.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"照合チェックリストを {path} に出力しました")
    print(f"  総行数: {len(lines)}")


def _write_form_item(lines: list, r: dict, receipt: dict, manifest: dict | None = None) -> None:
    """include_in_xlsx=True の項目を詳細出力"""
    rid = r["receipt_id"]
    pdf = rid_to_stored_path(rid, manifest)

    lines.append(f"### {rid} — {r['patient']} / {r['facility']}（{r.get('date', '')}）")
    lines.append("")
    lines.append(f"- **PDF**: `{pdf}`")
    lines.append(f"- **領収書合計**: {fmt(r.get('receipt_total', 0))}円")

    ins = r.get("receipt_insurance_amount", 0)
    oop_amt = r.get("receipt_out_of_pocket", 0)
    if ins > 0:
        lines.append(f"- **保険診療**: {fmt(ins)}円")
    if oop_amt > 0:
        lines.append(f"- **保険適用外**: {fmt(oop_amt)}円")
        detail = r.get("out_of_pocket_detail", {})
        for item_name, amt in detail.items():
            lines.append(f"  - {item_name}: {fmt(amt)}円")

    lines.append(f"- **控除対象額**: {fmt(r['deductible_amount'])}円")
    lines.append(f"- **判定**: {r['judgment']}")
    lines.append(f"- **根拠**: {r['judgment_reason']}")

    oop = r.get("oop_judgment")
    if oop:
        for item in oop["items"]:
            symbol = "○控除対象" if item["judgment"] == "deductible" else "×対象外"
            lines.append(f"  - {item['item']}: {fmt(item['amount'])}円 → {symbol}（{item['reason']}）")

    if receipt.get("notes"):
        lines.append(f"- **領収書備考**: {receipt['notes'][:100]}")
    lines.extend(["", ""])


def _categorize(item_name: str) -> str:
    if "不妊" in item_name:
        return "不妊治療"
    if "NIPT" in item_name or "出生前" in item_name or "遺伝" in item_name:
        return "出生前診断（NIPT）・遺伝カウンセリング"
    if "健診" in item_name or "検診" in item_name or "産科" in item_name:
        return "妊婦健診"
    if "血圧計" in item_name or "治療用器具" in item_name:
        return "治療用器具"
    return item_name


def _infer_treatment(item_name: str, ins_amount: int, receipt: dict, r: dict) -> str:
    """診療点数等から治療内容を推定した根拠を返す"""
    notes = receipt.get("notes", "")
    dept = r.get("department", receipt.get("department", ""))

    parts = []
    if dept:
        parts.append(f"診療科: {dept}")
    if "点" in notes:
        import re
        points = re.findall(r'(\d[\d,]*点)', notes)
        if points:
            parts.append(f"点数: {', '.join(points)}")
    if ins_amount > 0:
        parts.append(f"保険診療{fmt(ins_amount)}円と同日")

    return " / ".join(parts) if parts else "領収書記載の保険適用外費用"


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        year_dir = BASE / "years" / sys.argv[1]
        data_dir = year_dir / "data"
        output_dir = year_dir / "output"
        match_data, receipts, mynaportal = load_data(data_dir)
        generate_checklist(match_data, receipts, mynaportal, output_dir, year_dir, sys.argv[1])
    else:
        generate_checklist()
