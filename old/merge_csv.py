#!/usr/bin/env python3
import sys
import re
from pathlib import Path
import pandas as pd

# 全角→半角（数字/記号）
FW_TO_HW = str.maketrans({
    "０":"0","１":"1","２":"2","３":"3","４":"4","５":"5","６":"6","７":"7","８":"8","９":"9",
    "／":"/","－":"-","　":" ",  # 全角スラッシュ/全角ハイフン/全角スペース
})

def normalize_jp_date(s):
    """例: '２０２４年１１月１日' / '2024年11月1日' / '2024/11/1' -> Timestamp or NaT"""
    if pd.isna(s):
        return pd.NaT
    s = str(s).strip().translate(FW_TO_HW)

    # "YYYY年MM月DD日" を "YYYY-MM-DD" にする
    s = s.replace("年", "-").replace("月", "-").replace("日", "")
    s = s.replace("/", "-")
    s = re.sub(r"\s+", "", s)

    # 2024-11-1 のような形式もOKにする
    try:
        return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    except Exception:
        return pd.to_datetime(s, errors="coerce")

def parse_yen_amount(x):
    """例: '"4,277"' / '4,277' / 4277 -> 4277"""
    if pd.isna(x):
        return pd.NA
    s = str(x).strip().replace('"', "").replace(",", "").replace("−", "-")
    return pd.to_numeric(s, errors="coerce")

def main(folder):
    folder = Path(folder)
    csv_files = sorted(folder.glob("*.csv"))

    if not csv_files:
        print("CSVファイルが見つかりません")
        return 2

    frames = []
    for f in csv_files:
        print("読み込み:", f.name)
        # 日本のカードCSVはcp932が一番安定
        df = pd.read_csv(f, encoding="cp932", dtype=str)
        df["source_file"] = f.name
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # 余計な行削除（【成田 仁俊 様】など）
    if "確定情報" in combined.columns:
        combined["確定情報"] = combined["確定情報"].fillna("").astype(str).str.strip()
        combined = combined[combined["確定情報"].isin(["確定", "未確定", "取消"])].copy()

    # 日付を確実に変換
    if "ご利用日" in combined.columns:
        combined["ご利用日"] = combined["ご利用日"].apply(normalize_jp_date)
    if "お支払日" in combined.columns:
        combined["お支払日"] = combined["お支払日"].apply(normalize_jp_date)

    # 金額を数値化（カンマ除去）
    if "ご利用金額（円）" in combined.columns:
        combined["ご利用金額（円）"] = combined["ご利用金額（円）"].apply(parse_yen_amount)

    # 利用日でソート
    if "ご利用日" in combined.columns:
        combined = combined.sort_values("ご利用日", na_position="last")

    # 出力
    out_csv = folder / "combined_clean.csv"
    combined.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print("完了:", out_csv)

    # 変換できなかった利用日があれば件数表示（チェック用）
    if "ご利用日" in combined.columns:
        bad = combined["ご利用日"].isna().sum()
        print("ご利用日が空(NaT)の行数:", bad)

    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: ./merge_csv.py folder")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
