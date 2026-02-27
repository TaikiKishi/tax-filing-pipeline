"""
generate_invoice.py — 請求書 Markdown 生成

misc_income.json の income エントリから請求書 Markdown を生成する。
pandoc + XeLaTeX (invoice プロファイル) で PDF に変換可能。

Usage:
    python3 -m src.generate_invoice 2025_R7                     # 未生成分を一括生成
    python3 -m src.generate_invoice 2025_R7 --ref 20251127001   # 指定 reference_id のみ
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, datetime
from pathlib import Path


def load_misc_income(data_dir: Path) -> dict:
    """misc_income.json を読み込む。"""
    path = data_dir / "misc_income.json"
    if not path.exists():
        print(f"ERROR: {path} が見つかりません")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_misc_income(data_dir: Path, data: dict) -> None:
    """misc_income.json を保存する。"""
    path = data_dir / "misc_income.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def ensure_reference_id(entry: dict, index: int) -> str:
    """reference_id がなければ date + 連番から生成する。"""
    if entry.get("reference_id"):
        return entry["reference_id"]
    d = entry.get("date", "")
    if d:
        ref = d.replace("-", "") + f"{index + 1:03d}"
    else:
        ref = f"NODATE{index + 1:03d}"
    entry["reference_id"] = ref
    return ref


def calc_due_date(invoice_date: date) -> date:
    """請求日の翌月末を返す。"""
    if invoice_date.month == 12:
        next_year, next_month = invoice_date.year + 1, 1
    else:
        next_year, next_month = invoice_date.year, invoice_date.month + 1
    last_day = calendar.monthrange(next_year, next_month)[1]
    return date(next_year, next_month, last_day)


def format_amount(amount: int) -> str:
    """金額をカンマ区切りで返す。"""
    return f"{amount:,}"


def generate_invoice_md(
    year_dir: Path,
    year_label: str,
    entry: dict,
    issuer: dict,
) -> Path:
    """1件の請求書 Markdown を生成し、出力パスを返す。"""
    ref_id = entry["reference_id"]
    out_dir = year_dir / "output" / "invoices"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"INV-{ref_id}.md"

    # 日付
    invoice_date = date.fromisoformat(entry["date"])
    due_date = calc_due_date(invoice_date)

    # 金額
    amount = entry["amount"]
    withholding = entry.get("withholding", 0)
    net_amount = amount - withholding

    # 発行者情報
    issuer_name = issuer.get("name", "")
    issuer_postal = issuer.get("postal_code", "")
    issuer_address = issuer.get("address", "")
    issuer_email = issuer.get("email", "")
    bank = issuer.get("bank", {})

    # Markdown 生成
    lines = []

    # タイトル
    lines.append(r"\begin{center}")
    lines.append(r"{\LARGE\textbf{請　求　書}}")
    lines.append(r"\end{center}")
    lines.append("")
    lines.append(r"\vspace{5mm}")
    lines.append("")

    # 請求書番号・日付（右寄せ）
    lines.append(r"\begin{flushright}")
    lines.append(f"請求書番号: INV-{ref_id}" + r"\\")
    lines.append(f"発行日: {invoice_date.isoformat()}" + r"\\")
    lines.append(r"\end{flushright}")
    lines.append("")
    lines.append(r"\vspace{3mm}")
    lines.append("")

    # 宛先
    payer = entry.get("payer", "")
    payer_address = entry.get("payer_address", "")
    lines.append(f"**{payer}** 御中")
    if payer_address:
        lines.append(f"\\")
        lines.append(payer_address)
    lines.append("")
    lines.append(r"\vspace{5mm}")
    lines.append("")

    # 件名
    description = entry.get("notes", entry.get("income_type", ""))
    lines.append(f"下記の通りご請求申し上げます。")
    lines.append("")
    lines.append(r"\vspace{3mm}")
    lines.append("")

    # 合計金額（目立たせる）
    lines.append(r"\begin{center}")
    lines.append(r"{\Large\textbf{ご請求金額: ¥" + format_amount(net_amount) + r"}}")
    lines.append(r"\end{center}")
    lines.append("")
    lines.append(r"\vspace{5mm}")
    lines.append("")

    # 明細テーブル
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tabular}{l R{30mm} R{30mm} R{30mm}}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{項目} & \textbf{金額} & \textbf{源泉徴収} & \textbf{差引請求額} \\")
    lines.append(r"\midrule")
    lines.append(
        f"{description} & ¥{format_amount(amount)} & ¥{format_amount(withholding)} & ¥{format_amount(net_amount)} " + r"\\"
    )
    lines.append(r"\midrule")
    lines.append(r"\textbf{合計} & \textbf{¥" + format_amount(amount) + r"} & \textbf{¥" + format_amount(withholding) + r"} & \textbf{¥" + format_amount(net_amount) + r"} \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")
    lines.append("")
    lines.append(r"\vspace{5mm}")
    lines.append("")

    # 支払条件
    lines.append("## お支払い条件")
    lines.append("")
    lines.append(f"- **お支払期限**: {due_date.isoformat()}")
    lines.append("")

    # 振込先
    lines.append("## お振込先")
    lines.append("")
    if bank:
        lines.append(f"| | |")
        lines.append(f"|---|---|")
        lines.append(f"| 銀行名 | {bank.get('bank_name', '')} |")
        lines.append(f"| 支店名 | {bank.get('branch_name', '')} |")
        lines.append(f"| 口座種別 | {bank.get('account_type', '')} |")
        lines.append(f"| 口座番号 | {bank.get('account_number', '')} |")
        lines.append(f"| 口座名義 | {bank.get('account_holder', '')} |")
    lines.append("")
    lines.append(r"\vspace{10mm}")
    lines.append("")

    # 発行者情報（右寄せ）
    lines.append(r"\begin{flushright}")
    lines.append(issuer_name + r"\\")
    if issuer_postal:
        lines.append(f"〒{issuer_postal}" + r"\\")
    if issuer_address:
        lines.append(issuer_address + r"\\")
    if issuer_email:
        lines.append(issuer_email + r"\\")
    lines.append(r"\end{flushright}")
    lines.append("")

    content = "\n".join(lines)
    out_path.write_text(content, encoding="utf-8")
    print(f"  生成: {out_path}")
    return out_path


def generate_all_invoices(year_dir: Path, year_label: str) -> list[Path]:
    """invoice_file 未設定の全件について請求書 Markdown を生成する。"""
    data_dir = year_dir / "data"
    data = load_misc_income(data_dir)
    issuer = data.get("issuer", {})

    if not issuer or issuer.get("name", "").startswith("（"):
        print("WARNING: issuer 情報が未設定です。misc_income.json の issuer ブロックを記入してください。")

    generated = []
    modified = False

    for i, entry in enumerate(data.get("income", [])):
        # reference_id がなければ自動生成
        ref_before = entry.get("reference_id")
        ensure_reference_id(entry, i)
        if not ref_before:
            modified = True

        # 既に invoice_file がセットされていればスキップ
        if entry.get("invoice_file"):
            continue

        out_path = generate_invoice_md(year_dir, year_label, entry, issuer)
        # 相対パスで記録
        rel_path = str(out_path.relative_to(year_dir))
        entry["invoice_file"] = rel_path
        modified = True
        generated.append(out_path)

    if modified:
        save_misc_income(data_dir, data)
        print(f"  misc_income.json 更新済み")

    return generated


def generate_single_invoice(year_dir: Path, year_label: str, reference_id: str) -> Path | None:
    """指定 reference_id の請求書 Markdown を生成する。"""
    data_dir = year_dir / "data"
    data = load_misc_income(data_dir)
    issuer = data.get("issuer", {})

    for entry in data.get("income", []):
        if entry.get("reference_id") == reference_id:
            out_path = generate_invoice_md(year_dir, year_label, entry, issuer)
            rel_path = str(out_path.relative_to(year_dir))
            entry["invoice_file"] = rel_path
            save_misc_income(data_dir, data)
            print(f"  misc_income.json 更新済み")
            return out_path

    print(f"ERROR: reference_id '{reference_id}' が見つかりません")
    return None


def run(year_dir: Path, year_label: str) -> None:
    """パイプライン互換エントリーポイント。未生成分を一括生成する。"""
    print(f"=== 請求書 Markdown 生成 ({year_label}) ===")
    generated = generate_all_invoices(year_dir, year_label)
    if generated:
        print(f"\n{len(generated)} 件の請求書を生成しました")
    else:
        print("\n生成対象の請求書はありません（全件 invoice_file 設定済み）")


def main():
    parser = argparse.ArgumentParser(description="請求書 Markdown 生成")
    parser.add_argument("year_label", help="年度ラベル（例: 2025_R7）")
    parser.add_argument("--ref", help="特定の reference_id のみ生成")
    args = parser.parse_args()

    year_dir = Path("years") / args.year_label
    if not year_dir.exists():
        print(f"ERROR: {year_dir} が見つかりません")
        sys.exit(1)

    if args.ref:
        generate_single_invoice(year_dir, args.year_label, args.ref)
    else:
        run(year_dir, args.year_label)


if __name__ == "__main__":
    main()
