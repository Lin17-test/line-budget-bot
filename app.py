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

# 從環境變數取得 LINE 憑證和 Supabase 設定
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

if not all([channel_access_token, channel_secret, supabase_url, supabase_key]):
    raise ValueError("所有必要的環境變數都必須設置：LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SUPABASE_URL, SUPABASE_KEY")

# 初始化 LINE Bot API 和 Webhook 處理器
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
handler = WebhookHandler(channel_secret)

# 初始化 Supabase 客戶端
supabase = create_client(supabase_url, supabase_key)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    print(f"Received body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature error")
        abort(400)
    except Exception as e:
        print(f"Error in callback: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    print(f"User {user_id} said: {text}")

    reply_text = "🤖 指令錯誤，請輸入：記帳、總額、月報 或 刪除"

    if text == "記帳":
        reply_text = "請輸入格式：記帳 項目 金額 類別"

    elif text.startswith("記帳 "):
        try:
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("格式錯誤，請輸入：記帳 項目 金額 類別")

            _, item, amount_str, category = parts
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError("金額必須大於 0")

            # 記錄到 Supabase 的 'expenses' 表格
            data_response = supabase.table("expenses").insert({ # 將結果儲存到 data_response
                "user_id": user_id,
                "description": item,
                "amount": amount,
                "category": category,
                "expense_date": datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
            }).execute()

            # 修正錯誤判斷邏輯：檢查 data_response 中是否有明確的錯誤訊息，並且確保 data_response.data 不為空
            # Supabase 的執行結果會包含 data 和 error 兩個屬性
            if data_response.error or not data_response.data: # 如果有錯誤訊息或者沒有回傳資料，則判斷為失敗
                raise Exception(f"Supabase error: {data_response.error.get('message', 'Unknown error') if data_response.error else 'No data returned'}")

            reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        except ValueError as ve:
            reply_text = str(ve)
        except Exception as e:
            print(f"Error while recording expense: {e}")
            reply_text = "❌ 記帳失敗，請稍後再試"

    elif text == "總額":
        try:
            now_utc = datetime.utcnow()
            start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now_utc.month == 12:
                end_of_month = now_utc.replace(year=now_utc.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:
                end_of_month = now_utc.replace(month=now_utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)

            data_response = supabase.table("expenses").select("amount").eq("user_id", user_id).gte(
                "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
            ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

            if data_response.error:
                raise Exception(f"Supabase error: {data_response.error.get('message', 'Unknown error')}")

            total = sum(entry["amount"] for entry in data_response.data) if data_response.data else 0
            count = len(data_response.data)

            current_month_str = now_utc.strftime("%Y-%m")
            reply_text = f"💰 {current_month_str} 總支出：{total:.0f} 元，共 {count} 筆 (個人)"

        except Exception as e:
            print(f"Error while calculating total: {e}")
            reply_text = "❌ 查詢總額失敗，請稍後再試"

    elif text == "月報":
        try:
            now_utc = datetime.utcnow()
            start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now_utc.month == 12:
                end_of_month = now_utc.replace(year=now_utc.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:
                end_of_month = now_utc.replace(month=now_utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)

            data_response = supabase.table("expenses").select("*").gte(
                "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
            ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

            if data_response.error:
                raise Exception(f"Supabase error: {data_response.error.get('message', 'Unknown error')}")

            total = sum(entry["amount"] for entry in data_response.data) if data_response.data else 0
            count = len(data_response.data)

            category_stats = {}
            for entry in data_response.data:
                cat = entry["category"]
                if cat not in category_stats:
                    category_stats[cat] = {"total": 0, "count": 0, "items": []}
                category_stats[cat]["total"] += entry["amount"]
                category_stats[cat]["count"] += 1
                category_stats[cat]["items"].append((entry["description"], entry["amount"]))

            current_month_str = now_utc.strftime("%Y-%m")
            report = f"💰 {current_month_str} 月度報表 💰\n------------------------\n- 總支出：{total:.0f} 元\n- 總筆數：{count} 筆\n\n📊 按類別統計：\n"
            for cat, stats in category_stats.items():
                report += f"- {cat}: {stats['total']:.0f} 元 ({stats['count']} 筆)\n"
                for desc, amt in stats["items"]:
                    report += f"  - {desc}: {amt:.0f} 元\n"

            report += f"\n⏰ 報表生成時間：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
            reply_text = report

        except Exception as e:
            print(f"Error while generating monthly report: {e}")
            reply_text = "❌ 生成月度報表失敗，請稍後再試"

    elif text.startswith("刪除 "):
        try:
            item_to_delete = text.split(" ", 1)[1].strip()

            data_response = supabase.table("expenses").select("id").eq("user_id", user_id).eq("description", item_to_delete).order("expense_date", desc=True).limit(1).execute()

            if data_response.error:
                raise Exception(f"Supabase error when fetching for delete: {data_response.error.get('message', 'Unknown error')}")

            if data_response.data:
                delete_response = supabase.table("expenses").delete().eq("id", data_response.data[0]["id"]).execute()
                if delete_response.error:
                    raise Exception(f"Supabase error during delete: {delete_response.error.get('message', 'Unknown error')}")
                reply_text = f"🗑️ 已刪除最近一筆「{item_to_delete}」記錄"
            else:
                reply_text = f"⚠️ 找不到「{item_to_delete}」的記帳紀錄"

        except Exception as e:
            print(f"Error while deleting expense: {e}")
            reply_text = "❌ 刪除失敗，請稍後再試"

    try:
        messaging_api.reply_message(
            reply_message_request={
                "replyToken": event.reply_token,
                "messages": [TextMessage(text=reply_text)]
            }
        )
    except Exception as e:
        print(f"Error sending reply: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)