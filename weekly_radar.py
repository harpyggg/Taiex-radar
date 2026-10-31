import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime

# ==========================================
# 0. 環境與中文字型設定
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def send_telegram_alert(message, image_path=None):
    """透過 Telegram Bot 推送文字與圖片警報"""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("-> 未設定 Telegram 密鑰環境變數，跳過推送。")
        return

    # 發送文字訊息
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"-> Telegram 文字發送失敗: {e}")
    
    # 若有圖表則同步發送圖片
    if image_path and os.path.exists(image_path):
        photo_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        try:
            with open(image_path, 'rb') as photo:
                files = {"photo": photo}
                data = {"chat_id": chat_id, "caption": "📊 TXO 週結算 OI 牆與籌碼結構分析"}
                requests.post(photo_url, data=data, files=files, timeout=15)
        except Exception as e:
            print(f"-> Telegram 圖片發送失敗: {e}")

def run_weekly_options_pipeline():
    print("=== 2026 選擇權週結算與 OI 牆自動分析引擎啟動 ===")
    
    # 1. 自動尋找專案根目錄或 TXO2026 資料夾中的最新 CSV 檔案
    # 支援直接放在根目錄或子資料夾的搜尋模式
    search_patterns = ["TXO26*.csv", "**/TXO26*.csv"]
    files = []
    for pattern in search_patterns:
        files.extend(glob.glob(pattern, recursive=True))
    
    if not files:
        print("【錯誤】找不到任何 TXO26*.csv 資料檔案，請確認檔案是否已上傳至儲存庫！")
        return
    
    # 鎖定最新修改的檔案
    latest_file = max(files, key=os.path.getmtime)
    print(f"-> 成功鎖定最新資料檔案: {latest_file}")
    
    # 2. 讀取期交所 CSV 資料 (相容 Big5 與 UTF-8 編碼)
    try:
        df = pd.read_csv(latest_file, encoding='big5', low_memory=False)
    except Exception:
        df = pd.read_csv(latest_file, encoding='utf-8', low_memory=False)
        
    # 標準化欄位名稱（去除前後空白）
    df.columns = [col.strip() for col in df.columns]
    
    # 3. 欄位自我檢查
    required_cols = ['交易日期', '履約價', '買賣權', '未平倉口數']
    for col in required_cols:
        if col not in df.columns:
            print(f"【警告】找不到必要欄位 '{col}'。現有欄位: {df.columns.tolist()}")
            return

    # 4. 取得最新交易日期的資料
    df['交易日期'] = pd.to_numeric(df['交易日期'], errors='coerce')
    latest_date = df['交易日期'].max()
    df_latest = df[df['交易日期'] == latest_date].copy()
    print(f"-> 正在分析最新交易日: {latest_date}")
    
    # 5. 計算 Call 與 Put 各履約價的未平倉量 (OI) 總和
    df_latest['履約價'] = pd.to_numeric(df_latest['履約價'], errors='coerce')
    df_latest['未平倉口數'] = pd.to_numeric(df_latest['未平倉口數'], errors='coerce').fillna(0)
    
    oi_grouped = df_latest.groupby(['履約價', '買賣權'])['未平倉口數'].sum().unstack(fill_value=0)
    
    call_col = [c for c in oi_grouped.columns if '買' in str(c) or 'C' in str(c)]
    put_col = [c for c in oi_grouped.columns if '賣' in str(c) or 'P' in str(c)]
    
    if not call_col or not put_col:
        print(f"-> 無法辨識買賣權欄位，現有分類: {oi_grouped.columns.tolist()}")
        return
        
    calls = oi_grouped[call_col[0]]
    puts = oi_grouped[put_col[0]]
    
    # 找出最大 OI 牆（主力防守與壓力價位）
    max_call_strike = calls.idxmax()
    max_put_strike = puts.idxmax()
    
    msg = (
        f"🎯 *TXO 選擇權結算結構雷達報告*\n"
        f"📅 交易日期: `{latest_date}`\n"
        f"🔴 最大 Call 壓力牆 (Call Wall): `{max_call_strike}`\n"
        f"🟢 最大 Put 支撐牆 (Put Wall): `{max_put_strike}`\n"
        f"⚡ 狀態：雲端自動運算完成。"
    )
    print(msg)
    
    # 6. 自動繪製週結算 OI 牆分佈圖
    plt.figure(figsize=(12, 6))
    plt.bar(calls.index, calls.values, width=50, label='Call OI (買權未平倉)', color='crimson', alpha=0.7)
    plt.bar(puts.index, puts.values, width=50, label='Put OI (賣權未平倉)', color='forestgreen', alpha=0.7)
    
    plt.axvline(max_call_strike, color='darkred', linestyle='--', label=f'Max Call Wall: {max_call_strike}')
    plt.axvline(max_put_strike, color='darkgreen', linestyle='--', label=f'Max Put Wall: {max_put_strike}')
    
    plt.title(f'TXO 2026 Weekly Options OI Walls ({latest_date})', fontsize=14, fontweight='bold')
    plt.xlabel('Strike Price (履約價)', fontsize=12)
    plt.ylabel('Open Interest (未平倉口數)', fontsize=12)
    plt.legend(loc='upper right', fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.6)
    
    # 7. 儲存圖表檔案
    output_chart_path = f"TXO_OI_Wall_{latest_date}.png"
    plt.tight_layout()
    plt.savefig(output_chart_path, dpi=300)
    plt.close()
    print(f"-> 視覺化圖表已成功產出: {output_chart_path}")
    
    # 8. 透過 Telegram 推送報告與圖片
    send_telegram_alert(msg, output_chart_path)
    print("=== 週選擇權自動化掃描與 Telegram 推送完畢 ===")

if __name__ == "__main__":
    run_weekly_options_pipeline()
