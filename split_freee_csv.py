#!/usr/bin/env python3
import sys
from pathlib import Path
import pandas as pd

def write_excel(out_xlsx: Path, sheets: dict):
    # openpyxlは環境にある前提（pandasが内部利用）
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
        for name, df in sheets.items():
            # freeeが読みやすいように列順を固定（念のため）
            cols = ["取引日", "勘定科目", "金額", "内容", "メモ"]
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            df = df[cols].copy()

            # 取引日は文字列のまま（YYYY-MM-DD）でOK。Excelで勝手に日付化しても問題なし
            df.to_excel(w, sheet_name=name, index=False)

def main():
    if len(sys.argv) < 2:
        print("使い方: ./split_freee_csv.py freee_import.csv")
        sys.exit(1)

    f = Path(sys.argv[1])
    df = pd.read_csv(f, encoding="utf-8-sig", dtype=str)

    # 金額だけ数値に寄せたい場合（任意）
    if "金額" in df.columns:
        df["金額"] = pd.to_numeric(df["金額"], errors="coerce")

    # 1) 資産
    asset = df[df["勘定科目"] == "工具器具備品"].copy()
    asset.to_csv("freee_import_asset.csv", index=False, encoding="utf-8-sig")

    # 2) 開業費
    startup = df[df["勘定科目"] == "開業費"].copy()
    startup.to_csv("freee_import_startup.csv", index=False, encoding="utf-8-sig")

    # 3) 通常経費（上記以外）
    expense = df[~df["勘定科目"].isin(["工具器具備品", "開業費"])].copy()
    expense.to_csv("freee_import_expense.csv", index=False, encoding="utf-8-sig")

    # ★ 追加：Excel出力（freee取り込み用）
    write_excel(Path("freee_import_asset.xlsx"), {"asset": asset})
    write_excel(Path("freee_import_startup.xlsx"), {"startup": startup})
    write_excel(Path("freee_import_expense.xlsx"), {"expense": expense})

    # お好み：3シート1冊にもできる（こっちが使いやすい人が多い）
    write_excel(Path("freee_import_split_all.xlsx"), {
        "asset": asset,
        "startup": startup,
        "expense": expense,
    })

    print("作成: freee_import_asset.csv", len(asset))
    print("作成: freee_import_startup.csv", len(startup))
    print("作成: freee_import_expense.csv", len(expense))
    print("作成: freee_import_asset.xlsx / startup.xlsx / expense.xlsx")
    print("作成: freee_import_split_all.xlsx")

if __name__ == "__main__":
    main()