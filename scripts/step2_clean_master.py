import glob
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 1400)
pd.set_option("display.max_colwidth", 35)

# ==============================================================================
# 0. 設定區（支援環境變數，預設相對路徑方便 GitHub Actions 執行）
# ==============================================================================
MASTER_DIR = os.getenv("TAIFEX_MASTER_DIR", os.path.join("data", "TAIFEX"))
RAW_DIR = os.getenv("TAIFEX_RAW_DIR", os.path.join("data", "TAIFEX", "Raw_TAIFEX"))
BACKUP_DIR = os.path.join(MASTER_DIR, "_backup_step2")

DRY_RUN = os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")


# ==============================================================================
# 1. 通用工具
# ==============================================================================
def parse_date_to_iso(val) -> str:
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "<na>", "nat"):
        return ""
    m = re.match(r"^(\d{3,4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 1900:
            y += 1911
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m8 = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m8:
        y, mo, d = int(m8.group(1)), int(m8.group(2)), int(m8.group(3))
        if y < 1900:
            y += 1911
        return f"{y:04d}-{mo:02d}-{d:02d}"
    dt = pd.to_datetime(s, format="mixed", errors="coerce")
    return dt.strftime("%Y-%m-%d") if pd.notna(dt) else ""


def detect_date_style(series: pd.Series) -> str:
    sample = series.dropna().astype(str).str.strip()
    sample = sample[sample != ""]
    if sample.empty:
        return "YYYY-MM-DD"
    v = sample.iloc[-1]
    if re.match(r"^\d{8}$", v):
        return "YYYYMMDD"
    if "/" in v:
        return "YYYY/MM/DD"
    return "YYYY-MM-DD"


def format_iso_to_style(iso_series: pd.Series, style: str) -> pd.Series:
    if style == "YYYYMMDD":
        return iso_series.str.replace("-", "", regex=False)
    if style == "YYYY/MM/DD":
        return iso_series.str.replace("-", "/", regex=False)
    return iso_series


def clean_num(series: pd.Series) -> pd.Series:
    s = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.strip()
    )
    s = s.where(~s.isin(["-", "--", "", "nan", "None", "<NA>"]), other=np.nan)
    return pd.to_numeric(s, errors="coerce")


def read_raw_folders(folders) -> pd.DataFrame:
    if isinstance(folders, str):
        folders = [folders]
    dfs = []
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        files = sorted(glob.glob(os.path.join(folder, "*.csv")))
        for fp in files:
            for enc in ("cp950", "big5", "utf-8-sig", "utf-8"):
                try:
                    d = pd.read_csv(fp, encoding=enc, index_col=False, low_memory=False)
                    d.columns = [str(c).strip() for c in d.columns]
                    drop_cols = [c for c in d.columns if c.startswith("Unnamed:") and d[c].isna().all()]
                    if drop_cols:
                        d = d.drop(columns=drop_cols)
                    if not d.empty:
                        dfs.append(d)
                    break
                except Exception:
                    continue
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def read_existing_master(stem: str) -> pd.DataFrame:
    pq = os.path.join(MASTER_DIR, f"{stem}.parquet")
    csv = os.path.join(MASTER_DIR, f"{stem}.csv")
    if os.path.exists(pq):
        df = pd.read_parquet(pq)
    elif os.path.exists(csv):
        df = None
        for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
            try:
                df = pd.read_csv(csv, encoding=enc, low_memory=False)
                break
            except Exception:
                continue
        if df is None:
            raise RuntimeError(f"無法讀取既有主檔 CSV: {csv}")
    else:
        raise FileNotFoundError(f"找不到既有主檔: {stem} (於 {MASTER_DIR})")
    df.columns = [str(c).strip() for c in df.columns]
    return df


ALIAS_MAP = {
    "商品代號": ["契約", "商品代號", "商品名稱"],
    "契約": ["契約", "商品代號", "商品名稱"],
    "商品名稱": ["商品名稱", "契約", "商品代號"],
    "是否因訊息面暫停交易": ["是否因訊息面暫停交易", "是否因凱恩訊息"],
    "是否因凱恩訊息": ["是否因凱恩訊息", "是否因訊息面暫停交易"],
    "漲跌幅%": ["漲跌%", "漲跌幅%"],
    "漲跌%": ["漲跌%", "漲跌幅%"],
    "交易日期": ["交易日期", "日期"],
    "日期": ["日期", "交易日期"],
}


def map_and_cast_new_rows(
    new_df: pd.DataFrame,
    old_df: pd.DataFrame,
    date_col: str,
    date_style: str,
) -> pd.DataFrame:
    out = pd.DataFrame(index=new_df.index)
    for col in old_df.columns:
        target_dtype = old_df[col].dtype

        src_col = None
        if col in new_df.columns:
            src_col = col
        elif col in ALIAS_MAP:
            for cand in ALIAS_MAP[col]:
                if cand in new_df.columns:
                    src_col = cand
                    break

        if src_col is None:
            out[col] = np.nan
        elif col == date_col:
            out[col] = format_iso_to_style(new_df["_iso_date"], date_style)
        else:
            out[col] = new_df[src_col].values

        if pd.api.types.is_integer_dtype(target_dtype) or str(target_dtype) == "Int64":
            num = clean_num(out[col])
            if str(target_dtype) == "Int64" or num.isna().any():
                out[col] = num.round().astype("Int64")
            else:
                out[col] = num.round().astype("int64")
        elif pd.api.types.is_float_dtype(target_dtype):
            out[col] = clean_num(out[col]).astype("float64")
        else:
            s = out[col].where(out[col].notna(), "")
            out[col] = s.astype(str).str.strip().replace({"nan": "", "None": "", "<NA>": ""})

    return out[old_df.columns]


def normalize_old_for_parquet(old_df: pd.DataFrame) -> pd.DataFrame:
    out = old_df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            s = out[col].where(out[col].notna(), "")
            out[col] = s.astype(str).str.strip()
    return out


def append_master_safely(
    stem: str,
    raw_sub_df: pd.DataFrame,
    raw_date_col: str,
    raw_dedup_keys: list,
    master_date_col: str,
):
    old_df = read_existing_master(stem)
    old_iso = old_df[master_date_col].map(parse_date_to_iso)
    old_valid_dates = sorted([d for d in old_iso.unique() if d])
    if not old_valid_dates:
        raise ValueError(f"{stem} 舊檔日期欄 {master_date_col} 無法解析！")
    old_max_date = old_valid_dates[-1]
    date_style = detect_date_style(old_df[master_date_col])

    new_work = raw_sub_df.copy()
    new_work["_iso_date"] = new_work[raw_date_col].map(parse_date_to_iso)
    new_work = new_work[new_work["_iso_date"] != ""].copy()

    for k in raw_dedup_keys:
        if k in new_work.columns:
            new_work[k] = new_work[k].astype(str).str.strip()
    valid_raw_keys = [k for k in raw_dedup_keys if k in new_work.columns]
    if valid_raw_keys:
        new_work = new_work.drop_duplicates(
            subset=["_iso_date"] + [k for k in valid_raw_keys if k != raw_date_col],
            keep="last",
        )

    new_to_append = (
        new_work[new_work["_iso_date"] > old_max_date]
        .sort_values("_iso_date", kind="mergesort")
        .copy()
    )
    new_dates = sorted(new_to_append["_iso_date"].unique())

    print("\n" + "-" * 90)
    print(f"【{stem}】")
    print(
        f"  舊檔狀態: {len(old_df):,} 列 | {len(old_valid_dates)} 日 "
        f"({old_valid_dates[0]} ~ {old_max_date}) | 日期格式={date_style} | 欄數={len(old_df.columns)}"
    )
    print(f"  待補新日: {len(new_to_append):,} 列 | {len(new_dates)} 日 {new_dates}")

    if new_to_append.empty:
        print("  [無須更新] 沒有比舊檔更新的日期。")
        return None

    mapped_new = map_and_cast_new_rows(new_to_append, old_df, master_date_col, date_style)
    old_ready = normalize_old_for_parquet(old_df)
    merged = pd.concat([old_ready, mapped_new], ignore_index=True)

    for col in old_df.columns:
        dt = old_df[col].dtype
        if str(dt) == "Int64":
            merged[col] = clean_num(merged[col]).round().astype("Int64")
        elif pd.api.types.is_integer_dtype(dt):
            num = clean_num(merged[col])
            merged[col] = num.round().astype("Int64" if num.isna().any() else "int64")
        elif pd.api.types.is_float_dtype(dt):
            merged[col] = clean_num(merged[col]).astype("float64")

    merged_iso = merged[master_date_col].map(parse_date_to_iso)
    merged_dates = sorted([d for d in merged_iso.unique() if d])
    assert len(merged) == len(old_df) + len(mapped_new), "列數異常！中止"
    assert len(merged_dates) >= len(old_valid_dates), "日期數變少！中止"

    print(f"  合併結果: {len(merged):,} 列 | {len(merged_dates)} 日 ({merged_dates[0]} ~ {merged_dates[-1]})")
    print("  [合併後 tail(3)]:")
    print(merged.tail(3).to_string(index=False))

    if not DRY_RUN:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        for ext in (".csv", ".parquet"):
            src = os.path.join(MASTER_DIR, f"{stem}{ext}")
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(BACKUP_DIR, f"{stem}{ext}"))

        csv_out = os.path.join(MASTER_DIR, f"{stem}.csv")
        pq_out = os.path.join(MASTER_DIR, f"{stem}.parquet")
        merged.to_csv(csv_out, index=False, encoding="utf-8-sig")
        merged.to_parquet(pq_out, index=False, engine="pyarrow")

        chk_pq = pd.read_parquet(pq_out)
        chk_csv = pd.read_csv(csv_out, encoding="utf-8-sig", low_memory=False)
        chk_dates = sorted([d for d in chk_pq[master_date_col].map(parse_date_to_iso).unique() if d])
        print(
            f"  [寫入驗收] .parquet={len(chk_pq):,} 列 | .csv={len(chk_csv):,} 列 | "
            f"起迄={chk_dates[0]} ~ {chk_dates[-1]} ({len(chk_dates)} 日)"
        )
    return stem


# ==============================================================================
# 2. 執行 Step 2（9 組 Clean Master 依序接續）
# ==============================================================================
def run_step2() -> int:
    os.makedirs(MASTER_DIR, exist_ok=True)
    print("=" * 90)
    print(f"Step 2：Clean Master 從底接續合併 | DRY_RUN = {DRY_RUN}")
    print(f"  來源 RAW_DIR   : {os.path.abspath(RAW_DIR)}")
    print(f"  目標 MASTER_DIR: {os.path.abspath(MASTER_DIR)}")
    print("=" * 90)

    # A. 期貨日行情 -> TX / MTX / TMF 每日交易行情2026_CleanMaster
    for sym in ("TX", "MTX", "TMF"):
        raw_fut = read_raw_folders([
            os.path.join(RAW_DIR, f"futData_{sym}"),
            os.path.join(RAW_DIR, "Futures_Daily"),
        ])
        if not raw_fut.empty and "契約" in raw_fut.columns:
            raw_fut["契約"] = raw_fut["契約"].astype(str).str.strip()
            append_master_safely(
                stem=f"{sym}每日交易行情2026_CleanMaster",
                raw_sub_df=raw_fut[raw_fut["契約"] == sym].copy(),
                raw_date_col="交易日期",
                raw_dedup_keys=["交易日期", "契約", "到期月份(週別)", "交易時段"],
                master_date_col="交易日期",
            )

    # B. 三大法人期貨 -> TX / MTX / TMF 三大法人交易2026_CleanMaster
    raw_inst = read_raw_folders([
        os.path.join(RAW_DIR, "futContractsDate"),
        os.path.join(RAW_DIR, "Institutional_Futures"),
    ])
    if not raw_inst.empty:
        comm_col = "商品名稱" if "商品名稱" in raw_inst.columns else ("契約" if "契約" in raw_inst.columns else None)
        if comm_col:
            raw_inst[comm_col] = raw_inst[comm_col].astype(str).str.strip()
            for sym, cnames in [
                ("TX", {"臺股期貨", "TX"}),
                ("MTX", {"小型臺指期貨", "MTX"}),
                ("TMF", {"微型臺指期貨", "TMF"}),
            ]:
                append_master_safely(
                    stem=f"{sym}三大法人交易2026_CleanMaster",
                    raw_sub_df=raw_inst[raw_inst[comm_col].isin(cnames)].copy(),
                    raw_date_col="日期",
                    raw_dedup_keys=["日期", comm_col, "身份別"],
                    master_date_col="日期",
                )

    # C. 選擇權日行情 -> TXO_Daily_Regular / AfterHours_CleanMaster
    raw_opt = read_raw_folders([
        os.path.join(RAW_DIR, "optData_TXO"),
        os.path.join(RAW_DIR, "Options_Daily"),
    ])
    if not raw_opt.empty:
        if "契約" in raw_opt.columns:
            raw_opt["契約"] = raw_opt["契約"].astype(str).str.strip()
            txo_opt = raw_opt[raw_opt["契約"] == "TXO"].copy()
        else:
            txo_opt = raw_opt.copy()
        if "交易時段" in txo_opt.columns:
            txo_opt["交易時段"] = txo_opt["交易時段"].astype(str).str.strip()
            for sess, stem in [
                ("一般", "TXO_Daily_Regular_CleanMaster"),
                ("盤後", "TXO_Daily_AfterHours_CleanMaster"),
            ]:
                append_master_safely(
                    stem=stem,
                    raw_sub_df=txo_opt[txo_opt["交易時段"] == sess].copy(),
                    raw_date_col="交易日期",
                    raw_dedup_keys=["交易日期", "契約", "到期月份(週別)", "履約價", "買賣權", "交易時段"],
                    master_date_col="交易日期",
                )

    # D. P/C Ratio -> TXO_PutCallRatio_CleanMaster
    raw_pc = read_raw_folders([
        os.path.join(RAW_DIR, "pcRatio_TXO"),
        os.path.join(RAW_DIR, "TXO_PCRatio"),
    ])
    if not raw_pc.empty:
        date_col = "日期" if "日期" in raw_pc.columns else "交易日期"
        append_master_safely(
            stem="TXO_PutCallRatio_CleanMaster",
            raw_sub_df=raw_pc.copy(),
            raw_date_col=date_col,
            raw_dedup_keys=[date_col],
            master_date_col="日期",
        )

    print(f"\n=== Step 2 執行完畢（DRY_RUN = {DRY_RUN}） ===")
    return 0


if __name__ == "__main__":
    sys.exit(run_step2())
