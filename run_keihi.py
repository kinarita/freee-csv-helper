#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_CSV = PROJECT_ROOT / "combined_clean.csv"
PROCESS_SCRIPT = PROJECT_ROOT / "process_keihi.py"


def run_command(cmd, cwd=None):
    print()
    print("▶ " + " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"エラー: {' '.join(str(x) for x in cmd)}")
        sys.exit(result.returncode)


def main():
    print("==== freee 経費処理 ====")

    if not PROCESS_SCRIPT.exists():
        print(f"エラー: process_keihi.py が見つかりません: {PROCESS_SCRIPT}")
        sys.exit(1)

    if not INPUT_CSV.exists():
        print(f"エラー: combined_clean.csv が見つかりません: {INPUT_CSV}")
        print("先に run_merge.py を実行して、対象チェック・備考を確認してください。")
        sys.exit(1)

    run_command(
        ["python3", str(PROCESS_SCRIPT), str(INPUT_CSV)],
        cwd=PROJECT_ROOT
    )

    print()
    print("==== 完了 ====")
    print("process_keihi.py の処理が終了しました。")


if __name__ == "__main__":
    main()
