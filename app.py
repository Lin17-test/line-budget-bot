from flask import Flask, request, abort
from linebot.v3.messaging import MessagingApi, ApiClient, Configuration
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage
import os
from datetime import datetime, timedelta
from supabase import create_client

app = Flask(__name__)

# 環境變數設定
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

if not all([channel_access_token, channel_secret, supabase_url, supabase_key]):
    raise ValueError("請設定必要的環境變數：LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SUPABASE_URL, SUPABASE_KEY")

# 初始化 LINE API 和 Supabase
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
handler = WebhookHandler(channel_secret)
supabase = create_client(supabase_url, supabase_key)

def get_current_month_range_utc():
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)
    return start.isoformat() + "Z", end.isoformat() + "Z"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    print(f"Received body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature")
        abort(400)
    except Exception as e:
        print(f"Error in callback: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    reply_text = "⚠️ 指令錯誤，請輸入：記帳、總額、月報 或 刪除"

    try:
        if text == "記帳":
            reply_text = "請輸入格式：記帳 項目 金額 類別"

        elif text.startswith("記帳 "):
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("格式錯誤，請輸入：記帳 項目 金額 類別")

            _, item, amount_str, category = parts
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError("金額必須大於 0")

            result = supabase.table("expenses").insert({
                "user_id": user_id,
                "description": item,
                "amount": amount,
                "category": category,
                "expense_date": datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
            }).execute()

            print("[DEBUG] Insert response:", result)
            if hasattr(result, "error") and result.error:
                reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}（但有回應異常）"
            else:
                reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        elif text == "總額":
            start, end = get_current_month_range_utc()
            result = supabase.table("expenses").select("amount").eq("user_id", user_id).gte("expense_date", start).lte("expense_date", end).execute()
            if result.error:
                raise Exception(result.error)
            total = sum(entry["amount"] for entry in result.data or [])
            count = len(result.data or [])
            reply_text = f"\U0001F4B0 {start[:7]} 總支出：{total:.0f} 元，共 {count} 筆"

        elif text == "月報":
            start, end = get_current_month_range_utc()
            result = supabase.table("expenses").select("*").eq("user_id", user_id).gte("expense_date", start).lte("expense_date", end).execute()
            if result.error:
                raise Exception(result.error)

            category_summary = {}
            for row in result.data:
                cat = row["category"]
                category_summary.setdefault(cat, []).append((row["description"], row["amount"]))

            total = sum(row["amount"] for row in result.data)
            reply_lines = [f"\U0001F4B0 {start[:7]} 月報表", "------------------------", f"- 總支出：{total:.0f} 元", f"- 總筆數：{len(result.data)} 筆", "", "\U0001F4CA 按類別統計："]
            for cat, items in category_summary.items():
                cat_total = sum(a for _, a in items)
                reply_lines.append(f"- {cat}: {cat_total:.0f} 元（{len(items)} 筆）")
                for desc, amt in items:
                    reply_lines.append(f"  - {desc}: {amt:.0f} 元")
            reply_lines.append(f"\n⏰ 生成時間：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
            reply_text = "\n".join(reply_lines)

        elif text.startswith("刪除 "):
            item = text[3:].strip()
            result = supabase.table("expenses").select("id").eq("user_id", user_id).eq("description", item).order("expense_date", desc=True).limit(1).execute()
            if result.data:
                delete_result = supabase.table("expenses").delete().eq("id", result.data[0]["id"]).execute()
                if delete_result.error:
                    raise Exception(delete_result.error)
                reply_text = f"\U0001F5D1️ 已刪除最近一筆「{item}」"
            else:
                reply_text = f"⚠️ 找不到「{item}」的記帳紀錄"

    except ValueError as ve:
        reply_text = str(ve)
    except Exception as e:
        print(f"[ERROR] {e}")
        reply_text = "❌ 發生錯誤，請稍後再試"

    try:
        messaging_api.reply_message({
            "replyToken": event.reply_token,
            "messages": [TextMessage(text=reply_text)]
        })
    except Exception as e:
        print(f"[ERROR] 回覆訊息失敗：{e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)