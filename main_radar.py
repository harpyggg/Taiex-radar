from datetime import datetime, timedelta
import os
import sys

# ==========================================
# 1. 自動取得日期與設定區
# ==========================================
# 取得今天日期字串 (格式: YYYY/MM/DD)
today_dt = datetime.now()
start_date_str = today_dt.strftime("%Y/%m/%d")

# 轉成 datetime 物件
start_date = datetime.strptime(start_date_str, "%Y/%m/%d")

print(f"🚀 開始執行 Taiex Radar 爬蟲流程...")
print(f"📅 當前執行日期: {start_date_str}")

# ==========================================
# 2. 爬蟲與資料處理邏輯區 (請依實際模組調整)
# ==========================================
try:
  # 這裡放置您原本的爬蟲與儲存邏輯
  # 例如：fetch_taiex_data(start_date_str)
  print("✅ 資料抓取與清洗完成！")

except Exception as e:
  print(f"❌ 爬蟲執行過程發生錯誤: {e}")
  sys.exit(1)
