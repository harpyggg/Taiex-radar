from datetime import datetime, timedelta
import io
import os
import sys
import pandas as pd
import requests

# ==============================================================================
# 0. 初始化設定與資料儲存路徑
# ==============================================================================
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(DATA_DIR, "market_latest.csv")

LOOKBACK_DAYS = 7
today_dt = datetime.now()

print(
    f"🚀 Taiex Radar 自動排程啟動 (POST 介面版)... (當前時間:"
    f" {today_dt.strftime('%Y-%m-%d %H:%M')})"
)

date_list = [
    (today_dt - timedelta(days=i)).strftime("%Y/%m/%d")
    for i in range(LOOKBACK_DAYS, -1, -1)
]

all_collected_data = []

# ==============================================================================
# 1. 透過期交所 POST 介面逐日抓取資料
# ==============================================================================
# 期交所期貨每日行情下載的正確 POST 目標網址
url = "https://www.taifex.com.tw/cht/3/futDataDown"

for target_date in date_list:
  print(f"🔍 請求目標日期數據: {target_date}")
  try:
    # 帶入期交所要求的表單參數
    payload = {
        "down_type": "1",  # 1 為每日行情下載
        "queryStartDate": target_date,  # 格式: YYYY/MM/DD
        "queryEndDate": target_date,  # 格式: YYYY/MM/DD
        "commodity_id": "TMF",  # 可先抓微臺 (或改為 MTX, TX 等)
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "Referer": "https://www.taifex.com.tw/cht/3/futDataDown",
    }

    response = requests.post(url, data=payload, headers=headers, timeout=15)
    response.encoding = "big5"

    # 檢查是否成功取得有效 CSV 資料（避開錯誤頁面）
    if (
        response.status_code == 200
        and "404" not in response.text[:50]
        and "html" not in response.text[:50].lower()
    ):
      df_day = pd.read_csv(io.StringIO(response.text))
      df_day["抓取日期"] = target_date
      all_collected_data.append(df_day)
      print(f"  └─ ✅ {target_date} 透過 POST 成功取得期交所資料！")
    else:
      print(f"  └─ 💤 {target_date} 當日可能為假日或無交易資料。")

  except Exception as e:
    print(f"  └─ ⚠️ {target_date} 處理過程發生錯誤: {e}")

# ==============================================================================
# 2. 輸出儲存為實體 CSV 檔
# ==============================================================================
if all_collected_data:
  df_master_new = pd.concat(all_collected_data, ignore_index=True)
  df_master_new.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
  print(
      f"💾 成功更新並儲存最新資料至: {OUTPUT_CSV} (共 {len(df_master_new)}"
      f" 筆資料)"
  )
else:
  print("⚠️ 本次未收集到任何有效資料（可能全為假日）。")

print("🎉 流程執行完畢！")
