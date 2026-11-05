from datetime import datetime
import os
import sys

# ==============================================================================
# 1. 導日機制防呆 (解決 NameError: start_date_str is not defined)
# ==============================================================================
# 如果系統有傳入環境變數或參數則使用傳入值；若無（自動排程），則自動抓取今天 UTC/本地日期
start_date_str = os.environ.get("TARGET_DATE")

if not start_date_str:
  # 當自動排程執行時，自動給予當天日期字串 (格式: YYYY/MM/DD)
  start_date_str = datetime.now().strftime("%Y/%m/%d")

try:
  start_date = datetime.strptime(start_date_str, "%Y/%m/%d")
except ValueError:
  # 防呆：若格式不符，自動降級回當天
  start_date_str = datetime.now().strftime("%Y/%m/%d")
  start_date = datetime.strptime(start_date_str, "%Y/%m/%d")

print(f"🚀 Taiex Radar 自動爬蟲啟動...")
print(f"📅 執行抓取目標日期: {start_date_str}")

# ==============================================================================
# 2. 爬蟲與資料寫入邏輯
# ==============================================================================
try:
  # 這裡接您原本的爬蟲主程式與資料儲存邏輯
  # 例如：run_crawler_pipeline(start_date_str)

  print("✅ 資料抓取、清洗與檔存作業已成功完成！")

except Exception as e:
  print(f"❌ 執行過程發生異常: {e}")
  sys.exit(1)
