#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
MEISAI_DIR = PROJECT_ROOT / "meisai"
MERGE_SCRIPT = PROJECT_ROOT / "merge_csv.py"


def run_command(cmd, cwd=None):
    print()
    print("▶ " + " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"エラー: {' '.join(str(x) for x in cmd)}")
        sys.exit(result.returncode)


def main():
    print("==== freee 明細マージ ====")

    if not MERGE_SCRIPT.exists():
        print(f"エラー: merge_csv.py が見つかりません: {MERGE_SCRIPT}")
        sys.exit(1)

    if not MEISAI_DIR.exists():
        print(f"エラー: meisai ディレクトリが見つかりません: {MEISAI_DIR}")
        sys.exit(1)

    run_command(
        ["python3", str(MERGE_SCRIPT), str(MEISAI_DIR)],
        cwd=PROJECT_ROOT
    )

    combined_clean = PROJECT_ROOT / "combined_clean.csv"

    print()
    print("==== 完了 ====")
    if combined_clean.exists():
        print(f"生成済み: {combined_clean}")
        print("次の作業:")
        print("1. combined_clean.csv を Excel 等で開く")
        print("2. 対象チェック 列に 1 を入れる")
        print("3. 必要なら 備考 列を追記する")
        print("4. その後 run_keihi.py を実行する")
    else:
        print("警告: combined_clean.csv が見つかりません。merge_csv.py の結果を確認してください。")


if __name__ == "__main__":
    main()
