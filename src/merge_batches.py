"""
バッチJSONの統合 (Stage 1)

years/YYYY_RX/data/batches/batch_*.json を読み込み、receipts.json に統合する。
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def run(year_dir: Path, year_label: str) -> None:
    batches_dir = year_dir / "data" / "batches"
    output_path = year_dir / "data" / "receipts.json"

    all_receipts = []
    batch_files = sorted(batches_dir.glob("batch_*.json"))

    if not batch_files:
        print("バッチファイルが見つかりません")
        return

    for bf in batch_files:
        data = json.loads(bf.read_text("utf-8"))
        if isinstance(data, list):
            all_receipts.extend(data)
        else:
            all_receipts.append(data)
        print(f"  {bf.name}: {len(data) if isinstance(data, list) else 1}件")

    # ID重複チェック
    ids = [r["id"] for r in all_receipts]
    dupes = [x for x in set(ids) if ids.count(x) > 1]
    if dupes:
        print(f"  警告: ID重複あり: {dupes}")

    all_receipts.sort(key=lambda r: r["id"])

    output_path.write_text(
        json.dumps(all_receipts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"統合完了: {output_path}")
    print(f"総件数: {len(all_receipts)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.merge_batches 2025_R7")
        sys.exit(1)
    year_dir = BASE / "years" / sys.argv[1]
    run(year_dir, sys.argv[1])


if __name__ == "__main__":
    main()
