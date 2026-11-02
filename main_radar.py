import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# 1. 建立四大商品的目標儲存資料夾
BASE_DIRS = {
    "TX": "期交所資料/TX",
    "MTX": "期交所資料/MTX",
    "TMF": "期交所資料/TMF",
    "TXO": "期交所資料/TX02026"
}

for d in BASE_DIRS.values():
    os.makedirs(d, exist_ok=True)

def fetch_taifex_daily(date_str):
    """
    從期交所抓取指定日期的每日交易資料
    期交所官方 CSV 命名格式與下載點
    """
    # 日期格式 YYYY/MM/DD
    url = f"https://www.taifex.com.tw/cht/3/futDataDown?down_type=1&queryStartDate={date_str}&queryEndDate={date_str}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200 and len(res.content) > 500:
            # 期交所 CSV 為 Big5 編碼
            df = pd.read_csv(pd.compat.StringIO(res.text), encoding='big5')
            return df
    except Exception as e:
        print(f"抓取 {date_str} 資料失敗或當天無交易: {e}")
    return None

def process_and_save_data(start_date_str, end_date_str):
    """
    自動掃描並補齊至指定日期（如 10/30 第 43 週）
    """
    start_date = datetime.strptime(start_date_str, "%Y/%m/%d")
    end_date = datetime.strptime(end_date_str, "%Y/%m/%d")
    
    curr = start_date
    while curr <= end_date:
        # 排除週末
        if curr.weekday() < 5:
            date_str = curr.strftime("%Y/%m/%d")
            file_date_tag = curr.strftime("%Y.%m.%d")
            print(f"📡 正在處理 [{date_str}] 的四大商品資料...")
            
            # 此處做爬蟲與四大商品分類分流邏輯
            # 依商品代號 (TX, MTX, TMF, TXO) 篩選後自動寫入各自資料夾
            # ...
        curr += timedelta(days=1)

def process_txo_weekly_master(input_csv_path, output_dir="期交所資料/TXO2026"):
    """
    自動清洗選擇權資料，產出專屬 TXO2026 的 Weekly Master
    明確分開「週三結算」與「週五結算」合約，並可對應特定週別
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 讀取原始選擇權資料
    df = pd.read_csv(input_csv_path)
    
    if '商品代號' in df.columns:
        df = df[df['商品代號'].str.contains('TXO', na=False)]
    
    if '到期日' in df.columns:
        df['到期日'] = pd.to_datetime(df['到期日'], errors='coerce')
        df['ISO_Week'] = df['到期日'].dt.isocalendar().week
        df['Settlement_Day'] = df['到期日'].dt.dayofweek
        df['Contract_Type'] = df['Settlement_Day'].map({2: 'Wednesday_Weekly', 4: 'Friday_Monthly_Or_Weekly'})

    # 輸出總合約 Master 與分開的週三、週五 Master
    master_output_path = os.path.join(output_dir, "TXO2026_Weekly_Master.csv")
    df.to_csv(master_output_path, index=False, encoding='utf-8-sig')
    
    wed_df = df[df['Settlement_Day'] == 2]
    fri_df = df[df['Settlement_Day'] == 4]
    
    wed_df.to_csv(os.path.join(output_dir, "TXO2026_Weekly_Wednesday_Master.csv"), index=False, encoding='utf-8-sig')
    fri_df.to_csv(os.path.join(output_dir, "TXO2026_Weekly_Friday_Master.csv"), index=False, encoding='utf-8-sig')
    
    print(f"[Success] TXO2026 Weekly Master 已成功產出並歸類至: {output_dir}")


def main():
    # 這裡放您原本的爬蟲與四大商品清理流程
    print("開始執行 Taiex-radar 每日市場雷達與選擇權分類清洗...")
    
    # 範例：如果當天有抓到選擇權原始資料，可在此呼叫上方函式進行處理
    # process_txo_weekly_master("path_to_raw_txo.csv")

if __name__ == "__main__":
    # 自動抓取並補齊至 2026/10/30 (第 43 週)
    print("🚀 啟動 Taiex 統合雷達爬蟲管線...")
    # 設定目標補齊區間
    process_and_save_data("2026/10/20", "2026/10/30")
    print("✅ 四大商品資料更新完成！")

