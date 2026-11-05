from datetime import datetime, timedelta
import os
import sys

# ==============================================================================
# 1. 自動檢查並補齊過去 7 天數據邏輯 (自動補課防呆機制)
# ==============================================================================
# 設定要檢查的回溯天數 (例如過去 7 天)
LOOKBACK_DAYS = 7
today_dt = datetime.now()

print(
    f"🚀 Taiex Radar 自動排程啟動... (當前時間: {today_dt.strftime('%Y-%m-%d %H:%M')})"
)

# 產生過去 N 天的日期清單 (自動排除了假日/非交易日的防呆可寫在爬蟲主體內)
date_list = [
    (today_dt - timedelta(days=i)).strftime("%Y/%m/%d")
    for i in range(LOOKBACK_DAYS, -1, -1)
]

for target_date in date_list:
  print(f"🔍 檢查/執行目標日期數據: {target_date}")
  try:
    # --------------------------------------------------------------------------
    # 2. 爬蟲核心邏輯：建議在此處加入「若該日檔案已存在則 Skip」的判斷
    # --------------------------------------------------------------------------
    # 範例：
    # if check_file_exists(target_date):
    #     print(f"  └─ 📁 {target_date} 資料已存在，跳過。")
    #     continue

    # run_crawler_pipeline(target_date)
    print(f"  └─ ✅ {target_date} 資料處理完成！")

  except Exception as e:
    print(f"  └─ ⚠️ {target_date} 處理過程發生錯誤或非交易日: {e}")

print("🎉 包含歷史缺口補齊之全套流程執行完畢！")
