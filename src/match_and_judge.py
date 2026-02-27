"""
突合処理 & 控除判定

receipts.json と mynaportal.json を突合し、各項目に控除判定を付与する。
出力: data/match_results.json

家族構成や自治体固有ルールは mynaportal.json と年度設定から動的に取得する。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


# ── ユーティリティ ─────────────────────────────────────────

def normalize_facility(name: str) -> str:
    """施設名を正規化して比較しやすくする"""
    name = name.replace(" ", "").replace("\u3000", "")
    for prefix in ["医療法人", "社会医療法人", "一般社団法人", "公益財団法人",
                    "医療法人社団", "医療法人財団"]:
        name = name.replace(prefix, "")
    return name


def facility_match(receipt_name: str, portal_name: str) -> bool:
    """施設名が一致するかを判定（部分一致考慮）"""
    r = normalize_facility(receipt_name)
    p = normalize_facility(portal_name)
    if r == p:
        return True
    if r in p or p in r:
        return True
    return False


def extract_year_month(date_str: str) -> str:
    """'2025-04-24' → '2025-04'"""
    return date_str[:7]


def load_year_config(data_dir: Path) -> dict:
    """年度設定を読み込む。子ども医療費助成等の自治体ルールを含む。"""
    config_path = data_dir / "year_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text("utf-8"))
    return {
        "excluded_patients": [],
        "excluded_patient_reason": "子ども医療費助成により実質自己負担0円のため控除対象外",
    }


# ── メイン処理 ─────────────────────────────────────────────

def load_data(data_dir: Path):
    receipts = json.loads((data_dir / "receipts.json").read_text("utf-8"))
    mynaportal = json.loads((data_dir / "mynaportal.json").read_text("utf-8"))
    return receipts, mynaportal


def get_patient_keys(mynaportal: dict) -> list[str]:
    """マイナポータルデータから患者キー一覧を動的に取得する。"""
    keys = []
    for key, value in mynaportal.items():
        if isinstance(value, dict) and "明細" in value:
            keys.append(key)
    return keys


def group_receipts_by_month_facility(receipts: list[dict]) -> dict:
    """領収書を (patient, year_month, facility_normalized) でグループ化"""
    groups = defaultdict(list)
    for r in receipts:
        ym = extract_year_month(r["date"])
        key = (r["patient"], ym, normalize_facility(r["facility"]))
        groups[key].append(r)
    return groups


def match_receipts_to_portal(receipts: list[dict], mynaportal: dict,
                             year_config: dict) -> list[dict]:
    """領収書とマイナポータル通知を突合"""
    results = []
    patient_keys = get_patient_keys(mynaportal)
    used_portal_indices = {name: set() for name in patient_keys}
    excluded_patients = set(year_config.get("excluded_patients", []))
    excluded_reason = year_config.get(
        "excluded_patient_reason",
        "子ども医療費助成により実質自己負担0円のため控除対象外"
    )

    # 患者名 → マイナポータルキーのマッピング
    name_to_key = {}
    for key in patient_keys:
        full_name = mynaportal[key]["氏名"]
        name_to_key[full_name] = key

    # 年金・保険系は突合対象外 → 直接判定
    medical_receipts = []
    for r in receipts:
        if r["category"] in ("pension", "health_insurance"):
            results.append(build_social_insurance_result(r))
        else:
            medical_receipts.append(r)

    groups = group_receipts_by_month_facility(medical_receipts)

    for (patient, ym, fac_norm), group in groups.items():
        portal_key = name_to_key.get(patient)
        if not portal_key:
            for r in group:
                results.append(build_receipt_only_result(
                    r, excluded_patients, excluded_reason))
            continue

        entries = mynaportal[portal_key]["明細"]
        matched_portal = None
        matched_idx = None
        for i, entry in enumerate(entries):
            if i in used_portal_indices[portal_key]:
                continue
            if entry["year_month"] == ym and facility_match(fac_norm, entry["facility"]):
                matched_portal = entry
                matched_idx = i
                break

        if matched_portal:
            used_portal_indices[portal_key].add(matched_idx)
            receipt_insurance_total = sum(r["insurance_amount"] for r in group)
            portal_copay = matched_portal["copay"]
            amount_diff = abs(receipt_insurance_total - portal_copay)

            for r in group:
                is_excluded = any(ep in r["patient"] for ep in excluded_patients)
                result = build_matched_result(
                    r, matched_portal, amount_diff,
                    is_excluded, excluded_reason)
                results.append(result)
        else:
            for r in group:
                results.append(build_receipt_only_result(
                    r, excluded_patients, excluded_reason))

    # マイナポータルのみの項目
    for portal_key in patient_keys:
        entries = mynaportal[portal_key]["明細"]
        is_excluded = portal_key in excluded_patients
        for i, entry in enumerate(entries):
            if i not in used_portal_indices[portal_key]:
                results.append(build_notification_only_result(
                    entry, mynaportal[portal_key]["氏名"],
                    is_excluded, excluded_reason
                ))

    return results


# ── 結果ビルダー ───────────────────────────────────────────

def build_matched_result(receipt: dict, portal: dict, amount_diff: int,
                         is_excluded: bool, excluded_reason: str) -> dict:
    """マイナポータルと突合できた項目"""
    has_oop = receipt.get("out_of_pocket", 0) > 0

    if is_excluded:
        judgment = "not_deductible"
        reason = excluded_reason
        deduction_type = "not_deductible"
    else:
        judgment = "mynaportal_covered"
        reason = "マイナポータル連携で自動処理される保険診療分"
        deduction_type = "medical_expense"

    result = {
        "receipt_id": receipt["id"],
        "match_status": "matched",
        "patient": receipt["patient"],
        "year_month": extract_year_month(receipt["date"]),
        "date": receipt["date"],
        "facility": receipt["facility"],
        "department": receipt.get("department", ""),
        "receipt_insurance_amount": receipt["insurance_amount"],
        "portal_copay": portal["copay"],
        "amount_diff": amount_diff,
        "judgment": judgment,
        "judgment_reason": reason,
        "deduction_type": deduction_type,
        "deductible_amount": 0,
        "include_in_xlsx": False,
    }

    if has_oop and not is_excluded:
        oop_judgment = judge_out_of_pocket(receipt)
        result["oop_judgment"] = oop_judgment

    return result


def build_receipt_only_result(receipt: dict, excluded_patients: set,
                              excluded_reason: str) -> dict:
    """領収書のみ（マイナポータルに該当なし）"""
    is_excluded = any(ep in receipt["patient"] for ep in excluded_patients)

    if is_excluded:
        judgment = "not_deductible"
        reason = excluded_reason
        deduction_type = "not_deductible"
        deductible_amount = 0
        include_xlsx = False
    else:
        judgment, reason, deductible_amount = judge_unmatched_receipt(receipt)
        deduction_type = "medical_expense"
        include_xlsx = judgment == "deductible" and deductible_amount > 0

    return {
        "receipt_id": receipt["id"],
        "match_status": "receipt_only",
        "patient": receipt["patient"],
        "year_month": extract_year_month(receipt["date"]),
        "date": receipt["date"],
        "facility": receipt["facility"],
        "department": receipt.get("department", ""),
        "receipt_total": receipt["total"],
        "receipt_insurance_amount": receipt["insurance_amount"],
        "receipt_out_of_pocket": receipt.get("out_of_pocket", 0),
        "out_of_pocket_detail": receipt.get("out_of_pocket_detail", {}),
        "judgment": judgment,
        "judgment_reason": reason,
        "deduction_type": deduction_type,
        "deductible_amount": deductible_amount,
        "include_in_xlsx": include_xlsx,
    }


def build_social_insurance_result(receipt: dict) -> dict:
    """国民年金・国保税"""
    ins_type = "国民年金保険料" if receipt["category"] == "pension" else "国民健康保険税"
    return {
        "receipt_id": receipt["id"],
        "match_status": "receipt_only",
        "patient": receipt["patient"],
        "year_month": extract_year_month(receipt["date"]),
        "date": receipt["date"],
        "facility": receipt["facility"],
        "receipt_total": receipt["total"],
        "judgment": "deductible",
        "judgment_reason": f"社会保険料控除対象（{ins_type}）",
        "tax_answer_ref": "No.1130",
        "deduction_type": "social_insurance",
        "insurance_type": ins_type,
        "deductible_amount": receipt["total"],
        "include_in_xlsx": False,
        "notes": receipt.get("notes", ""),
    }


def build_notification_only_result(entry: dict, patient_name: str,
                                   is_excluded: bool, excluded_reason: str) -> dict:
    """マイナポータルのみ（領収書なし）"""
    return {
        "receipt_id": None,
        "match_status": "notification_only",
        "patient": patient_name,
        "year_month": entry["year_month"],
        "facility": entry["facility"],
        "portal_category": entry["category"],
        "portal_copay": entry["copay"],
        "portal_total": entry["total"],
        "judgment": "not_deductible" if is_excluded else "mynaportal_covered",
        "judgment_reason": (
            excluded_reason if is_excluded
            else "マイナポータル連携で処理（領収書は手元になし）"
        ),
        "deduction_type": "not_deductible" if is_excluded else "medical_expense",
        "deductible_amount": 0,
        "include_in_xlsx": False,
    }


# ── 控除判定ロジック ───────────────────────────────────────

def judge_out_of_pocket(receipt: dict) -> dict:
    """保険適用外分の控除判定"""
    detail = receipt.get("out_of_pocket_detail", {})
    amount = receipt.get("out_of_pocket", 0)

    judgments = []
    for item, item_amount in detail.items():
        j, reason = judge_oop_item(item, item_amount, receipt)
        judgments.append({
            "item": item,
            "amount": item_amount,
            "judgment": j,
            "reason": reason,
        })

    if not judgments and amount > 0:
        j, reason = judge_oop_item("不明", amount, receipt)
        judgments.append({
            "item": "保険適用外",
            "amount": amount,
            "judgment": j,
            "reason": reason,
        })

    return {
        "total": amount,
        "items": judgments,
        "deductible_total": sum(
            j["amount"] for j in judgments if j["judgment"] == "deductible"
        ),
    }


def judge_oop_item(item: str, amount: int, receipt: dict) -> tuple[str, str]:
    """自費項目1件の控除判定"""
    item_lower = item.lower()

    if "健診" in item_lower or "検診" in item_lower:
        return "deductible", "妊婦健診費用は医療費控除対象（国税庁No.1124）"
    if "文書" in item_lower or "診断書" in item_lower or "証明" in item_lower:
        return "not_deductible", "文書料（診断書・証明書）は医療費控除対象外"
    if "ベッド" in item_lower or "室料" in item_lower or "個室" in item_lower:
        return "conditional", "差額ベッド代は原則対象外（やむを得ない場合を除く）"
    if "自費" in item_lower or "96" in item_lower:
        return "conditional", "自費診療（内容により控除可否が異なる）要確認"

    return "conditional", f"保険適用外（{item}）: 内容確認要"


def judge_unmatched_receipt(receipt: dict) -> tuple[str, str, int]:
    """マイナポータル未掲載の領収書の控除判定"""
    if receipt["insurance_amount"] > 0:
        return (
            "deductible",
            "マイナポータル未掲載の保険診療分 → 集計フォームに記載",
            receipt["insurance_amount"],
        )

    oop = receipt.get("out_of_pocket", 0)
    if oop > 0:
        detail = receipt.get("out_of_pocket_detail", {})
        if detail:
            total_deductible = 0
            reasons = []
            for item, amt in detail.items():
                j, reason = judge_oop_item(item, amt, receipt)
                if j == "deductible":
                    total_deductible += amt
                reasons.append(f"{item}: {reason}")
            return (
                "deductible" if total_deductible > 0 else "conditional",
                "; ".join(reasons),
                total_deductible,
            )
        return "conditional", "保険適用外（内容確認要）", oop

    return "not_deductible", "金額0円のため控除対象外", 0


# ── 集計 ───────────────────────────────────────────────────

def summarize(results: list[dict], mynaportal: dict) -> dict:
    """結果のサマリーを生成"""
    patient_keys = get_patient_keys(mynaportal)

    # マイナポータル合計（全患者）
    mynaportal_totals = {}
    for key in patient_keys:
        name = mynaportal[key]["氏名"]
        copay = mynaportal[key]["合計"]["窓口負担相当額"]
        mynaportal_totals[name] = copay

    summary = {
        "total_items": len(results),
        "matched": 0,
        "receipt_only": 0,
        "notification_only": 0,
        "medical_expense": {
            "mynaportal_by_patient": mynaportal_totals,
            "mynaportal_total": sum(mynaportal_totals.values()),
            "xlsx_items": [],
            "xlsx_total": 0,
        },
        "social_insurance": {
            "pension": 0,
            "health_insurance": 0,
            "items": [],
        },
        "not_deductible_total": 0,
        "conditional_items": [],
    }

    for r in results:
        status = r["match_status"]
        summary[status] = summary.get(status, 0) + 1

        if r["deduction_type"] == "social_insurance":
            ins_type = r.get("insurance_type", "")
            if "年金" in ins_type:
                summary["social_insurance"]["pension"] += r["deductible_amount"]
            else:
                summary["social_insurance"]["health_insurance"] += r["deductible_amount"]
            summary["social_insurance"]["items"].append({
                "type": ins_type,
                "amount": r["deductible_amount"],
                "notes": r.get("notes", ""),
            })

        elif r.get("include_in_xlsx"):
            summary["medical_expense"]["xlsx_items"].append({
                "patient": r["patient"],
                "facility": r["facility"],
                "amount": r["deductible_amount"],
            })
            summary["medical_expense"]["xlsx_total"] += r["deductible_amount"]

        elif r["judgment"] == "conditional":
            summary["conditional_items"].append({
                "receipt_id": r["receipt_id"],
                "patient": r["patient"],
                "facility": r["facility"],
                "reason": r["judgment_reason"],
            })

    return summary


# ── エントリーポイント ─────────────────────────────────────

def main(data_dir: Path):
    receipts, mynaportal = load_data(data_dir)
    year_config = load_year_config(data_dir)
    results = match_receipts_to_portal(receipts, mynaportal, year_config)
    summary = summarize(results, mynaportal)

    output = {
        "results": results,
        "summary": summary,
    }

    out_path = data_dir / "match_results.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"突合結果を {out_path} に出力しました")
    print(f"  総件数: {summary['total_items']}")
    print(f"  突合: {summary['matched']}, 領収書のみ: {summary['receipt_only']}, 通知のみ: {summary['notification_only']}")
    print(f"  マイナポータル連携医療費: {summary['medical_expense']['mynaportal_total']:,}円")
    print(f"  集計フォーム記載対象: {len(summary['medical_expense']['xlsx_items'])}件 / {summary['medical_expense']['xlsx_total']:,}円")
    print(f"  社会保険料: 年金{summary['social_insurance']['pension']:,}円 / 国保{summary['social_insurance']['health_insurance']:,}円")
    print(f"  要確認: {len(summary['conditional_items'])}件")


def run(year_dir: Path, year_label: str) -> None:
    """パイプラインから呼ばれるエントリポイント。"""
    data_dir = year_dir / "data"
    main(data_dir)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        year_dir = BASE / "years" / sys.argv[1]
        run(year_dir, sys.argv[1])
    else:
        main(BASE / "data")
