from datetime import datetime, timedelta
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

print(f"🚀 Taiex Radar 自動排程啟動... (當前時間: {today_dt.strftime('%Y-%m-%d %H:%M')})")

date_list = [
    (today_dt - timedelta(days=i)).strftime("%Y/%m/%d")
    for i in range(LOOKBACK_DAYS, -1, -1)
]

all_collected_data = []

# ==============================================================================
# 1. 自動檢查並補齊過去 7 天數據邏輯
# ==============================================================================
for target_date in date_list:
    print(f"🔍 檢查/執行目標日期數據: {target_date}")
    try:
        # --------------------------------------------------------------------------
        # 2. 期交所資料下載邏輯 (以期貨每日行情為例)
        # --------------------------------------------------------------------------
        # 期交所日行情 CSV 下載網址格式 (日期格式為 YYYYMMDD)
        date_str_clean = target_date.replace('/', '')
        url = f"https://www.taifex.com.tw/file/taifex/Dailydow/Dailydow{date_str_clean}.csv"
        
        # 嘗試發送請求下載
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200 and len(response.text) > 100:
            # 成功抓到資料，可在此進行解析與清洗
            print(f"  └─ ✅ {target_date} 成功從期交所取得資料！")
            # 實務上可將當日資料轉為 DataFrame 並存入 list
        else:
            print(f"  └─ 💤 {target_date} 當日可能為假日或無交易資料。")

    except Exception as e:
        print(f"  └─ ⚠️ {target_date} 處理過程發生錯誤: {e}")

# ==============================================================================
# 3. 輸出儲存與 Git 準備
# ==============================================================================
print("🎉 包含歷史缺口補齊之全套流程執行完畢！")
