#!/usr/bin/env python3
"""
process_keihi.py (final, stable)

- 対象チェック=1 を抽出
- 店名/メモで勘定科目を自動付与（RULES + 特例）
- 開業日(OPEN_DATE)より前の支出を「開業費」に振替（ただし資産=工具器具備品は除外）
- freee_import.csv / need_review.csv / store_summary_with_account.csv を出力

使い方:
  chmod +x process_keihi.py
  ./process_keihi.py meisai/combined_clean.csv
"""

import sys
import re
import datetime
import pandas as pd


# -------------------------
# 表記ゆれ吸収（全角英数→半角、スペース正規化）
# -------------------------
_ZEN = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
_HAN = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_TRANS = str.maketrans(_ZEN, _HAN)

def norm_text(s: str) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    s = s.replace("\u3000", " ")           # 全角スペース→半角
    s = s.translate(_TRANS)                # 全角英数→半角
    s = re.sub(r"\s+", " ", s).strip()     # 連続空白→1つ
    return s


# -------------------------
# 店名→勘定科目（部分一致・上から優先）
# -------------------------
RULES = [
    # --- クラウド / SaaS（通信費） ---
    (["AMAZON WEB SERV", "AMAZON WEB SERVI", "AWS", "AWS SERVICES"], "通信費"),
    (["OPENAI", "CHATGPT"], "通信費"),
    (["CLAUDE.AI", "CLAUDE"], "通信費"),
    (["1PASSWORD"], "通信費"),
    (["XSERVER", "エックスサーバ"], "通信費"),
    (["エックスサ－バ－／M", "エックスサーバー／M", "エックスサ-バ-／M"], "通信費"),
    (["CONOHA", "コノハ"], "通信費"),
    (["FLY.IO", "FLYIO"], "通信費"),
    (["VALUE DOMAIN", "VALUEDOMAIN", "バリュードメイン", "バリユードメイン"], "通信費"),
    (["REPLIT"], "通信費"),
    (["GOOGLE ONE"], "通信費"),
    (["日本通信"], "通信費"),
    (["AU電話", "AU 電話"], "通信費"),

    # --- 会計ソフト（支払手数料） ---
    (["FREEE", "ｆｒｅｅｅ", "freee"], "支払手数料"),

    # --- 情報収集（新聞図書費） ---
    (["TRADINGVIEW"], "新聞図書費"),
    (["日経ID", "日経ＩＤ", "NIKKEI"], "新聞図書費"),
    (["INVESTORS BUSINESS", "INVESTOR'S BUSINESS"], "新聞図書費"),
    (["MEDIUM"], "新聞図書費"),
    (["テレビ東京"], "新聞図書費"),
    (["Dマガジン", "dマガジン", "DMAGAZINE"], "新聞図書費"),
    (["LINKEDIN"], "新聞図書費"),

    # 書籍・書店（新聞図書費）
    (["BOOKOFF", "ＢＯＯＫＯＦＦ"], "新聞図書費"),
    (["TSUTAYA", "ＴＳＵＴＡＹＡ"], "新聞図書費"),
    (["紀伊國屋", "紀伊国屋", "キノクニヤ"], "新聞図書費"),
    (["くまざわ", "クマザワ"], "新聞図書費"),
    (["丸善", "マルゼン", "ジュンク堂", "ジュンクドウ"], "新聞図書費"),
    (["ときわ書房", "トキワ書房"], "新聞図書費"),
    (["そごう", "西武"], "新聞図書費"),

    # --- 研修・資格（研修費） ---
    (["COURSERA"], "研修費"),
    (["JDLA", "ＪＤＬＡ"], "研修費"),
    (["オデッセイ"], "研修費"),

    # --- 機材・部材・文具（消耗品費） ---
    (["JP.PLAUD.AI", "PLAUD"], "消耗品費"),
    (["秋月電子"], "消耗品費"),
    (["IKEA", "イケア"], "消耗品費"),
    (["世界堂"], "消耗品費"),
    (["無印", "ムジルシ", "無印良品"], "消耗品費"),
    (["イトーヨーカドー", "ヨーカドー"], "消耗品費"),
    (["ダイソー"], "消耗品費"),

    # --- 中古・フリマ（基本は消耗品費。メモで資産判定へ上書きあり） ---
    (["メルカリ", "MERCARI"], "消耗品費"),

    # --- Appleはメモで分岐（ここでは要確認に落として特例で確定） ---
    (["APPLE.COM", "APPLE", "ＡＰＰＬＥ", "ＡＰＰＬＥ．ＣＯＭ"], "要確認"),
]


def pick_account(shop: str, memo: str) -> str:
    """
    基本は RULES で決める（部分一致）。
    ただし、以下はメモで上書きして確定させる:
      - Apple（iPad=工具器具備品 / Developer=通信費）
      - メルカリ（PC/パソコン/スピーカー=工具器具備品）
      - トレジャーファク（スピーカー等=消耗品費）
    """
    shop_n = norm_text(shop)
    memo_n = norm_text(memo)

    # PayPay経由のトレジャーファク（表記ゆれを確実に潰す）
    if "トレジャーファク" in shop_n or "トレジャーファクト" in shop_n:
        return "消耗品費"

    # Apple：メモで確定
    if "APPLE" in shop_n.upper() or "ＡＰＰＬＥ" in shop_n:
        m = memo_n.lower()
        if "developer" in m:
            return "通信費"
        if "ipad" in m:
            return "工具器具備品"
        return "要確認"

    # メルカリ：メモで資産判定
    if "メルカリ" in shop_n or "MERCARI" in shop_n.upper():
        m = memo_n.lower()
        if ("pc" in m) or ("パソコン" in memo_n) or ("スピーカー" in memo_n):
            return "工具器具備品"
        return "消耗品費"

    # 通常ルール
    shop_upper = shop_n.upper()
    for keywords, account in RULES:
        for k in keywords:
            if norm_text(k).upper() in shop_upper:
                return account

    return "要確認"


def to_int_flag(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def main():
    if len(sys.argv) < 2:
        print("使い方: ./process_keihi.py meisai/combined_clean.csv")
        sys.exit(1)

    input_file = sys.argv[1]
    print(f"読み込み: {input_file}")

    df = pd.read_csv(input_file, encoding="utf-8-sig")

    col_check  = "対象チェック"
    col_shop   = "ご利用店名（海外ご利用店名／海外都市名）"
    col_date   = "ご利用日"
    col_amount = "ご利用金額（円）"
    col_memo   = "備考"

    # 対象抽出
    df[col_check] = to_int_flag(df[col_check])
    keihi = df[df[col_check] == 1].copy()

    # 正規化
    keihi[col_shop] = keihi[col_shop].apply(norm_text)
    if col_memo in keihi.columns:
        keihi[col_memo] = keihi[col_memo].apply(norm_text)
    else:
        keihi[col_memo] = ""

    # 金額
    keihi[col_amount] = (
        keihi[col_amount].astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    keihi[col_amount] = pd.to_numeric(keihi[col_amount], errors="coerce")

    # 日付（YYYY-MM-DDへ）
    keihi[col_date] = pd.to_datetime(keihi[col_date], errors="coerce").dt.date.astype(str)

    # 勘定科目付与
    keihi["勘定科目"] = keihi.apply(lambda r: pick_account(r[col_shop], r[col_memo]), axis=1)

    # freee用
    freee = pd.DataFrame({
        "取引日": keihi[col_date],
        "勘定科目": keihi["勘定科目"],
        "金額": keihi[col_amount],
        "内容": keihi[col_shop],
        "メモ": keihi[col_memo],
    })

    # -------------------------
    # 開業費変換（資産は除外）
    # -------------------------
    OPEN_DATE = datetime.date(2025, 10, 1)

    d = pd.to_datetime(freee["取引日"], errors="coerce").dt.date
    is_before_open = d < OPEN_DATE
    is_asset = freee["勘定科目"] == "工具器具備品"

    freee.loc[is_before_open & ~is_asset, "勘定科目"] = "開業費"

    # 出力
    freee.to_csv("freee_import.csv", index=False, encoding="utf-8-sig")
    print("作成: freee_import.csv")

    need = freee[freee["勘定科目"] == "要確認"].copy()
    need.to_csv("need_review.csv", index=False, encoding="utf-8-sig")
    print("作成: need_review.csv（要確認のみ）")

    summary = (
        keihi.groupby([col_shop, "勘定科目"])[col_amount]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={col_amount: "合計金額"})
    )
    summary.to_csv("store_summary_with_account.csv", index=False, encoding="utf-8-sig")
    print("作成: store_summary_with_account.csv")

    print("\n件数:")
    print("  経費対象:", len(freee))
    print("  要確認:", len(need))
    print("  OK:", len(freee) - len(need))


if __name__ == "__main__":
    main()
