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
        # 2. 期交所資料下載邏輯
        # --------------------------------------------------------------------------
        date_str_clean = target_date.replace('/', '')
        url = f"https://www.taifex.com.tw/file/taifex/Dailydow/Dailydow{date_str_clean}.csv"
        
        response = requests.get(url, timeout=10)
        
        # 確保編碼正確（期交所常用 big5 或 utf-8）
        response.encoding = 'big5'
        
        if response.status_code == 200 and len(response.text) > 100:
            # 將文字轉為 DataFrame 並存入列表
            df_day = pd.read_csv(io.StringIO(response.text))
            df_day['抓取日期'] = target_date
            all_collected_data.append(df_day)
            print(f"  └─ ✅ {target_date} 成功從期交所取得資料！")
        else:
            print(f"  └─ 💤 {target_date} 當日可能為假日或無交易資料。")

    except Exception as e:
        print(f"  └─ ⚠️ {target_date} 處理過程發生錯誤: {e}")

# ==============================================================================
# 3. 輸出儲存與 Git 準備 (關鍵：實體檔案生成)
# ==============================================================================
if all_collected_data:
    df_master_new = pd.concat(all_collected_data, ignore_index=True)
    # 實際建立並寫入 CSV 檔案，供 GitHub Actions 進行 git push
    df_master_new.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"💾 成功更新並儲存最新資料至: {OUTPUT_CSV} (共 {len(df_master_new)} 筆資料)")
else:
    print("⚠️ 本次未收集到任何有效資料（可能全為假日）。")

print("🎉 包含歷史缺口補齊之全套流程執行完畢！")
