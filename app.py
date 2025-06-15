from flask import Flask, request, abort
from linebot.v3.messaging import MessagingApi, ApiClient, Configuration
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage
import os
from datetime import datetime, timedelta # 匯入 timedelta
from supabase import create_client

app = Flask(__name__)

# 從環境變數取得 LINE 憑證和 Supabase 設定
# These environment variables must be set in your deployment environment (e.g., Render)
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

# 檢查必要的環境變數是否都已設定
if not all([channel_access_token, channel_secret, supabase_url, supabase_key]):
    raise ValueError("所有必要的環境變數都必須設置：LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SUPABASE_URL, SUPABASE_KEY")

# 初始化 LINE Bot API 和 Webhook 處理器
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
handler = WebhookHandler(channel_secret)

# 初始化 Supabase 客戶端
# 使用從環境變數讀取到的 Supabase URL 和 Key
supabase = create_client(supabase_url, supabase_key)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    print(f"Received body: {body}")

    try:
        # 處理 LINE 傳入的訊息
        handler.handle(body, signature)
    except InvalidSignatureError:
        # 如果簽名無效，回傳 400 錯誤
        print("Invalid signature error")
        abort(400)
    except Exception as e:
        # 處理其他未預期的錯誤
        print(f"Error in callback: {e}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id # 取得 LINE 使用者的 ID
    text = event.message.text.strip() # 取得使用者傳送的文字訊息並去除前後空白
    print(f"User {user_id} said: {text}")

    reply_text = "🤖 指令錯誤，請輸入：記帳、總額、月報 或 刪除"

    if text == "記帳":
        # 提示記帳格式
        reply_text = "請輸入格式：記帳 項目 金額 類別"

    elif text.startswith("記帳 "):
        try:
            parts = text.split()
            if len(parts) != 4:
                # 檢查輸入格式是否正確
                raise ValueError("格式錯誤，請輸入：記帳 項目 金額 類別")

            _, item, amount_str, category = parts
            amount = float(amount_str)
            if amount <= 0:
                # 金額必須大於零
                raise ValueError("金額必須大於 0")

            # 記錄到 Supabase 的 'expenses' 表格
            # expense_date 儲存為 UTC 時間並格式化
            data = supabase.table("expenses").insert({
                "user_id": user_id,
                "description": item,
                "amount": amount,
                "category": category,
                "expense_date": datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
            }).execute()

            # 檢查 Supabase 操作是否有錯誤
            if data.error:
                raise Exception(f"Supabase error: {data.error.get('message', 'Unknown error')}")

            reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        except ValueError as ve:
            # 處理格式錯誤或金額無效
            reply_text = str(ve)
        except Exception as e:
            # 處理其他記帳失敗的情況
            print(f"Error while recording expense: {e}")
            reply_text = "❌ 記帳失敗，請稍後再試"

    elif text == "總額":
        try:
            now_utc = datetime.utcnow()
            # 計算當月的第一天
            start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # 計算當月的最後一天 (下個月的第一天減去 1 微秒)
            if now_utc.month == 12:
                end_of_month = now_utc.replace(year=now_utc.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:
                end_of_month = now_utc.replace(month=now_utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)

            # 從 Supabase 查詢當月個人總支出
            data = supabase.table("expenses").select("amount").eq("user_id", user_id).gte(
                "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
            ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

            # 檢查 Supabase 操作是否有錯誤
            if data.error:
                raise Exception(f"Supabase error: {data.error.get('message', 'Unknown error')}")

            # 計算總金額和筆數
            total = sum(entry["amount"] for entry in data.data) if data.data else 0
            count = len(data.data)

            current_month_str = now_utc.strftime("%Y-%m")
            reply_text = f"💰 {current_month_str} 總支出：{total:.0f} 元，共 {count} 筆 (個人)"

        except Exception as e:
            # 處理查詢總額失敗的情況
            print(f"Error while calculating total: {e}")
            reply_text = "❌ 查詢總額失敗，請稍後再試"

    elif text == "月報":
        try:
            now_utc = datetime.utcnow()
            # 計算當月的第一天和最後一天
            start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if now_utc.month == 12:
                end_of_month = now_utc.replace(year=now_utc.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)
            else:
                end_of_month = now_utc.replace(month=now_utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(microseconds=1)

            # 從 Supabase 查詢當月所有支出紀錄
            data = supabase.table("expenses").select("*").gte(
                "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
            ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

            # 檢查 Supabase 操作是否有錯誤
            if data.error:
                raise Exception(f"Supabase error: {data.error.get('message', 'Unknown error')}")

            # 計算總金額和筆數
            total = sum(entry["amount"] for entry in data.data) if data.data else 0
            count = len(data.data)

            # 按類別統計支出
            category_stats = {}
            for entry in data.data:
                cat = entry["category"]
                if cat not in category_stats:
                    category_stats[cat] = {"total": 0, "count": 0, "items": []}
                category_stats[cat]["total"] += entry["amount"]
                category_stats[cat]["count"] += 1
                category_stats[cat]["items"].append((entry["description"], entry["amount"]))

            current_month_str = now_utc.strftime("%Y-%m")
            report = f"💰 {current_month_str} 月度報表 💰\n------------------------\n- 總支出：{total:.0f} 元\n- 總筆數：{count} 筆\n\n📊 按類別統計：\n"
            # 生成報表內容
            for cat, stats in category_stats.items():
                report += f"- {cat}: {stats['total']:.0f} 元 ({stats['count']} 筆)\n"
                for desc, amt in stats["items"]:
                    report += f"  - {desc}: {amt:.0f} 元\n"

            # 加上報表生成時間 (以 UTC 時間顯示)
            report += f"\n⏰ 報表生成時間：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
            reply_text = report

        except Exception as e:
            # 處理生成月度報表失敗的情況
            print(f"Error while generating monthly report: {e}")
            reply_text = "❌ 生成月度報表失敗，請稍後再試"

    elif text.startswith("刪除 "):
        try:
            item_to_delete = text.split(" ", 1)[1].strip()

            # 從 Supabase 查詢要刪除的最近一筆紀錄的 ID
            data = supabase.table("expenses").select("id").eq("user_id", user_id).eq("description", item_to_delete).order("expense_date", desc=True).limit(1).execute()

            # 檢查 Supabase 查詢是否有錯誤
            if data.error:
                raise Exception(f"Supabase error when fetching for delete: {data.error.get('message', 'Unknown error')}")

            if data.data:
                # 如果找到紀錄，則執行刪除操作
                delete_response = supabase.table("expenses").delete().eq("id", data.data[0]["id"]).execute()
                # 檢查 Supabase 刪除操作是否有錯誤
                if delete_response.error:
                    raise Exception(f"Supabase error during delete: {delete_response.error.get('message', 'Unknown error')}")
                reply_text = f"🗑️ 已刪除最近一筆「{item_to_delete}」記錄"
            else:
                # 找不到符合的紀錄
                reply_text = f"⚠️ 找不到「{item_to_delete}」的記帳紀錄"

        except Exception as e:
            # 處理刪除失敗的情況
            print(f"Error while deleting expense: {e}")
            reply_text = "❌ 刪除失敗，請稍後再試"

    # 回覆使用者訊息
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
    # 應用程式在本地運行時的配置
    app.run(host="0.0.0.0", port=5000)