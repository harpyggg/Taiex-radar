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
    f"🚀 Taiex Radar 自動排程啟動... (當前時間:"
    f" {today_dt.strftime('%Y-%m-%d %H:%M')})"
)

date_list = [
    (today_dt - timedelta(days=i)).strftime("%Y/%m/%d")
    for i in range(LOOKBACK_DAYS, -1, -1)
]

all_collected_data = []

# ==============================================================================
# 1. 自動檢查並補齊過去 7 天數據邏輯 (逐日請求)
# ==============================================================================
for target_date in date_list:
  print(f"🔍 檢查/執行目標日期數據: {target_date}")
  try:
    # 將 YYYY/MM/DD 轉為 YYYYMMDD
    date_str_clean = target_date.replace("/", "")

    # 期交所每日行情下載網址 (帶入當日日期參數)
    url = f"https://www.taifex.com.tw/file/taifex/Dailydow/Dailydow{date_str_clean}.csv"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.encoding = "big5"

    # 檢查是否成功取得資料（排除 404 頁面與錯誤回應）
    if response.status_code == 200 and "404" not in response.text[:50]:
      df_day = pd.read_csv(io.StringIO(response.text))
      df_day["抓取日期"] = target_date
      all_collected_data.append(df_day)
      print(f"  └─ ✅ {target_date} 成功從期交所取得資料！")
    else:
      print(f"  └─ 💤 {target_date} 當日可能為假日或查無交易資料。")

  except Exception as e:
    print(f"  └─ ⚠️ {target_date} 處理過程發生錯誤: {e}")

# ==============================================================================
# 2. 輸出儲存為實體 CSV 檔 (供 GitHub 提交與 Colab 同步)
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

print("🎉 包含歷史缺口補齊之全套流程執行完畢！")
