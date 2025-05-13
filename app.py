from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import json

app = Flask(__name__)

# 從環境變數取得 LINE 憑證
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")

if not channel_access_token or not channel_secret:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 必須設置")

# 初始化 LINE Bot API 和 Webhook 處理器
line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# LINE Webhook 的入口
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    print(f"Received callback body: {body}")
    print(f"Signature: {signature}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        print(f"InvalidSignatureError: {e}")
        abort(400)
    except Exception as e:
        print(f"Callback error: {e}")
        abort(500)

    return 'OK'


# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    print(f"Received message: {text}")

    if text == "記帳":
        reply_text = "請輸入格式：記帳 [項目] [金額] [類別]"

    elif text.startswith("記帳 "):
        try:
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("格式錯誤，請輸入：記帳 [項目] [金額] [類別]")

            _, item, amount_str, category = parts
            amount = float(amount_str)

            # 嘗試讀取舊資料
            try:
                with open("expenses.json", "r", encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                print("expenses.json 損壞或不存在，將重新建立")
                data = []

            # 新增記錄
            new_entry = {
                "item": item,
                "amount": amount,
                "category": category,
                "month": "2025-05"  # 固定寫死，之後可改自動
            }
            data.append(new_entry)

            # 儲存資料
            with open("expenses.json", "w", encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        except ValueError as ve:
            reply_text = str(ve)
            print(f"ValueError: {ve}")
        except Exception as e:
            reply_text = "❌ 發生錯誤，請稍後再試"
            print(f"Unhandled Error: {e}")

    elif text == "總額":
        try:
            with open("expenses.json", "r", encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            data = []

        current_month = "2025-05"
        month_entries = [entry for entry in data if entry.get("month") == current_month]
        total = sum(entry.get("amount", 0) for entry in month_entries)
        reply_text = f"💰 {current_month} 的總支出是 {total:.0f} 元，共 {len(month_entries)} 筆"

    elif text == "查詢":
        reply_text = "🔍 查詢功能尚未實作"

    else:
        reply_text = "🤖 指令錯誤，請輸入：記帳、總額 或 查詢"

    print(f"Replying with: {reply_text}")

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"Reply error: {e}")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
