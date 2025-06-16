from flask import Flask, request, abort
import os
import pendulum
import logging
from linebot.v3.messaging import MessagingApi, ApiClient, Configuration
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage
from supabase import create_client

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 從環境變數取得憑證
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

if not all([channel_access_token, channel_secret, supabase_url, supabase_key]):
    logger.error("缺少必要的環境變數")
    raise ValueError("必須設置 LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SUPABASE_URL, SUPABASE_KEY")

# 初始化 LINE Bot 和 Supabase
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
handler = WebhookHandler(channel_secret)
supabase = create_client(supabase_url, supabase_key)

def get_user_categories(user_id):
    """獲取用戶的自訂類別"""
    response = supabase.table("categories").select("category_name").eq("user_id", user_id).execute()
    return [row["category_name"] for row in response.data] if response.data else ["食物", "交通", "娛樂", "購物", "其他"]

def add_user_category(user_id, category):
    """新增用戶自訂類別"""
    response = supabase.table("categories").insert({
        "user_id": user_id,
        "category_name": category
    }).execute()
    return response.data is not None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    logger.info(f"Received webhook body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        abort(400)
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    logger.info(f"User {user_id} sent: {text}")

    reply_text = "🤖 請輸入：記帳、總額、月報個人、月報總和、刪除、新增類別 或 總額 YYYY-MM、月報個人 YYYY-MM、月報總和 YYYY-MM"

    try:
        if text == "記帳":
            user_categories = get_user_categories(user_id)
            reply_text = f"請輸入格式：記帳 項目 金額 類別（類別需為：{', '.join(user_categories)}）"

        elif text.startswith("記帳 "):
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("格式錯誤，請輸入：記帳 項目 金額 類別")

            _, item, amount_str, category = parts
            if len(item) > 50:
                raise ValueError("項目名稱過長（最多50字）")
            
            user_categories = get_user_categories(user_id)
            if category not in user_categories:
                raise ValueError(f"無效類別，請選擇：{', '.join(user_categories)} 或使用「新增類別」指令")
            
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError("金額必須大於0")
            except ValueError:
                raise ValueError("金額必須是有效數字")

            data_response = supabase.table("expenses").insert({
                "user_id": user_id,
                "description": item,
                "amount": amount,
                "category": category,
                "expense_date": pendulum.now('UTC').to_iso8601_string()
            }).execute()

            if data_response.data:
                reply_text = f"✅ 已記帳：{item} - {amount:.0f} 元 - {category}"
            else:
                logger.error(f"Supabase insert failed: {data_response}")
                raise Exception("記帳失敗，資料庫未回傳資料")

        elif text.startswith("新增類別 "):
            category = text.split(" ", 1)[1].strip()
            if len(category) > 20:
                raise ValueError("類別名稱過長（最多20字）")
            if add_user_category(user_id, category):
                reply_text = f"✅ 已新增類別：{category}"
            else:
                raise Exception("新增類別失敗，請稍後再試")

        elif text.startswith("總額"):
            parts = text.split()
            if len(parts) > 1:
                try:
                    target_date = pendulum.parse(parts[1], strict=False)
                except ValueError:
                    raise ValueError("月份格式錯誤，請輸入 YYYY-MM")
            else:
                target_date = pendulum.now('UTC')

            start_of_month = target_date.start_of('month')
            end_of_month = target_date.end_of('month')

            data_response = supabase.table("expenses").select("amount").eq("user_id", user_id).gte(
                "expense_date", start_of_month.to_iso8601_string()
            ).lte("expense_date", end_of_month.to_iso8601_string()).execute()

            if data_response.data:
                total = sum(entry["amount"] for entry in data_response.data)
                count = len(data_response.data)
                month_str = target_date.format("YYYY-MM")
                reply_text = f"💰 {month_str} 總支出：{total:.0f} 元，共 {count} 筆 (個人)"
            else:
                reply_text = f"💰 {target_date.format('YYYY-MM')} 無支出記錄"

        elif text.startswith("月報個人") or text.startswith("月報總和"):
            is_personal = text.startswith("月報個人")
            parts = text.split()
            if len(parts) > 1:
                try:
                    target_date = pendulum.parse(parts[1], strict=False)
                except ValueError:
                    raise ValueError("月份格式錯誤，請輸入 YYYY-MM")
            else:
                target_date = pendulum.now('UTC')

            start_of_month = target_date.start_of('month')
            end_of_month = target_date.end_of('month')

            query = supベース.table("expenses").select("*").gte(
                "expense_date", start_of_month.to_iso8601_string()
            ).lte("expense_date", end_of_month.to_iso8601_string())
            if is_personal:
                query = query.eq("user_id", user_id)

            data_response = query.execute()

            if not data_response.data:
                reply_text = f"💰 {target_date.format('YYYY-MM')} 無支出記錄 ({'個人' if is_personal else '全用戶'})"
            else:
                total = sum(entry["amount"] for entry in data_response.data)
                count = len(data_response.data)
                category_stats = {}
                for entry in data_response.data:
                    cat = entry["category"]
                    if cat not in category_stats:
                        category_stats[cat] = {"total": 0, "count": 0, "items": []}
                    category_stats[cat]["total"] += entry["amount"]
                    category_stats[cat]["count"] += 1
                    category_stats[cat]["items"].append((entry["description"], entry["amount"]))

                month_str = target_date.format("YYYY-MM")
                report = f"💰 {month_str} {'個人' if is_personal else '全用戶'}月度報表 💰\n------------------------\n- 總支出：{total:.0f} 元\n- 總筆數：{count} 筆\n\n📊 按類別統計：\n"
                for cat, stats in category_stats.items():
                    report += f"- {cat}: {stats['total']:.0f} 元 ({stats['count']} 筆)\n"
                    for desc, amt in stats["items"]:
                        report += f"  - {desc}: {amt:.0f} 元\n"
                report += f"\n⏰ 報表生成時間：{pendulum.now('UTC').format('YYYY-MM-DD HH:mm')} UTC"
                reply_text = report

        elif text.startswith("刪除 "):
            item_to_delete = text.split(" ", 1)[1].strip()
            data_response = supabase.table("expenses").select("id, description, amount, category").eq("user_id", user_id).eq("description", item_to_delete).order("expense_date", desc=True).limit(1).execute()

            if data_response.data:
                delete_response = supabase.table("expenses").delete().eq("id", data_response.data[0]["id"]).execute()
                if delete_response.data or not delete_response.error:
                    reply_text = f"🗑️ 已刪除：{item_to_delete} ({data_response.data[0]['amount']:.0f} 元, {data_response.data[0]['category']})"
                else:
                    raise Exception("刪除失敗，資料庫錯誤")
            else:
                reply_text = f"⚠️ 找不到「{item_to_delete}」的記帳紀錄"

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        reply_text = f"❌ 操作失敗：{str(e)}"

    try:
        logger.info(f"Replying to user {user_id}: {reply_text}")
        messaging_api.reply_message(
            reply_message_request={
                "replyToken": event.reply_token,
                "messages": [TextMessage(text=reply_text)]
            }
        )
    except Exception as e:
        logger.error(f"Failed to send reply: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)