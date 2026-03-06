#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_csv.py (monthly only + keep manual columns)

- meisai/ 以下の月次CSV (YYYYMM.csv) のみ結合
- 出力（プロジェクト直下）:
  - combined.csv
  - combined_clean.csv  ※Excelで手入力した「対象チェック」「備考」を自動で引き継ぐ
  - combined_duplicates.csv (あれば)  ※結合後に検出した全列一致重複を退避
- 出力（meisai/）:
  - potential_issues.csv

使い方:
  python3 merge_csv.py meisai
  （run_merge.py から呼ぶ場合は引数不要）
"""

from __future__ import annotations

import re
import sys
import csv
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd

MONTHLY_RE = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])\.csv$")  # YYYYMM.csv

OUT_COMBINED = "combined.csv"
OUT_COMBINED_CLEAN = "combined_clean.csv"
OUT_DUPLICATES = "combined_duplicates.csv"
OUT_ISSUES = "potential_issues.csv"

# 手入力で維持したい列
MANUAL_COLS = ["対象チェック", "備考"]


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def guess_encoding(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            path.read_text(encoding=enc)
            return enc
        except Exception:
            pass
    return "utf-8"


def guess_sep(path: Path, encoding: str) -> str:
    try:
        sample = path.read_text(encoding=encoding, errors="replace")[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";"])
        return dialect.delimiter
    except Exception:
        return ","


def list_monthly_csvs(input_dir: Path) -> List[Path]:
    files: List[Path] = []
    for p in input_dir.iterdir():
        if p.is_file() and MONTHLY_RE.match(p.name):
            files.append(p)
    files.sort(key=lambda x: x.name)
    return files


def normalize_columns(cols: List[str]) -> List[str]:
    return [str(c).replace("\u3000", " ").strip() for c in cols]


def extract_month_tag(filename: str) -> str:
    m = re.match(r"^((19|20)\d{2})(0[1-9]|1[0-2])\.csv$", filename)
    if not m:
        return ""
    yyyy = m.group(1)
    mm = m.group(3)
    return f"{yyyy}-{mm}"


def detect_schema_drift(base_cols: List[str], cols: List[str]) -> Tuple[List[str], List[str]]:
    base_set = set(base_cols)
    cur_set = set(cols)
    missing = [c for c in base_cols if c not in cur_set]
    extra = [c for c in cols if c not in base_set]
    return missing, extra


def add_issue(issues: List[Dict], type_: str, severity: str, file: str, month: str, detail: str):
    issues.append({
        "type": type_,
        "severity": severity,
        "file": file,
        "month": month,
        "detail": detail
    })


def try_read_csv(path: Path, issues: List[Dict], month_tag: str) -> Optional[pd.DataFrame]:
    enc = guess_encoding(path)
    sep = guess_sep(path, enc)

    attempts = [
        dict(encoding=enc, sep=sep, engine="python", dtype=str, on_bad_lines="warn"),
        dict(encoding=enc, sep=sep, engine="python", dtype=str, on_bad_lines="skip"),
        dict(encoding=enc, sep=",", engine="python", dtype=str, on_bad_lines="skip"),
        dict(encoding="utf-8-sig", sep=sep, engine="python", dtype=str, on_bad_lines="skip"),
        dict(encoding="cp932", sep=sep, engine="python", dtype=str, on_bad_lines="skip"),
    ]

    last_err = None
    for i, kwargs in enumerate(attempts, start=1):
        try:
            df = pd.read_csv(path, **kwargs)
            df.columns = normalize_columns(list(df.columns))
            if df.empty:
                add_issue(
                    issues, "empty_or_no_rows", "warn", path.name, month_tag,
                    f"読み込み成功だが行が空です (attempt={i}) enc={kwargs.get('encoding')} sep={repr(kwargs.get('sep'))}"
                )
            return df
        except Exception as e:
            last_err = e

    add_issue(issues, "read_failed", "error", path.name, month_tag, f"pd.read_csv が失敗: {repr(last_err)}")
    return None


def analyze_basic(df: pd.DataFrame, path: Path, month_tag: str, issues: List[Dict]):
    if any(str(c).strip() == "" for c in df.columns):
        add_issue(issues, "empty_column_name", "warn", path.name, month_tag, "空の列名が含まれています。")

    dup_cols = [c for c in df.columns if list(df.columns).count(c) > 1]
    if dup_cols:
        add_issue(issues, "duplicate_columns", "warn", path.name, month_tag, f"列名が重複: {sorted(set(dup_cols))}")

    if len(df) > 1:
        dups = df.duplicated().sum()
        if dups > 0:
            add_issue(issues, "duplicate_rows_within_file", "warn", path.name, month_tag, f"全列一致の重複行が {dups} 件")


def _to_str_series(df: pd.DataFrame, col: str) -> pd.Series:
    s = df[col] if col in df.columns else pd.Series([pd.NA] * len(df))
    s = s.astype("string")
    s = s.fillna("")
    s = s.str.replace("\u3000", " ").str.strip()
    return s


def make_row_id(df: pd.DataFrame) -> pd.Series:
    """
    明細行を同定するID（sha1）を作る。
    重要: 対象チェック/備考/source_file のような「変わり得る列」はキーから除外。
    """
    # あなたのCSV実態に合わせた安定キー（存在するものだけ使う）
    key_candidates = [
        "確定情報",
        "お支払日",
        "ご利用日",
        "ご利用店名（海外ご利用店名／海外都市名）",
        "支払回数",
        "何回目",
        "ご利用金額（円）",
        "現地通貨額・通貨名称・換算レート",
    ]
    # 実際に存在する列だけ使う
    key_cols = [c for c in key_candidates if c in df.columns]
    if not key_cols:
        # 最悪：manual/source_file以外の全列
        key_cols = [c for c in df.columns if c not in (MANUAL_COLS + ["source_file"])]

    def row_hash(i: int) -> str:
        parts = []
        for c in key_cols:
            parts.append(_to_str_series(df, c).iat[i])
        s = "||".join(parts)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()

    return pd.Series([row_hash(i) for i in range(len(df))], index=df.index, dtype="string")


def clean_dataframe(df: pd.DataFrame, issues: List[Dict], project_root: Path) -> pd.DataFrame:
    clean = df.copy()
    clean.columns = normalize_columns(list(clean.columns))

    # 文字列列: trim + 空をNAへ
    obj_cols = [c for c in clean.columns if clean[c].dtype == object]
    for c in obj_cols:
        clean[c] = clean[c].astype(str)
        clean[c] = clean[c].replace({"nan": "", "None": ""})
        clean[c] = clean[c].str.replace("\u3000", " ").str.strip()
        clean[c] = clean[c].replace({"": pd.NA})

    # 全列空行を除去
    before = len(clean)
    clean = clean.dropna(how="all")
    after = len(clean)
    if after < before:
        add_issue(issues, "dropped_all_empty_rows", "info", "(merged)", "", f"全列空行を {before - after} 行削除しました")

    # 結合後の全列一致重複を退避して削除（＝二重計上防止）
    if len(clean) > 1:
        dup_mask = clean.duplicated(keep="first")
        dup_count = int(dup_mask.sum())
        if dup_count > 0:
            out_dup = project_root / OUT_DUPLICATES
            dup_rows = clean.loc[dup_mask].copy()
            dup_rows.to_csv(out_dup, index=False, encoding="utf-8-sig")
            clean = clean.loc[~dup_mask].copy()
            add_issue(
                issues, "duplicate_rows_in_merged_removed", "warn", "(merged)", "",
                f"結合後に全列一致の重複行が {dup_count} 件あったため削除しました（退避: {out_dup}）"
            )

    return clean


def restore_manual_columns(clean: pd.DataFrame, project_root: Path, issues: List[Dict]) -> pd.DataFrame:
    """
    既存 combined_clean.csv があれば、対象チェック/備考 を row_id で引き継ぐ。
    既存が無いなら列だけ作る。
    """
    existing_path = project_root / OUT_COMBINED_CLEAN

    # まず列を必ず用意（Excelで入力できるように）
    for c in MANUAL_COLS:
        if c not in clean.columns:
            clean[c] = pd.NA

    if not existing_path.exists():
        add_issue(issues, "manual_columns_created", "info", "(merged)", "", "初回のため '対象チェック'/'備考' 列を追加しました（Excelで手入力できます）")
        return clean

    try:
        old = pd.read_csv(existing_path, encoding="utf-8-sig", dtype=str)
        old.columns = normalize_columns(list(old.columns))

        available = [c for c in MANUAL_COLS if c in old.columns]
        if not available:
            add_issue(issues, "manual_columns_created", "info", "(merged)", "", "既存 combined_clean.csv に手入力列が無いため、新規に列だけ追加しました")
            return clean

        # row_id を双方で作ってマージ
        old = old.copy()
        old["__row_id"] = make_row_id(old)
        clean = clean.copy()
        clean["__row_id"] = make_row_id(clean)

        keep = old[["__row_id"] + available].drop_duplicates(subset=["__row_id"])

        before_nonnull = {c: int(clean[c].notna().sum()) for c in MANUAL_COLS if c in clean.columns}

        clean = clean.merge(keep, on="__row_id", how="left", suffixes=("", "_old"))

        # マージ結果は同名列として入る（clean側に既に列がある場合、mergeはその列を保つ）
        # clean側が空で old側に値がある場合に埋める
        for c in available:
            # merge後に c が存在している前提
            # ただし clean側に既存値がある場合はそれを優先
            # clean[c] が NA で old側があるなら埋める、を行うために一旦 old列を持ってきて埋める
            # （pandas mergeの挙動に依存しないように c_old を作る）
            if f"{c}_old" in clean.columns:
                clean[c] = clean[c].combine_first(clean[f"{c}_old"])
                clean = clean.drop(columns=[f"{c}_old"])

        # row_id は出力に不要
        clean = clean.drop(columns=["__row_id"])

        after_nonnull = {c: int(clean[c].notna().sum()) for c in MANUAL_COLS if c in clean.columns}
        add_issue(
            issues, "manual_columns_restored", "info", "(merged)", "",
            f"既存 combined_clean.csv から手入力列を引き継ぎました: {available} / nonnull {before_nonnull} -> {after_nonnull}"
        )
        return clean

    except Exception as e:
        add_issue(
            issues, "manual_restore_failed", "warn", "(merged)", "",
            f"既存 combined_clean.csv の手入力列引き継ぎに失敗。列は維持します: {repr(e)}"
        )
        return clean


def main(input_dir: str) -> int:
    meisai_dir = Path(input_dir).expanduser().resolve()
    if not meisai_dir.exists() or not meisai_dir.is_dir():
        eprint(f"[ERROR] directory not found: {meisai_dir}")
        return 2

    project_root = meisai_dir.parent

    monthly_files = list_monthly_csvs(meisai_dir)
    if not monthly_files:
        eprint(f"[ERROR] No monthly CSV files found (YYYYMM.csv) in: {meisai_dir}")
        return 3

    print("==== merge_csv.py (monthly only) ====")
    print(f"Input dir: {meisai_dir}")
    print("Monthly CSV files:")
    for p in monthly_files:
        print(f"  - {p.name}")

    issues: List[Dict] = []
    dfs: List[pd.DataFrame] = []
    base_cols: Optional[List[str]] = None

    for p in monthly_files:
        month_tag = extract_month_tag(p.name)
        print(f"\n▶ 読み込み: {p.name}")

        df = try_read_csv(p, issues, month_tag)
        if df is None:
            print(f"  -> 読み込み失敗: {p.name}")
            continue

        analyze_basic(df, p, month_tag, issues)

        if base_cols is None:
            base_cols = list(df.columns)
        else:
            missing, extra = detect_schema_drift(base_cols, list(df.columns))
            if missing or extra:
                add_issue(
                    issues, "schema_drift", "warn", p.name, month_tag,
                    f"最初の月と列構成が異なります: {json.dumps({'missing': missing, 'extra': extra}, ensure_ascii=False)}"
                )

        # 既存の加工済みCSVの列名に合わせて source_file を付ける
        df["source_file"] = p.name

        dfs.append(df)

    if not dfs:
        eprint("[ERROR] All CSV reads failed. Nothing to merge.")
        out_issues = meisai_dir / OUT_ISSUES
        pd.DataFrame(issues).to_csv(out_issues, index=False, encoding="utf-8-sig")
        eprint(f"[INFO] wrote issues: {out_issues}")
        return 4

    merged = pd.concat(dfs, ignore_index=True, sort=False)

    out_combined = project_root / OUT_COMBINED
    merged.to_csv(out_combined, index=False, encoding="utf-8-sig")
    print(f"\n✅ wrote: {out_combined}")

    clean = clean_dataframe(merged, issues, project_root)

    # ✅ ここが本体：手入力列（対象チェック/備考）を復元
    clean = restore_manual_columns(clean, project_root, issues)

    out_clean = project_root / OUT_COMBINED_CLEAN
    clean.to_csv(out_clean, index=False, encoding="utf-8-sig")
    print(f"✅ wrote: {out_clean}")

    out_issues = meisai_dir / OUT_ISSUES
    issues_df = pd.DataFrame(issues)
    if issues_df.empty:
        issues_df = pd.DataFrame([{
            "type": "no_issues_detected",
            "severity": "info",
            "file": "",
            "month": "",
            "detail": "潜在的な問題は検出されませんでした（このスクリプトの検査範囲内）"
        }])
    issues_df.to_csv(out_issues, index=False, encoding="utf-8-sig")
    print(f"✅ wrote: {out_issues}")

    counts = {"error": 0, "warn": 0, "info": 0}
    for it in issues:
        sev = it.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1

    print("\n==== Summary ====")
    print(f"rows merged: {len(merged)}")
    print(f"errors: {counts.get('error', 0)}  warns: {counts.get('warn', 0)}  infos: {counts.get('info', 0)}")
    if counts.get("error", 0) > 0:
        print("⚠️ error があるため、potential_issues.csv を確認してください。")

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        eprint("Usage: python3 merge_csv.py <dir>")
        eprint("Example: python3 merge_csv.py meisai")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))