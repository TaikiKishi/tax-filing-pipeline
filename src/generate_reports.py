"""
証跡レポート一括生成 (Stage 5)

generate_report.py と generate_checklist.py を統合的に実行する。

出力:
    - judgment_report.md       — 全件の判定根拠一覧
    - tax_summary.md           — 確定申告全体サマリー
    - verification_checklist.md — 照合チェックリスト
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load_data(data_dir: Path):
    match_data = json.loads((data_dir / "match_results.json").read_text("utf-8"))
    mynaportal = json.loads((data_dir / "mynaportal.json").read_text("utf-8"))
    receipts = json.loads((data_dir / "receipts.json").read_text("utf-8"))
    return match_data, mynaportal, receipts


def run(year_dir: Path, year_label: str) -> None:
    """パイプラインから呼ばれるエントリポイント。"""
    data_dir = year_dir / "data"
    output_dir = year_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    match_data, mynaportal, receipts = load_data(data_dir)

    from src.generate_report import generate_judgment_report, generate_tax_summary
    generate_judgment_report(match_data, output_dir, year_label)
    generate_tax_summary(match_data, mynaportal, data_dir, output_dir, year_label)

    from src.generate_checklist import generate_checklist
    generate_checklist(match_data, receipts, mynaportal, output_dir, year_dir, year_label)


def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.generate_reports 2025_R7")
        sys.exit(1)
    year_dir = BASE / "years" / sys.argv[1]
    run(year_dir, sys.argv[1])


if __name__ == "__main__":
    main()
