import os
import datetime
from io import StringIO
import requests
import pandas as pd


def get_target_date() -> datetime.date:
    """
    取得目標交易日期：
    若環境變數 TARGET_DATE 有指定（格式 YYYY-MM-DD 或 YYYY/MM/DD），則優先使用；
    否則預設抓今天（台北時區）。
    """
    env_date = os.environ.get("TARGET_DATE", "").strip()
    if env_date:
        cleaned = env_date.replace("/", "-")
        return datetime.date.fromisoformat(cleaned)

    tz_taipei = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz_taipei).date()


def fetch_text_with_retry(url: str, params: dict | None = None, retries: int = 3) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.taifex.com.tw/",
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            resp.encoding = "big5"
            text = resp.text.strip()
            if text:
                return text
        except Exception as exc:
            print(f"[WARN] 第 {attempt}/{retries} 次抓取失敗 ({url}): {exc}")
    return None


def download_taifex_daily_csv(trade_date: datetime.date, out_dir: str) -> str | None:
    """
    嘗試下載期交所每日行情 CSV（DailyMarketCSV）。
    若該日非交易日或查無資料，回傳 None。
    """
    date_slash = trade_date.strftime("%Y/%m/%d")
    date_compact = trade_date.strftime("%Y%m%d")

    # 期交所每日行情下載端點（依實際需求可調整或擴充）
    url = "https://www.taifex.com.tw/cht/3/dlFtdDaily"
    params = {
        "downfile": "1",
        "commodity_id": "TX",
        "queryStartDate": date_slash,
        "queryEndDate": date_slash,
    }

    raw_text = fetch_text_with_retry(url, params=params)
    if not raw_text:
        print(f"[INFO] {date_slash} 未取得期交所資料（可能為非交易日或尚未公布）。")
        return None

    # 簡單檢查是否為錯誤提示頁或無資料訊息
    if "<html" in raw_text.lower() or "查無資料" in raw_text or len(raw_text) < 50:
        print(f"[INFO] {date_slash} 無可用行情 CSV 資料。")
        return None

    try:
        df = pd.read_csv(
            StringIO(raw_text),
            encoding_errors="ignore",
            engine="python",
            on_bad_lines="skip",
        )
    except Exception as exc:
        print(f"[WARN] {date_slash} CSV 解析失敗: {exc}")
        return None

    if df.empty:
        print(f"[INFO] {date_slash} 解析後資料列為空。")
        return None

    os.makedirs(out_dir, exist_ok=True)
    save_path = os.path.join(out_dir, f"taifex_daily_{date_compact}.csv")
    df.to_csv(save_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 已儲存 {save_path}（共 {len(df)} 列）")
    return save_path


def main() -> None:
    out_dir = os.environ.get("TAIFEX_RAW_DIR", "data/raw")
    target_date = get_target_date()

    print(f"=== Step 1 開始執行 | 目標日期: {target_date} | 輸出目錄: {out_dir} ===")
    saved = download_taifex_daily_csv(target_date, out_dir)
    if saved:
        print(f"=== Step 1 完成 | 產出檔案: {saved} ===")
    else:
        print("=== Step 1 完成 | 今日無新增行情檔，流程正常結束 ===")


if __name__ == "__main__":
    main()
