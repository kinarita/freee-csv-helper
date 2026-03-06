#!/usr/bin/env python3
import sys
import pandas as pd

def main():
    if len(sys.argv) < 2:
        print("使い方: ./review_queue.py need_review.csv")
        sys.exit(1)

    f = sys.argv[1]
    df = pd.read_csv(f, encoding="utf-8-sig")

    # 店名別：件数と合計金額
    q = (
        df.groupby("内容")
        .agg(件数=("金額", "count"), 合計金額=("金額", "sum"))
        .sort_values(["合計金額", "件数"], ascending=False)
        .reset_index()
    )
    q.to_csv("need_review_by_shop.csv", index=False, encoding="utf-8-sig")
    print("作成: need_review_by_shop.csv")

if __name__ == "__main__":
    main()
