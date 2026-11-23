import math
import os
import sys

import numpy as np
import pandas as pd

# ==============================================================================
# 0. 路徑與參數設定（可由環境變數覆蓋，方便 GitHub Actions 執行）
# ==============================================================================
BASE_DIR = os.getenv("TAIFEX_MASTER_DIR", os.path.join("data", "TAIFEX"))

AMP_THRESHOLD = float(os.getenv("AMP_THRESHOLD", "1500"))
BIN_SIZE = int(os.getenv("BIN_SIZE", "50"))
START_AFTER_DATE = os.getenv("START_AFTER_DATE", "2026-11-11").strip()

PROFILE_COLS = [
    "date",
    "weekday",
    "symbol",
    "contract_month",
    "open",
    "high",
    "low",
    "close",
    "settlement",
    "price_bin",
    "retail_long_bin",
    "retail_short_bin",
    "volume_bin",
    "foreign_long_oi",
    "foreign_short_oi",
    "dealer_long_oi",
    "dealer_short_oi",
]

INT64_COLS = [
    "open",
    "high",
    "low",
    "close",
    "settlement",
    "price_bin",
    "retail_long_bin",
    "retail_short_bin",
    "volume_bin",
    "foreign_long_oi",
    "foreign_short_oi",
    "dealer_long_oi",
    "dealer_short_oi",
]

SYMBOLS_CONFIG = {
    "MTX": {
        "price_file": os.path.join(BASE_DIR, "MTX每日交易行情2026_CleanMaster.csv"),
        "inst_file": os.path.join(BASE_DIR, "MTX三大法人交易2026_CleanMaster.csv"),
        "out_parquet": os.path.join(BASE_DIR, "MTX_Clean_Master_Profile.parquet"),
        "out_csv": os.path.join(BASE_DIR, "MTX_Clean_Master_Profile.csv"),
        "has_session_col": True,
    },
    "TMF": {
        "price_file": os.path.join(BASE_DIR, "TMF每日交易行情2026_CleanMaster.csv"),
        "inst_file": os.path.join(BASE_DIR, "TMF三大法人交易2026_CleanMaster.csv"),
        "out_parquet": os.path.join(BASE_DIR, "TMF_Clean_Master_Profile.parquet"),
        "out_csv": os.path.join(BASE_DIR, "TMF_Clean_Master_Profile.csv"),
        "has_session_col": False,
    },
}

WEEKDAY_MAP = {0: "週一", 1: "週二", 2: "週三", 3: "週四", 4: "週五", 5: "週六", 6: "週日"}


# ==============================================================================
# 1. 清洗、權重與最大餘數法工具
# ==============================================================================
def clean_num(series: pd.Series) -> pd.Series:
    s = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.strip()
    )
    s = s.replace({"": np.nan, "-": np.nan, "--": np.nan, "None": np.nan, "nan": np.nan})
    return pd.to_numeric(s, errors="coerce")


def normalize_date_str(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.replace("/", "-", regex=False)
    mask_8 = s.str.fullmatch(r"\d{8}")
    s = np.where(
        mask_8,
        s.str.slice(0, 4) + "-" + s.str.slice(4, 6) + "-" + s.str.slice(6, 8),
        s,
    )
    return pd.Series(s, index=series.index)


def allocate_largest_remainder(total_int: int, weights: np.ndarray) -> np.ndarray:
    """將整數 total_int 依權重分配至各 bin，保證整數加總嚴格等於 total_int。"""
    n = len(weights)
    if n == 0:
        return np.array([], dtype=np.int64)
    total_int = int(max(0, round(total_int)))
    if total_int == 0:
        return np.zeros(n, dtype=np.int64)

    w = np.asarray(weights, dtype=np.float64)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.sum() <= 0:
        w = np.ones(n, dtype=np.float64)
    probs = w / w.sum()

    exact = total_int * probs
    floors = np.floor(exact).astype(np.int64)
    remainder = int(total_int - floors.sum())

    if remainder > 0:
        frac = exact - floors
        order = np.argsort(-frac, kind="mergesort")
        floors[order[:remainder]] += 1
    elif remainder < 0:
        frac = exact - floors
        order = np.argsort(frac, kind="mergesort")
        for idx in order[: abs(remainder)]:
            if floors[idx] > 0:
                floors[idx] -= 1

    return floors


def build_weights(bins: np.ndarray, high: float, low: float, anchor: float, amp: float) -> tuple[str, np.ndarray]:
    """振幅 > 1500 走模式 B（雙峰防禦）；振幅 <= 1500 走模式 A（梯形/斜坡分佈）。"""
    n = len(bins)
    weights = np.zeros(n, dtype=np.float64)
    if n == 0:
        return "模式A(梯形)", weights

    if amp > AMP_THRESHOLD:
        mode = "模式B(雙峰>1500)"
        if n <= 6:
            weights[:] = 1.0 / n
        else:
            top3_idx = np.argsort(-bins)[:3]
            bot3_idx = np.argsort(bins)[:3]
            weights[top3_idx] += 0.5 / 3.0
            weights[bot3_idx] += 0.5 / 3.0
        return mode, weights

    mode = "模式A(梯形)"
    span = max(high - low, float(BIN_SIZE))
    pos = np.clip((anchor - low) / span, 0.0, 1.0)
    ramp = np.linspace(-1.0, 1.0, n) if n > 1 else np.array([0.0])
    slope = 0.85 * (2.0 * pos - 1.0)
    raw = 1.0 + slope * ramp
    raw = np.maximum(raw, 0.25)
    weights = raw / raw.sum()
    return mode, weights


def load_existing_profile(cfg: dict) -> pd.DataFrame:
    """讀取既有 Profile 主檔（優先 .parquet，其次 .csv），並嚴格校驗 17 欄。"""
    if os.path.exists(cfg["out_parquet"]):
        df_old = pd.read_parquet(cfg["out_parquet"])
    elif os.path.exists(cfg["out_csv"]):
        df_old = pd.read_csv(
            cfg["out_csv"],
            dtype={"date": str, "weekday": str, "symbol": str, "contract_month": str},
        )
    else:
        raise FileNotFoundError(f"找不到既有 Profile 主檔: {cfg['out_parquet']} 或 {cfg['out_csv']}")

    if list(df_old.columns) != PROFILE_COLS:
        raise ValueError(f"既有 Profile 欄位與預期 17 欄不符: {list(df_old.columns)}")

    df_old = df_old.copy()
    df_old["date"] = normalize_date_str(df_old["date"])
    for c in ["weekday", "symbol", "contract_month"]:
        df_old[c] = df_old[c].astype(str).str.strip()
    for c in INT64_COLS:
        df_old[c] = pd.to_numeric(df_old[c], errors="raise").astype("int64")

    return df_old[PROFILE_COLS]


# ==============================================================================
# 2. 單一商品接續計算與寫入
# ==============================================================================
def append_symbol_profile(symbol: str, cfg: dict):
    df_old = load_existing_profile(cfg)
    old_rows = len(df_old)
    old_max_date = str(df_old["date"].max())

    if not os.path.exists(cfg["price_file"]) or not os.path.exists(cfg["inst_file"]):
        print(f"[{symbol}] 找不到 CleanMaster 來源檔，略過。")
        return

    df_p = pd.read_csv(cfg["price_file"], dtype=str)
    df_i = pd.read_csv(cfg["inst_file"], dtype=str)

    date_col_p = "交易日期" if "交易日期" in df_p.columns else "date"
    date_col_i = "日期" if "日期" in df_i.columns else "date"
    df_p["dt_str"] = normalize_date_str(df_p[date_col_p])
    df_i["dt_str"] = normalize_date_str(df_i[date_col_i])

    for col in ["成交量", "未沖銷契約數", "開盤價", "最高價", "最低價", "收盤價", "結算價"]:
        if col in df_p.columns:
            df_p[col] = clean_num(df_p[col])

    contract_col = "契約" if "契約" in df_p.columns else "商品代號"
    month_col = "到期月份(週別)" if "到期月份(週別)" in df_p.columns else "contract_month"
    df_p["contract_clean"] = df_p[contract_col].astype(str).str.strip()
    df_p["month_clean"] = df_p[month_col].astype(str).str.strip()

    df_p = df_p[
        ~df_p["contract_clean"].str.contains("/", na=False)
        & ~df_p["month_clean"].str.contains("W", case=False, na=False)
    ].copy()

    if cfg["has_session_col"] and "交易時段" in df_p.columns:
        df_day = df_p[df_p["交易時段"].astype(str).str.strip() == "一般"].copy()
    else:
        df_day = df_p[df_p["結算價"].notna() & df_p["未沖銷契約數"].notna()].copy()

    df_i["身份別"] = df_i["身份別"].astype(str).str.strip()
    df_i["多方未平倉口數"] = clean_num(df_i["多方未平倉口數"]).fillna(0)
    df_i["空方未平倉口數"] = clean_num(df_i["空方未平倉口數"]).fillna(0)

    cutoff = max(old_max_date, START_AFTER_DATE)
    target_dates = sorted([d for d in df_day["dt_str"].dropna().unique() if d > cutoff])

    if not target_dates:
        print(f"[{symbol}] 無新增交易日（既有最新={old_max_date}）。")
        return

    new_records = []
    for d in target_dates:
        sub_p = df_day[df_day["dt_str"] == d].copy()
        if sub_p.empty:
            continue

        dups_count = int(sub_p.duplicated(subset=["dt_str", "month_clean"]).sum())
        if dups_count > 0:
            raise RuntimeError(f"[{symbol}] {d} 發現同日同到期月份重複列 (DUPS={dups_count})，已中止寫入！")

        sub_p["vol_num"] = sub_p["成交量"].fillna(0)
        main_row = sub_p.sort_values("vol_num", ascending=False).iloc[0]

        c_month = main_row["month_clean"]
        o_px = int(round(main_row["開盤價"]))
        h_px = int(round(main_row["最高價"]))
        l_px = int(round(main_row["最低價"]))
        c_px = int(round(main_row["收盤價"]))
        s_px = int(round(main_row["結算價"])) if pd.notna(main_row["結算價"]) else c_px
        amp = int(h_px - l_px)

        total_vol = int(round(sub_p["成交量"].fillna(0).sum()))
        total_oi = int(round(sub_p["未沖銷契約數"].fillna(0).sum()))

        sub_i = df_i[df_i["dt_str"] == d]
        f_row = sub_i[sub_i["身份別"].str.contains("外資", na=False)]
        d_row = sub_i[sub_i["身份別"].str.contains("自營", na=False)]

        f_long = int(round(f_row["多方未平倉口數"].sum()))
        f_short = int(round(f_row["空方未平倉口數"].sum()))
        d_long = int(round(d_row["多方未平倉口數"].sum()))
        d_short = int(round(d_row["空方未平倉口數"].sum()))

        retail_long_total = max(0, total_oi - (f_long + d_long))
        retail_short_total = max(0, total_oi - (f_short + d_short))

        low_bin = int(math.floor(l_px / BIN_SIZE) * BIN_SIZE)
        high_bin = int(math.floor(h_px / BIN_SIZE) * BIN_SIZE)
        bins = np.arange(low_bin, high_bin + BIN_SIZE, BIN_SIZE, dtype=np.int64)

        _, weights = build_weights(bins, h_px, l_px, s_px, amp)

        r_long_bins = allocate_largest_remainder(retail_long_total, weights)
        r_short_bins = allocate_largest_remainder(retail_short_total, weights)
        vol_bins = allocate_largest_remainder(total_vol, weights)

        long_sum = int(r_long_bins.sum() + f_long + d_long)
        short_sum = int(r_short_bins.sum() + f_short + d_short)
        if long_sum != short_sum:
            raise RuntimeError(f"[{symbol}] {d} 零和檢核失敗：多方={long_sum} != 空方={short_sum}")

        w_str = WEEKDAY_MAP.get(pd.to_datetime(d).dayofweek, "")
        for idx, b in enumerate(bins):
            new_records.append({
                "date": d,
                "weekday": w_str,
                "symbol": symbol,
                "contract_month": c_month,
                "open": o_px,
                "high": h_px,
                "low": l_px,
                "close": c_px,
                "settlement": s_px,
                "price_bin": int(b),
                "retail_long_bin": int(r_long_bins[idx]),
                "retail_short_bin": int(r_short_bins[idx]),
                "volume_bin": int(vol_bins[idx]),
                "foreign_long_oi": f_long,
                "foreign_short_oi": f_short,
                "dealer_long_oi": d_long,
                "dealer_short_oi": d_short,
            })

    if not new_records:
        print(f"[{symbol}] 沒有可寫入的新列。")
        return

    df_new = pd.DataFrame(new_records, columns=PROFILE_COLS)
    for c in INT64_COLS:
        df_new[c] = df_new[c].astype("int64")

    df_merged = pd.concat([df_old, df_new], ignore_index=True)
    df_merged = (
        df_merged.drop_duplicates(
            subset=["date", "symbol", "contract_month", "price_bin"], keep="last"
        )
        .sort_values(["date", "contract_month", "price_bin"], kind="mergesort")
        .reset_index(drop=True)
    )

    df_merged = df_merged[PROFILE_COLS]
    for c in INT64_COLS:
        df_merged[c] = df_merged[c].astype("int64")

    df_merged.to_parquet(cfg["out_parquet"], index=False)
    df_merged.to_csv(cfg["out_csv"], index=False, encoding="utf-8-sig")

    df_chk = pd.read_parquet(cfg["out_parquet"])
    print("=" * 95)
    print(f"【Step 3 接續寫入完成】{symbol}")
    print(
        f"  原列數={old_rows} (最新={old_max_date}) -> 新增列={len(df_new)} "
        f"-> 回讀總列數={len(df_chk)} (最新={df_chk['date'].max()})"
    )
    print(f"  欄位數={len(df_chk.columns)} | 已同步更新: .parquet 與 .csv (utf-8-sig)")
    print("=" * 95)


def run_step3() -> int:
    for sym, conf in SYMBOLS_CONFIG.items():
        append_symbol_profile(sym, conf)
    return 0


if __name__ == "__main__":
    sys.exit(run_step3())
