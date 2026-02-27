"""
確定申告パイプライン オーケストレータ

全ステージを順に実行する。個別ステージの実行も可能。

Usage:
    python -m src.pipeline 2025_R7              # 全ステージ実行
    python -m src.pipeline 2025_R7 --stage 5    # Stage 5 のみ実行
    python -m src.pipeline 2025_R7 --from 3     # Stage 3 以降を実行

Stages:
    0: organize_sources    — ソースファイル整理・マニフェスト生成
    1: merge_batches       — バッチJSON統合 → receipts.json
    2: match_and_judge     — 領収書 × マイナポータル突合・判定
    3: apply_confirmations — ユーザー確認反映
    4: generate_xlsx       — 医療費集計フォーム生成
    5: generate_reports    — 証跡レポート一括生成
    6: prefiling_check     — NTA QAベース事前チェックリスト

Note:
    Stage 0.5 (scan-receipts) は Claude Code スキルとして実行。
    /scan-receipts [year_label] で領収書PDF→バッチJSON変換を行う。
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def resolve_year_dir(year_label: str) -> Path:
    year_dir = BASE / "years" / year_label
    if not year_dir.exists():
        print(f"Error: {year_dir} が見つかりません")
        sys.exit(1)
    return year_dir


STAGES = [
    (0, "organize_sources",    "ソースファイル整理・マニフェスト生成"),
    (1, "merge_batches",       "バッチJSON統合"),
    (2, "match_and_judge",     "突合・判定"),
    (3, "apply_confirmations", "ユーザー確認反映"),
    (4, "generate_xlsx",       "医療費集計フォーム生成"),
    (5, "generate_reports",    "証跡レポート一括生成"),
    (6, "prefiling_check",     "NTA QAベース事前チェックリスト"),
]


def run_stage(stage_num: int, year_dir: Path, year_label: str) -> None:
    _, module_name, description = STAGES[stage_num]
    print(f"\n{'='*60}")
    print(f"Stage {stage_num}: {description}")
    print(f"{'='*60}")

    module = importlib.import_module(f"src.{module_name}")
    module.run(year_dir, year_label)


def main():
    parser = argparse.ArgumentParser(description="確定申告パイプライン")
    parser.add_argument("year_label", help="年度ラベル (例: 2025_R7)")
    parser.add_argument("--stage", type=int, help="特定ステージのみ実行")
    parser.add_argument("--from", dest="from_stage", type=int, default=0,
                        help="指定ステージ以降を実行")
    args = parser.parse_args()

    year_dir = resolve_year_dir(args.year_label)

    if args.stage is not None:
        run_stage(args.stage, year_dir, args.year_label)
    else:
        for stage_num, _, _ in STAGES:
            if stage_num >= args.from_stage:
                run_stage(stage_num, year_dir, args.year_label)

    print(f"\n{'='*60}")
    print("パイプライン完了")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
