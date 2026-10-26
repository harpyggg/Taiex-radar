import datetime
import os
import requests

# 從 GitHub 雲端保險箱安全讀取金鑰
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')


def send_telegram_alert(message):
  url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
  payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
  response = requests.post(url, json=payload)
  if response.status_code == 200:
    print('📱 [雲端雷達警報] Telegram 推播發送成功！')
  else:
    print(f'❌ 發送失敗: {response.text}')


print('🚀 【微台宏觀量化清算雷達】雲端背景執行中...')

# 模擬當前 4 萬點級距與 Day 1 掃描
current_price = 46500
capitulation_floor = 45200
consecutive_margin_calls = 1
today_str = datetime.datetime.now().strftime('%Y-%m-%d')

print(f'--- 執行盤勢掃描 [{today_str}] ---')
print(f'• 當前指數: {current_price} | 紫色斷頭價: {capitulation_floor}')
print(f'• 連續 Margin Call 天數: Day {consecutive_margin_calls}')

if consecutive_margin_calls == 1:
  msg = (
      f'⚠️ *【微台清算雷達：Day 1 雲端預警】*\n'
      f'------------------------------------\n'
      f'📅 日期：{today_str}\n'
      f'🔴 偵測信號：市場首日觸發 Margin Call。\n'
      f'🎯 戰略動作：啟動選擇權 *Long Strangle (雙買勒式)* 佈局。\n'
      f'📊 當前參考價：{current_price}'
  )
  send_telegram_alert(msg)
