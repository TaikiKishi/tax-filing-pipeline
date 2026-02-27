"""
ソースファイル整理・リネーム・マニフェスト生成 (Stage 0)

スキャン済み領収書PDF、補填書類、マイナポータル出力等を
意味のあるファイル名にリネームして years/YYYY_RX/sources/ に配置し、
manifest.json (原本名→保存名→receipt_id の対応表) を生成する。

Usage:
    python -m src.organize_sources 2025_R7
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def resolve_year_dir(year_label: str) -> Path:
    year_dir = BASE / "years" / year_label
    if not year_dir.exists():
        raise FileNotFoundError(f"Year directory not found: {year_dir}")
    return year_dir


def load_source_config(year_dir: Path) -> dict:
    """年度ディレクトリの source_config.json を読み込む。
    なければデフォルト設定を返す。"""
    config_path = year_dir / "source_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text("utf-8"))
    return {
        "scanner_prefix": "",
        "import_dirs": [],
        "import_file_maps": {},
        "reimbursement_files": {},
    }


def build_receipt_file_map(year_dir: Path, config: dict) -> dict[str, Path]:
    """receipt_id → 元のPDFパス のマッピングを構築。"""
    mapping: dict[str, Path] = {}
    scanner_prefix = config.get("scanner_prefix", "")

    for import_dir_str in config.get("import_dirs", []):
        import_dir = Path(import_dir_str)
        if not import_dir.is_absolute():
            import_dir = BASE / import_dir_str
        if import_dir.exists():
            for pdf in import_dir.glob("*.pdf"):
                name = pdf.stem
                if scanner_prefix and name.startswith(scanner_prefix):
                    receipt_id = name[len(scanner_prefix):]
                    mapping[receipt_id] = pdf

    # import_file_maps: 個別ファイルの receipt_id マッピング
    for rid, fname in config.get("import_file_maps", {}).items():
        for import_dir_str in config.get("import_dirs", []):
            import_dir = Path(import_dir_str)
            if not import_dir.is_absolute():
                import_dir = BASE / import_dir_str
            fpath = import_dir / fname
            if fpath.exists():
                mapping[rid] = fpath
                break

    return mapping


def sanitize_filename(s: str, max_len: int = 30) -> str:
    """ファイル名に使えない文字を除去し、長さを制限。"""
    for ch in '/\\:*?"<>|':
        s = s.replace(ch, "")
    return s[:max_len].strip()


def organize_receipts(year_dir: Path, receipts: list[dict],
                      file_map: dict[str, Path]) -> list[dict]:
    """領収書PDFをリネームして sources/receipts/ に配置。"""
    dest_dir = year_dir / "sources" / "receipts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    counter = 1

    for r in sorted(receipts, key=lambda x: (x.get("date", ""), x["id"])):
        rid = r["id"]
        src_path = file_map.get(rid)
        if not src_path or not src_path.exists():
            continue

        patient = sanitize_filename(r.get("patient", "不明"))
        facility = sanitize_filename(r.get("facility", "不明"), 20)
        dt = r.get("date", "unknown")
        ext = src_path.suffix

        stored_name = f"MED-{counter:03d}_{dt}_{patient}_{facility}{ext}"
        dest_path = dest_dir / stored_name

        if not dest_path.exists():
            shutil.copy2(src_path, dest_path)

        entries.append({
            "id": f"MED-{counter:03d}",
            "type": "receipt",
            "original_name": src_path.name,
            "stored_path": f"sources/receipts/{stored_name}",
            "receipt_id": rid,
            "patient": r.get("patient", ""),
            "facility": r.get("facility", ""),
            "date": dt,
        })
        counter += 1

    return entries


def organize_reimbursements(year_dir: Path, config: dict) -> list[dict]:
    """補填書類をリネームして sources/reimbursements/ に配置。"""
    reimb_file = year_dir / "data" / "reimbursements.json"
    if not reimb_file.exists():
        return []

    reimbursements = json.loads(reimb_file.read_text("utf-8"))
    dest_dir = year_dir / "sources" / "reimbursements"
    dest_dir.mkdir(parents=True, exist_ok=True)
    entries = []

    # 設定ファイルからソースファイルマッピングを取得
    source_files = {}
    for name, path_str in config.get("reimbursement_files", {}).items():
        p = Path(path_str)
        if not p.is_absolute():
            p = BASE / path_str
        source_files[name] = p

    for i, r in enumerate(reimbursements, 1):
        source_name = r.get("source", "")
        src_path = source_files.get(source_name)
        if not src_path or not src_path.exists():
            for f in dest_dir.iterdir():
                if source_name.replace(" ", "") in f.name.replace(" ", ""):
                    entries.append({
                        "id": f"RMB-{i:03d}",
                        "type": "reimbursement",
                        "original_name": f.name,
                        "stored_path": f"sources/reimbursements/{f.name}",
                        "source": source_name,
                        "amount": r["amount"],
                        "date": r.get("date", ""),
                    })
                    break
            continue

        dt = r.get("date", "unknown")
        source_short = sanitize_filename(source_name, 25)
        ext = src_path.suffix
        stored_name = f"RMB-{i:03d}_{dt}_{source_short}{ext}"
        dest_path = dest_dir / stored_name

        if not dest_path.exists():
            shutil.copy2(src_path, dest_path)

        entries.append({
            "id": f"RMB-{i:03d}",
            "type": "reimbursement",
            "original_name": src_path.name,
            "stored_path": f"sources/reimbursements/{stored_name}",
            "source": source_name,
            "amount": r["amount"],
            "date": dt,
        })

    return entries


def organize_directory(year_dir: Path, subdir: str, prefix: str, file_type: str) -> list[dict]:
    """汎用ディレクトリ整理。"""
    src_dir = year_dir / "sources" / subdir
    entries = []
    for i, f in enumerate(sorted(src_dir.glob("*")), 1):
        if f.is_file():
            entries.append({
                "id": f"{prefix}-{i:03d}",
                "type": file_type,
                "original_name": f.name,
                "stored_path": f"sources/{subdir}/{f.name}",
            })
    return entries


def generate_manifest(year_dir: Path, year_label: str) -> None:
    """全ソースファイルを整理し manifest.json を生成。"""
    data_dir = year_dir / "data"
    receipts_file = data_dir / "receipts.json"
    config = load_source_config(year_dir)

    receipts = json.loads(receipts_file.read_text("utf-8")) if receipts_file.exists() else []
    file_map = build_receipt_file_map(year_dir, config)

    all_entries = []
    all_entries.extend(organize_receipts(year_dir, receipts, file_map))
    all_entries.extend(organize_reimbursements(year_dir, config))

    for subdir, prefix, ftype in [
        ("mynaportal", "MYN", "mynaportal"),
        ("social_insurance", "SOC", "social_insurance"),
        ("other", "OTH", "other"),
    ]:
        src_dir = year_dir / "sources" / subdir
        if src_dir.exists():
            all_entries.extend(organize_directory(year_dir, subdir, prefix, ftype))

    parts = year_label.split("_")
    fiscal_year = parts[0] if len(parts) >= 1 else year_label
    era = parts[1] if len(parts) >= 2 else ""

    manifest = {
        "fiscal_year": fiscal_year,
        "era": era,
        "year_label": year_label,
        "created": date.today().isoformat(),
        "files": all_entries,
    }

    manifest_path = year_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    by_type = {}
    for e in all_entries:
        t = e["type"]
        by_type[t] = by_type.get(t, 0) + 1

    print(f"manifest.json を {manifest_path} に生成しました")
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}件")
    print(f"  合計: {len(all_entries)}件")


def run(year_dir: Path, year_label: str) -> None:
    """パイプラインから呼ばれるエントリポイント。"""
    generate_manifest(year_dir, year_label)


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.organize_sources 2025_R7")
        sys.exit(1)

    year_label = sys.argv[1]
    year_dir = resolve_year_dir(year_label)
    run(year_dir, year_label)


if __name__ == "__main__":
    main()
