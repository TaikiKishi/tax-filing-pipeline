"""
ユーザー確認結果を match_results.json に反映する (Stage 3)

年度固有の確認ロジックは data/confirmation_rules.json に記述する。
このモジュールはルールファイルを読み込み、match_results.json を更新する。

confirmation_rules.json のフォーマット:
{
  "updates": [
    {
      "receipt_id": "xxx_001",
      "action": "update_oop",      // "update_oop" | "set_deductible" | "set_not_deductible" | "add_entry"
      "oop_items": [...],           // action=update_oop の場合
      "deductible_amount": 1000,    // action=set_deductible の場合
      "judgment_reason": "...",
      ...
    }
  ],
  "new_entries": [
    { ... 完全な match_result エントリ ... }
  ],
  "compensations": [
    {
      "receipt_id": "xxx_015",
      "source": "保険会社名",
      "amount": 25000,
      "target_date": "2025-07-22",
      "notes": "..."
    }
  ],
  "resolved_ids": ["xxx_001", "xxx_002"]
}

Usage:
    python -m src.apply_confirmations 2025_R7
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_rules(data_dir: Path) -> dict:
    """confirmation_rules.json を読み込む。なければ空ルールを返す。"""
    rules_path = data_dir / "confirmation_rules.json"
    if rules_path.exists():
        return json.loads(rules_path.read_text("utf-8"))
    return {"updates": [], "new_entries": [], "compensations": [], "resolved_ids": []}


def apply_confirmations(data_dir: Path) -> None:
    path = data_dir / "match_results.json"
    data = json.loads(path.read_text("utf-8"))
    results = data["results"]
    rules = load_rules(data_dir)

    # receipt_id → index のマップ
    id_map: dict[str, int] = {}
    for i, r in enumerate(results):
        rid = r.get("receipt_id")
        if rid:
            id_map[rid] = i

    # ── ルールに基づく更新 ──
    for update in rules.get("updates", []):
        rid = update["receipt_id"]
        if rid not in id_map:
            continue
        r = results[id_map[rid]]
        action = update.get("action", "update_oop")

        if action == "update_oop":
            # 保険適用外項目の判定を更新
            if "oop_items" in update:
                oop_items = update["oop_items"]
                deductible_total = sum(
                    it["amount"] for it in oop_items if it["judgment"] == "deductible"
                )
                r["oop_judgment"] = {
                    "total": sum(it["amount"] for it in oop_items),
                    "items": oop_items,
                    "deductible_total": deductible_total,
                }
            # oop_judgment 内の個別アイテムだけ更新
            if "update_oop_items" in update:
                oop = r.get("oop_judgment", {"total": 0, "items": [], "deductible_total": 0})
                for item_update in update["update_oop_items"]:
                    for item in oop["items"]:
                        if item["item"] == item_update.get("match_item", ""):
                            item.update(item_update.get("set", {}))
                oop["deductible_total"] = sum(
                    it["amount"] for it in oop["items"] if it["judgment"] == "deductible"
                )
                r["oop_judgment"] = oop

        elif action == "set_deductible":
            r["judgment"] = "deductible"
            if "deductible_amount" in update:
                r["deductible_amount"] = update["deductible_amount"]
            if "judgment_reason" in update:
                r["judgment_reason"] = update["judgment_reason"]
            r["include_in_xlsx"] = update.get("include_in_xlsx", True)
            if "oop_items" in update:
                oop_items = update["oop_items"]
                r["oop_judgment"] = {
                    "total": sum(it["amount"] for it in oop_items),
                    "items": oop_items,
                    "deductible_total": sum(
                        it["amount"] for it in oop_items if it["judgment"] == "deductible"
                    ),
                }

        elif action == "set_not_deductible":
            r["judgment"] = "not_deductible"
            if "judgment_reason" in update:
                r["judgment_reason"] = update["judgment_reason"]
            r["deductible_amount"] = 0
            r["include_in_xlsx"] = False

    # ── 新規エントリの追加 ──
    for entry in rules.get("new_entries", []):
        rid = entry.get("receipt_id")
        if rid and rid not in id_map:
            results.append(entry)
            id_map[rid] = len(results) - 1
        elif rid and rid in id_map:
            results[id_map[rid]] = entry

    # ── 補填される金額の登録 ──
    for comp in rules.get("compensations", []):
        rid = comp["receipt_id"]
        if rid in id_map:
            r = results[id_map[rid]]
            r["insurance_compensation"] = {
                "source": comp["source"],
                "amount": comp["amount"],
                "target_date": comp.get("target_date", ""),
                "notes": comp.get("notes", ""),
            }

    # ── サマリー更新 ──
    summary = data["summary"]
    summary["total_items"] = len(results)
    summary["matched"] = sum(1 for r in results if r["match_status"] == "matched")
    summary["receipt_only"] = sum(1 for r in results if r["match_status"] == "receipt_only")
    summary["notification_only"] = sum(1 for r in results if r["match_status"] == "notification_only")

    # 集計フォーム項目を再構築
    xlsx_items = []
    for r in results:
        if r.get("include_in_xlsx") and r.get("deductible_amount", 0) > 0:
            xlsx_items.append({
                "receipt_id": r["receipt_id"],
                "patient": r["patient"],
                "facility": r["facility"],
                "amount": r["deductible_amount"],
            })

    # oop_judgment の deductible 項目（matched 分から追加）
    oop_deductible_items = []
    for r in results:
        oop = r.get("oop_judgment")
        if not oop or oop["deductible_total"] == 0:
            continue
        if r.get("include_in_xlsx"):
            continue
        for item in oop["items"]:
            if item["judgment"] == "deductible":
                oop_deductible_items.append({
                    "receipt_id": r.get("receipt_id"),
                    "patient": r["patient"],
                    "facility": r["facility"],
                    "item": item["item"],
                    "amount": item["amount"],
                })

    oop_total = sum(it["amount"] for it in oop_deductible_items)
    xlsx_total = sum(it["amount"] for it in xlsx_items)

    summary["medical_expense"]["xlsx_items"] = xlsx_items
    summary["medical_expense"]["xlsx_total"] = xlsx_total
    summary["medical_expense"]["oop_deductible_items"] = oop_deductible_items
    summary["medical_expense"]["oop_deductible_total"] = oop_total

    # 補填情報をサマリーに追加
    compensation_items = []
    for r in results:
        comp = r.get("insurance_compensation")
        if comp:
            compensation_items.append({
                "receipt_id": r.get("receipt_id"),
                "source": comp["source"],
                "amount": comp["amount"],
                "target_date": comp.get("target_date", ""),
            })
    summary["medical_expense"]["compensation_items"] = compensation_items
    summary["medical_expense"]["compensation_total"] = sum(
        c["amount"] for c in compensation_items
    )

    # conditional_items を更新（解決済みを除外）
    resolved_ids = set(rules.get("resolved_ids", []))
    summary["conditional_items"] = [
        item for item in summary.get("conditional_items", [])
        if item["receipt_id"] not in resolved_ids
    ]

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    comp_total = summary["medical_expense"]["compensation_total"]
    print("match_results.json を更新しました")
    print(f"  集計フォーム項目: {len(xlsx_items)}件 ({xlsx_total:,}円)")
    print(f"  OOP控除対象項目: {len(oop_deductible_items)}件 ({oop_total:,}円)")
    print(f"  集計フォーム合計: {xlsx_total + oop_total:,}円")
    print(f"  補填される金額: {len(compensation_items)}件 ({comp_total:,}円)")
    print(f"  未解決要確認: {len(summary['conditional_items'])}件")


def run(year_dir: Path, year_label: str) -> None:
    """パイプラインから呼ばれるエントリポイント。"""
    data_dir = year_dir / "data"
    apply_confirmations(data_dir)


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.apply_confirmations 2025_R7")
        sys.exit(1)
    year_dir = BASE / "years" / sys.argv[1]
    run(year_dir, sys.argv[1])


if __name__ == "__main__":
    main()
