import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import requests
import numpy as np

# ==========================================
# 0. 環境與中文字型設定
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def send_telegram_alert(message, image_path=None):
    """透過 Telegram Bot 推送文字與多維度驗屍圖表"""
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
                data = {"chat_id": chat_id, "caption": "📊 TXO 2026 週結算多維度籌碼驗屍報告"}
                requests.post(photo_url, data=data, files=files, timeout=15)
        except Exception as e:
            print(f"-> Telegram 圖片發送失敗: {e}")

def run_multi_dimensional_radar():
    print("=== 2026 選擇權多維度週結算驗屍引擎啟動 ===")
    
    # 1. 尋找所有選擇權資料檔案
    search_patterns = ["TXO26*.csv", "**/TXO26*.csv"]
    files = []
    for pattern in search_patterns:
        files.extend(glob.glob(pattern, recursive=True))
    
    if not files:
        print("【錯誤】找不到任何 TXO26*.csv 資料檔案，請確認檔案是否已上傳至儲存庫！")
        return
    
    latest_file = max(files, key=os.path.getmtime)
    print(f"-> 成功鎖定最新資料檔案: {latest_file}")
    
    # 2. 讀取數據
    try:
        df = pd.read_csv(latest_file, encoding='big5', low_memory=False)
    except Exception:
        df = pd.read_csv(latest_file, encoding='utf-8', low_memory=False)
        
    df.columns = [col.strip() for col in df.columns]
    
    # 3. 取得最新交易日期與前一日以計算 Delta OI
    df['交易日期'] = pd.to_numeric(df['交易日期'], errors='coerce')
    unique_dates = sorted(df['交易日期'].dropna().unique())
    if len(unique_dates) < 2:
        print("-> 日期資料不足，無法計算變動量。")
        return
        
    latest_date = unique_dates[-1]
    prev_date = unique_dates[-2]
    print(f"-> 正在比對結算軌跡: 前日 [{prev_date}] vs 最新 [{latest_date}]")
    
    df_latest = df[df['交易日期'] == latest_date].copy()
    df_prev = df[df['交易日期'] == prev_date].copy()
    
    # 4. 資料清洗與型態轉換
    for sub_df in [df_latest, df_prev]:
        sub_df['履約價'] = pd.to_numeric(sub_df['履約價'], errors='coerce')
        sub_df['未平倉口數'] = pd.to_numeric(sub_df['未平倉口數'], errors='coerce').fillna(0)
    
    # 5. 計算 5 大核心維度
    # (A) Call / Put OI 聚合
    oi_latest = df_latest.groupby(['履約價', '買賣權'])['未平倉口數'].sum().unstack(fill_value=0)
    oi_prev = df_prev.groupby(['履約價', '買賣權'])['未平倉口數'].sum().unstack(fill_value=0)
    
    call_col = [c for c in oi_latest.columns if '買' in str(c) or 'C' in str(c)][0]
    put_col = [c for c in oi_latest.columns if '賣' in str(c) or 'P' in str(c)][0]
    
    calls = oi_latest[call_col]
    puts = oi_latest[put_col]
    
    # (B) 計算 Delta OI (變動量)
    calls_prev = oi_prev.get(call_col, pd.Series(0, index=calls.index))
    puts_prev = oi_prev.get(put_col, pd.Series(0, index=puts.index))
    delta_calls = calls - calls_prev
    delta_puts = puts - puts_prev
    
    # (C) 計算 P/C Ratio (未平倉比率)
    total_call_oi = calls.sum()
    total_put_oi = puts.sum()
    pc_ratio = (total_put_oi / total_call_oi) * 100 if total_call_oi > 0 else 0
    
    max_call_strike = calls.idxmax()
    max_put_strike = puts.idxmax()
    
    msg = (
        f"🔬 *2026 極端行情選擇權驗屍報告*\n"
        f"📅 結算/比對日: `{prev_date}` ➔ `{latest_date}`\n"
        f"📈 Put/Call Ratio: `{pc_ratio:.2f}%`\n"
        f"🔴 最大 Call 壓力牆: `{max_call_strike}` (OI: {int(calls[max_call_strike]):,})\n"
        f"🟢 最大 Put 支撐牆: `{max_put_strike}` (OI: {int(puts[max_put_strike]):,})\n"
        f"⚡ 狀態：多維度指標與圖表自動產出完成。"
    )
    print(msg)
    
    # 6. 自動繪製多面板專業驗屍圖表（整合 OI 牆與 Delta OI 變動）
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # 子圖 1：OI 結構牆 (Open Interest Profile)
    axes[0].bar(calls.index, calls.values, width=40, label='Call OI (買權未平倉)', color='crimson', alpha=0.7)
    axes[0].bar(puts.index, puts.values, width=40, label='Put OI (賣權未平倉)', color='forestgreen', alpha=0.7)
    axes[0].axvline(max_call_strike, color='darkred', linestyle='--', label=f'Max Call Wall: {max_call_strike}')
    axes[0].axvline(max_put_strike, color='darkgreen', linestyle='--', label=f'Max Put Wall: {max_put_strike}')
    axes[0].set_title(f'TXO 2026 Weekly Options Autopsy & Walls ({latest_date}) | P/C Ratio: {pc_ratio:.1f}%', fontsize=14, fontweight='bold')
    axes[0].set_ylabel('Open Interest (未平倉口數)', fontsize=12)
    axes[0].legend(loc='upper right', fontsize=10)
    axes[0].grid(True, linestyle=':', alpha=0.6)
    
    # 子圖 2：Delta OI 變動量（捕捉主力換倉與爆量軌跡）
    axes[1].bar(delta_calls.index, delta_calls.values, width=40, label='Δ Call OI (買權增減)', color='orange', alpha=0.8)
    axes[1].bar(delta_puts.index, delta_puts.values, width=40, label='Δ Put OI (賣權增減)', color='dodgerblue', alpha=0.8)
    axes[1].axhline(0, color='black', linewidth=0.8)
    axes[1].set_xlabel('Strike Price (履約價)', fontsize=12)
    axes[1].set_ylabel('Delta OI (單日增減口數)', fontsize=12)
    axes[1].legend(loc='upper right', fontsize=10)
    axes[1].grid(True, linestyle=':', alpha=0.6)
    
    # 7. 儲存圖表
    output_chart_path = f"TXO_Autopsy_{latest_date}.png"
    plt.tight_layout()
    plt.savefig(output_chart_path, dpi=300)
    plt.close()
    print(f"-> 多維度驗屍圖表已成功產出: {output_chart_path}")
    
    # 8. 推送到 Telegram
    send_telegram_alert(msg, output_chart_path)
    print("=== 多維度週結算驗屍與 Telegram 推送完畢 ===")

if __name__ == "__main__":
    run_multi_dimensional_radar()
