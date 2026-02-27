"""
確定申告プレファイリングチェック (Stage 6)

e-Tax入力前に、NTA QAベースのチェックリストで申告内容の漏れを確認する。
データから自動判定できる項目は自動で、人間の確認が必要な項目は
チェックリストとして出力する。

参照: https://www.nta.go.jp/taxes/shiraberu/shinkoku/qa/13.htm

出力:
    - prefiling_checklist.md — 確定申告前チェックリスト
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_json_safe(path: Path):
    """JSONファイルを安全に読み込む。存在しなければNoneを返す。"""
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None


def check_medical_expenses(data_dir: Path) -> dict:
    """医療費控除の自動チェック。"""
    result = {"status": "unknown", "details": []}

    match_data = load_json_safe(data_dir / "match_results.json")
    if not match_data:
        result["status"] = "no_data"
        result["details"].append("match_results.json が見つかりません")
        return result

    entries = match_data.get("results", match_data if isinstance(match_data, list) else [])
    medical = [e for e in entries if e.get("deduction_type") == "medical_expense"]
    total = sum(e.get("deductible_amount", 0) for e in medical)

    # マイナポータル連携分も含める
    mynaportal_covered = [e for e in entries if e.get("judgment") == "mynaportal_covered"]
    mynaportal_total = sum(e.get("deductible_amount", 0) for e in mynaportal_covered)

    grand_total = total + mynaportal_total
    result["total_medical"] = grand_total
    result["xlsx_amount"] = total
    result["mynaportal_amount"] = mynaportal_total
    result["status"] = "ok" if grand_total > 100000 else "below_threshold"
    result["details"].append(f"医療費控除対象合計: {grand_total:,}円")
    if total > 0:
        result["details"].append(f"  うち集計フォーム記載分: {total:,}円")
    if mynaportal_total > 0:
        result["details"].append(f"  うちマイナポータル連携分: {mynaportal_total:,}円")

    if grand_total <= 100000:
        result["details"].append("注意: 医療費合計が10万円以下です。控除が受けられない可能性があります")

    return result


def check_mynaportal(data_dir: Path) -> dict:
    """マイナポータルデータの確認。"""
    result = {"status": "unknown", "details": []}

    mynaportal = load_json_safe(data_dir / "mynaportal.json")
    if not mynaportal:
        result["status"] = "missing"
        result["details"].append("mynaportal.json が見つかりません。マイナポータル連携データを取得してください")
        return result

    total_entries = 0
    total_copay = 0
    patients = []
    for key, value in mynaportal.items():
        if isinstance(value, dict) and "明細" in value:
            meisai = value["明細"]
            total_entries += len(meisai)
            total_copay += sum(m.get("copay", 0) for m in meisai)
            patients.append(value.get("氏名", key))

    result["status"] = "ok"
    result["total_entries"] = total_entries
    result["details"].append(f"マイナポータル通知: {total_entries}件（{', '.join(patients)}）")
    result["details"].append(f"窓口負担相当額合計: {total_copay:,}円")
    return result


def check_reimbursements(data_dir: Path) -> dict:
    """補填金額の確認。"""
    result = {"status": "unknown", "details": []}

    reimb = load_json_safe(data_dir / "reimbursements.json")
    if not reimb:
        result["status"] = "none"
        result["details"].append("reimbursements.json なし（補填金額なし）")
        return result

    total = sum(r.get("amount", 0) for r in reimb)
    result["status"] = "ok"
    result["total_reimbursement"] = total
    result["details"].append(f"補填金額合計: {total:,}円（{len(reimb)}件）")
    return result


def check_social_insurance(data_dir: Path) -> dict:
    """社会保険料データの確認。"""
    result = {"status": "unknown", "details": []}

    # insurance_deductions.json を優先的にチェック
    insurance = load_json_safe(data_dir / "insurance_deductions.json")
    if insurance:
        social = insurance.get("社会保険料控除", {})
        if isinstance(social, dict) and "合計" in social:
            total = social["合計"]
            details = []
            for key in ["国民年金保険料", "国民健康保険税"]:
                if key in social:
                    details.append(f"  {key}: {social[key].get('合計', 0):,}円")
            result["status"] = "ok"
            result["details"].append(f"社会保険料控除合計: {total:,}円")
            result["details"].extend(details)
            return result

        # フラットな配列形式のフォールバック
        items = insurance if isinstance(insurance, list) else insurance.get("items", [])
        if items:
            total = sum(i.get("amount", 0) for i in items)
            result["status"] = "ok"
            result["details"].append(f"社会保険料控除合計: {total:,}円（{len(items)}件）")
            return result

    # フォールバック: match_results.json から社会保険料分を集計
    match_data = load_json_safe(data_dir / "match_results.json")
    if match_data:
        entries = match_data.get("results", match_data if isinstance(match_data, list) else [])
        social = [e for e in entries if e.get("deduction_type") == "social_insurance"]
        if social:
            total = sum(e.get("deductible_amount", 0) for e in social)
            result["status"] = "ok"
            result["details"].append(f"社会保険料控除合計（match_results由来）: {total:,}円（{len(social)}件）")
            return result

    result["status"] = "no_data"
    result["details"].append("社会保険料データが見つかりません")
    return result


def check_misc_income(data_dir: Path) -> dict:
    """雑所得データの確認。"""
    result = {"status": "unknown", "details": []}

    misc = load_json_safe(data_dir / "misc_income.json")
    if not misc:
        result["status"] = "not_found"
        result["details"].append("misc_income.json が見つかりません。該当なしの場合は問題ありません")
        return result

    incomes = misc.get("income", [])
    expenses = misc.get("expenses", [])
    total_income = sum(i["amount"] for i in incomes)
    total_withholding = sum(i.get("withholding", 0) for i in incomes)
    total_expense = sum(e.get("deductible", 0) for e in expenses)
    net = total_income - total_expense

    result["status"] = "ok"
    result["details"].append(f"雑所得の収入: {len(incomes)}件 / {total_income:,}円")
    result["details"].append(f"  必要経費: {total_expense:,}円")
    result["details"].append(f"  雑所得（差引）: {net:,}円")
    if total_withholding > 0:
        result["details"].append(f"  源泉徴収済み: {total_withholding:,}円")

    if net > 200_000:
        result["details"].append("  注意: 雑所得20万円超 → 給与所得者でも確定申告が必要です")
    elif net > 0:
        result["details"].append("  参考: 雑所得20万円以下 → 給与所得者は確定申告不要の場合あり（住民税申告は必要）")

    return result


def check_furusato_xml(year_dir: Path) -> dict:
    """ふるさと納税XMLの確認。"""
    result = {"status": "unknown", "details": []}

    other_dir = year_dir / "sources" / "other"
    xml_files = list(other_dir.glob("*.xml")) if other_dir.exists() else []

    if xml_files:
        result["status"] = "ok"
        result["details"].append(f"ふるさと納税XML: {len(xml_files)}件")
        for f in xml_files:
            result["details"].append(f"  - {f.name}")
    else:
        result["status"] = "not_found"
        result["details"].append("ふるさと納税XMLが見つかりません。該当なしの場合は問題ありません")

    return result


def check_receipt_coverage(year_dir: Path) -> dict:
    """領収書のJSON化カバレッジ確認。"""
    result = {"status": "unknown", "details": []}

    receipts_dir = year_dir / "sources" / "receipts"
    batches_dir = year_dir / "data" / "batches"

    pdf_count = len(list(receipts_dir.glob("*.pdf"))) if receipts_dir.exists() else 0
    jpg_count = len(list(receipts_dir.glob("*.jpg"))) if receipts_dir.exists() else 0
    source_count = pdf_count + jpg_count

    batch_files = list(batches_dir.glob("batch_*.json")) if batches_dir.exists() else []
    record_count = 0
    for bf in batch_files:
        data = json.loads(bf.read_text("utf-8"))
        record_count += len(data)

    result["source_files"] = source_count
    result["json_records"] = record_count
    result["details"].append(f"ソースファイル: {source_count}件、JSONレコード: {record_count}件")

    if source_count > 0 and record_count == 0:
        result["status"] = "no_json"
        result["details"].append("警告: 領収書ファイルはあるがJSON化されていません。scan-receiptsスキルを実行してください")
    else:
        result["status"] = "ok"

    return result


def generate_checklist(year_dir: Path, year_label: str) -> str:
    """チェックリストMarkdownを生成。"""
    data_dir = year_dir / "data"

    # 自動チェック実行
    medical = check_medical_expenses(data_dir)
    mynaportal = check_mynaportal(data_dir)
    reimb = check_reimbursements(data_dir)
    social = check_social_insurance(data_dir)
    misc = check_misc_income(data_dir)
    furusato = check_furusato_xml(year_dir)
    coverage = check_receipt_coverage(year_dir)

    # 西暦・元号分離
    parts = year_label.split("_")
    fiscal_year = parts[0] if len(parts) >= 1 else year_label
    era = parts[1] if len(parts) >= 2 else ""

    lines = []
    lines.append(f"# 確定申告プレファイリングチェック（{era}・{fiscal_year}年分）\n")
    lines.append("e-Tax入力前の確認チェックリストです。")
    lines.append("参照: https://www.nta.go.jp/taxes/shiraberu/shinkoku/qa/13.htm\n")
    lines.append("---\n")

    # A. 自動チェック結果
    lines.append("## A. データ準備状況（自動チェック）\n")

    def status_icon(s):
        return {"ok": "[x]", "missing": "[ ]", "no_data": "[ ]",
                "not_found": "[-]", "below_threshold": "[!]",
                "no_json": "[!]", "none": "[-]"}.get(s, "[ ]")

    checks = [
        ("領収書JSON化", coverage),
        ("マイナポータルデータ", mynaportal),
        ("医療費控除", medical),
        ("補填金額", reimb),
        ("社会保険料データ", social),
        ("雑所得データ", misc),
        ("ふるさと納税XML", furusato),
    ]

    for name, check in checks:
        icon = status_icon(check["status"])
        lines.append(f"- {icon} **{name}**")
        for detail in check["details"]:
            lines.append(f"  - {detail}")
        lines.append("")

    # B. 確定申告の必要性
    lines.append("---\n")
    lines.append("## B. 確定申告の必要性（手動確認）\n")
    lines.append("- [ ] 給与所得者の確定申告要件に該当するか（年収2,000万超/2ヶ所給与/給与外所得20万超）")
    lines.append("- [ ] 年末調整が完了しているか（源泉徴収票で確認）")
    lines.append("- [ ] 年内退職で年末調整未実施の場合は申告必要")
    lines.append("")

    # C. 所得の確認
    lines.append("## C. 所得の確認（手動確認）\n")
    lines.append("NTA タックスアンサー参照:\n")
    lines.append("- [ ] 給与所得: 源泉徴収票の金額確認")
    if misc["status"] == "ok":
        lines.append("- [x] 雑所得の有無: misc_income.json で管理済み（No.1500, No.1906, No.2010）")
    else:
        lines.append("- [ ] 雑所得の有無: 副業収入、原稿料、暗号資産取引等（No.1500, No.1906, No.2010）")
    lines.append("- [ ] 一時所得の有無: 生命保険満期金、懸賞金等（No.1490）")
    lines.append("- [ ] 配当所得の有無: 株式配当等の課税方式選択（No.1120）")
    lines.append("- [ ] 譲渡所得の有無: 不動産・株式売却等（No.1440, No.1600）")
    lines.append("")

    # D. 所得控除チェック
    lines.append("## D. 所得控除の該当チェック（手動確認）\n")

    lines.append("### D-1. 医療費控除")
    lines.append("- [ ] セルフメディケーション税制との比較検討")
    lines.append("- [ ] 交通費（通院費）の計上漏れがないか")
    lines.append("")

    lines.append("### D-2. 社会保険料控除")
    lines.append("- [ ] 国民年金: 控除証明書（日本年金機構ハガキ）の有無")
    lines.append("- [ ] 国民健康保険税: 納付額証明書の有無")
    lines.append("- [ ] 共済組合掛金: 源泉徴収票の「社会保険料等の金額」に含まれているか")
    lines.append("- [ ] 家族分の保険料も申告しているか")
    lines.append("")

    lines.append("### D-3. 生命保険料控除")
    lines.append("- [ ] 控除証明書が全て揃っているか")
    lines.append("- [ ] 年末調整での処理済み分を確認（源泉徴収票「生命保険料の控除額」欄）")
    lines.append("- [ ] 「証明額」ではなく「申告額」（12月末見込額）を使用しているか")
    lines.append("")

    lines.append("### D-4. 地震保険料控除")
    lines.append("- [ ] 年末調整での処理済み分を確認（源泉徴収票「地震保険料の控除額」欄）")
    lines.append("- [ ] 火災保険料は対象外（地震保険料のみ）")
    lines.append("")

    lines.append("### D-5. 寄附金控除（ふるさと納税等）")
    lines.append("- [ ] 寄附金受領証明書/XMLを全件取得済みか")
    lines.append("- [ ] ワンストップ特例申請済みでも、確定申告する場合は無効になる")
    lines.append("- [ ] 全ての寄附先が含まれているか")
    lines.append("")

    lines.append("### D-6. 配偶者控除・扶養控除")
    lines.append("- [ ] 配偶者の所得確認（No.1191, No.1195）")
    lines.append("- [ ] 16歳以上の扶養親族の有無（No.1145, No.1177）")
    lines.append("")

    lines.append("### D-7. 住宅ローン控除")
    lines.append("- [ ] 初年度は確定申告が必要（No.1211-1）")
    lines.append("- [ ] 2年目以降は年末調整で処理済みか確認")
    lines.append("")

    lines.append("### D-8. その他")
    lines.append("- [ ] 基礎控除: 所得2,400万円以下なら48万円（No.1199）")
    lines.append("- [ ] 障害者控除の該当者がいるか（No.1170）")
    lines.append("- [ ] 災害減免の該当があるか")
    lines.append("")

    # E. 必要書類
    lines.append("## E. 必要書類の準備状況\n")
    lines.append("- [ ] 源泉徴収票（勤務先から受領済み）")
    lines.append("- [ ] マイナンバーカード（e-Tax利用に必要）")
    lines.append("- [ ] 各種控除証明書（上記D項で必要な証明書）")
    lines.append("- [ ] 還付金の振込先口座情報")
    lines.append("")

    # F. 復興特別所得税
    lines.append("## F. その他\n")
    lines.append("- [ ] 復興特別所得税（所得税額×2.1%）が加算されることを認識している")
    lines.append("")

    lines.append("---\n")
    lines.append("## 次のアクション\n")

    # 要対応項目のリスト
    actions = []
    if coverage["status"] == "no_json":
        actions.append("1. `/scan-receipts` で領収書をJSON化する")
    if mynaportal["status"] == "missing":
        actions.append("1. マイナポータルから医療費通知データを取得する")
    if medical["status"] == "below_threshold":
        actions.append("1. 医療費合計が10万円以下です。交通費等の追加計上を検討してください")

    if actions:
        lines.append("**要対応:**\n")
        for a in actions:
            lines.append(a)
    else:
        lines.append("データ準備は完了しています。上記の手動確認項目をチェックした後、")
        lines.append("`output/etax_entry_guide.md` に従ってe-Tax入力を開始してください。")

    return "\n".join(lines)


def run(year_dir: Path, year_label: str) -> None:
    """パイプラインから呼ばれるエントリポイント。"""
    output_dir = year_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    checklist = generate_checklist(year_dir, year_label)
    output_path = output_dir / "prefiling_checklist.md"
    output_path.write_text(checklist, encoding="utf-8")

    print(f"プレファイリングチェックリストを {output_path} に生成しました")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.prefiling_check 2025_R7")
        sys.exit(1)

    year_label = sys.argv[1]
    year_dir = BASE / "years" / year_label
    if not year_dir.exists():
        print(f"Error: {year_dir} が見つかりません")
        sys.exit(1)

    run(year_dir, year_label)
