#!/usr/bin/env python3
"""
process_keihi.py (YAML rules, final)

- 対象チェック=1 を抽出
- 店名/メモで勘定科目を自動付与（rules.yaml）
- 開業日(open_date)より前の支出を「開業費」に振替（ただし資産=工具器具備品は除外）
- freee_import.csv / need_review.csv / store_summary_with_account.csv を出力

使い方:
  python3 process_keihi.py combined_clean.csv
  # ルールファイルを指定したい場合
  python3 process_keihi.py combined_clean.csv rules.yaml
  （通常は run_keihi.py から呼びます）
"""

import sys
import re
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# 出力は常にスクリプト所在ディレクトリ（リポジトリ直下）へ
PROJECT_ROOT = Path(__file__).resolve().parent

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML が必要です。`pip install pyyaml` を実行してください。", file=sys.stderr)
    sys.exit(1)

# -------------------------
# 表記ゆれ吸収（全角英数→半角、スペース正規化）
# -------------------------
_ZEN = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
_HAN = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_TRANS = str.maketrans(_ZEN, _HAN)

def norm_text(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    s = s.replace("\u3000", " ")           # 全角スペース→半角
    s = s.translate(_TRANS)                # 全角英数→半角
    s = re.sub(r"\s+", " ", s).strip()     # 連続空白→1つ
    return s

def to_int_flag(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)

def parse_open_date(s: str) -> datetime.date:
    # "YYYY-MM-DD" 想定
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except Exception as e:
        raise ValueError(f"open_date の形式が不正です: {s} (期待: YYYY-MM-DD)") from e

def load_rules_yaml(path: Path) -> Tuple[datetime.date, List[Dict[str, Any]], Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"rules.yaml が見つかりません: {path}")

    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    open_date = parse_open_date(cfg.get("open_date", "2025-10-01"))

    rules = cfg.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("rules は配列（list）である必要があります")

    special = cfg.get("special_cases", {})
    if not isinstance(special, dict):
        raise ValueError("special_cases は辞書（dict）である必要があります")

    # 正規化しておく（高速化＆揺れ吸収）
    for r in rules:
        r["account"] = norm_text(r.get("account", "要確認"))
        r["keywords"] = [norm_text(k) for k in (r.get("keywords") or [])]

    for _, sc in special.items():
        if not isinstance(sc, dict):
            continue
        sc["shop_keywords"] = [norm_text(k) for k in (sc.get("shop_keywords") or [])]
        sc["default"] = norm_text(sc.get("default", "要確認"))
        memo_map = sc.get("memo_map") or {}
        if isinstance(memo_map, dict):
            # キーは小文字で比較する
            sc["memo_map"] = {str(k).lower(): norm_text(v) for k, v in memo_map.items()}
        else:
            sc["memo_map"] = {}

    return open_date, rules, special

def shop_contains(shop_n: str, keywords: List[str]) -> bool:
    shop_u = shop_n.upper()
    for k in keywords:
        if not k:
            continue
        if norm_text(k).upper() in shop_u:
            return True
    return False

def apply_special_cases(shop: str, memo: str, special: Dict[str, Any]) -> Optional[str]:
    """
    special_cases の適用。
    - shop_keywords が店名に含まれたら適用
    - memo_map のキーがメモに含まれたら対応する account に確定
    - default があればそれを返す
    """
    shop_n = norm_text(shop)
    memo_n = norm_text(memo)
    memo_low = memo_n.lower()

    for _, sc in special.items():
        if not isinstance(sc, dict):
            continue
        sk = sc.get("shop_keywords") or []
        if sk and not shop_contains(shop_n, sk):
            continue

        # shop_keywords が空なら無条件適用…は危険なのでスキップ
        if not sk:
            continue

        memo_map = sc.get("memo_map") or {}
        for key_low, account in memo_map.items():
            if key_low and key_low in memo_low:
                return account

        # メモにヒットしなければ default
        default = sc.get("default")
        if default:
            return default

    return None

def pick_account(shop: str, memo: str, rules: List[Dict[str, Any]], special: Dict[str, Any]) -> str:
    # 特例（Apple / メルカリ / トレジャーファク等）
    sp = apply_special_cases(shop, memo, special)
    if sp:
        return sp

    shop_n = norm_text(shop)
    shop_u = shop_n.upper()

    # 通常ルール（上から優先）
    for r in rules:
        account = r.get("account", "要確認")
        for k in r.get("keywords") or []:
            if not k:
                continue
            if norm_text(k).upper() in shop_u:
                return account

    return "要確認"

def pick_first_existing_col(df: pd.DataFrame, candidates: List[str]) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"必要な列が見つかりません。候補: {candidates} / 実際: {list(df.columns)}")

def main():
    if len(sys.argv) < 2:
        print("使い方: python3 process_keihi.py combined_clean.csv [rules.yaml]")
        sys.exit(1)

    input_file = Path(sys.argv[1])
    rules_file = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path(__file__).parent / "rules.yaml"

    print(f"読み込み: {input_file}")
    print(f"ルール: {rules_file}")

    open_date, rules, special = load_rules_yaml(rules_file)

    df = pd.read_csv(input_file, encoding="utf-8-sig", dtype=str)

    # 列名の候補（カードCSVの違いに少し強くしておく）
    col_check  = pick_first_existing_col(df, ["対象チェック"])
    col_shop   = pick_first_existing_col(df, [
        "ご利用店名（海外ご利用店名／海外都市名）",
        "ご利用店名",
        "利用店名",
        "加盟店名",
    ])
    col_date   = pick_first_existing_col(df, ["ご利用日", "利用日"])
    col_amount = pick_first_existing_col(df, ["ご利用金額（円）", "利用金額", "金額"])
    col_memo   = "備考" if "備考" in df.columns else ("メモ" if "メモ" in df.columns else None)

    # 対象抽出
    df[col_check] = to_int_flag(df[col_check])
    keihi = df[df[col_check] == 1].copy()

    # 正規化
    keihi[col_shop] = keihi[col_shop].apply(norm_text)
    if col_memo:
        keihi[col_memo] = keihi[col_memo].apply(norm_text)
    else:
        keihi["備考"] = ""
        col_memo = "備考"

    # 金額（数値化）
    keihi[col_amount] = (
        keihi[col_amount].astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace("−", "-", regex=False)
    )
    keihi[col_amount] = pd.to_numeric(keihi[col_amount], errors="coerce")

    # 日付（YYYY-MM-DDへ）
    # merge_csv.py 側で日付整形している前提だが、念のため here でも受ける
    keihi[col_date] = pd.to_datetime(keihi[col_date], errors="coerce").dt.date.astype(str)

    # 勘定科目付与
    keihi["勘定科目"] = keihi.apply(
        lambda r: pick_account(r[col_shop], r[col_memo], rules, special),
        axis=1
    )

    # freee用CSV（列は固定）
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
    d = pd.to_datetime(freee["取引日"], errors="coerce").dt.date
    is_before_open = d < open_date
    is_asset = freee["勘定科目"] == "工具器具備品"

    freee.loc[is_before_open & ~is_asset, "勘定科目"] = "開業費"

    # 出力（常にリポジトリ直下）
    freee.to_csv(PROJECT_ROOT / "freee_import.csv", index=False, encoding="utf-8-sig")
    print("作成: freee_import.csv")

    need = freee[freee["勘定科目"] == "要確認"].copy()
    need.to_csv(PROJECT_ROOT / "need_review.csv", index=False, encoding="utf-8-sig")
    print("作成: need_review.csv（要確認のみ）")

    summary = (
        keihi.groupby([col_shop, "勘定科目"])[col_amount]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={col_amount: "合計金額", col_shop: "店名"})
    )
    summary.to_csv(PROJECT_ROOT / "store_summary_with_account.csv", index=False, encoding="utf-8-sig")
    print("作成: store_summary_with_account.csv")

    print("\n件数:")
    print("  経費対象:", len(freee))
    print("  要確認:", len(need))
    print("  OK:", len(freee) - len(need))
    print(f"\n開業日(open_date): {open_date.isoformat()}")

if __name__ == "__main__":
    main()