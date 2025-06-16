from flask import Flask, request, abort
from linebot.v3.messaging import MessagingApi, ApiClient, Configuration
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage
import os
from datetime import datetime, timedelta
from supabase import create_client
import logging # 導入 logging 模組

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

# 從環境變數取得 LINE 憑證和 Supabase 設定
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
supabase_url = os.getenv("SUPABASE_URL", "")
supabase_key = os.getenv("SUPABASE_KEY", "")

# 檢查必要的環境變數是否都已設置
if not all([channel_access_token, channel_secret, supabase_url, supabase_key]):
    logging.error("所有必要的環境變數都必須設置：LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, SUPABASE_URL, SUPABASE_KEY")
    raise ValueError("所有必要的環境變數都必須設置！請檢查環境設定。")

# 初始化 LINE Bot API 和 Webhook 處理器
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
handler = WebhookHandler(channel_secret)

# 集中初始化 Supabase 客戶端
supabase = create_client(supabase_url, supabase_key)
logging.info("Supabase 客戶端初始化完成。")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    logging.info(f"收到 Webhook Body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logging.error("無效的簽名錯誤 (InvalidSignatureError)")
        abort(400)
    except Exception as e:
        logging.error(f"Callback 處理時發生錯誤: {e}", exc_info=True)
        abort(500)
    return 'OK'

# --- 指令處理函數 ---

def get_month_boundaries():
    """獲取當前月份的開始和結束時間（UTC）。"""
    now_utc = datetime.utcnow()
    start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # 計算下個月的第一天，然後減去 1 微秒即可得到本月的最後一個微秒
    if now_utc.month == 12:
        first_day_next_month = datetime(now_utc.year + 1, 1, 1, 0, 0, 0, 0)
    else:
        first_day_next_month = datetime(now_utc.year, now_utc.month + 1, 1, 0, 0, 0, 0)
    
    end_of_month = first_day_next_month - timedelta(microseconds=1)
    
    return start_of_month, end_of_month, now_utc.strftime("%Y-%m")

def handle_record_expense(user_id: str, message_text: str) -> str:
    """處理記帳指令"""
    try:
        parts = message_text.split()
        if len(parts) != 4:
            return "格式錯誤，請輸入：記帳 項目 金額 類別"

        _, item, amount_str, category = parts
        amount = float(amount_str)
        if amount <= 0:
            return "金額必須大於 0"

        data_to_insert = {
            "user_id": user_id,
            "description": item,
            "amount": amount,
            "category": category,
            "expense_date": datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
        }
        
        data_response = supabase.table("expenses").insert(data_to_insert).execute()

        if data_response.error:
            logging.error(f"Supabase 記帳錯誤 (user_id: {user_id}, data: {data_to_insert}): {data_response.error}")
            return f"❌ 記帳失敗，Supabase 回報錯誤：{data_response.error.get('message', '未知錯誤')}"
        elif data_response.data: # 檢查 data 是否有內容 (表示成功插入)
            logging.info(f"成功記帳 (user_id: {user_id}): {item} - {amount} 元 - {category}")
            return f"✅ 已記帳：{item} - {amount} 元 - {category}"
        else: # 即使 data 為空列表，但無 error 也視為成功
            logging.warning(f"記帳成功但 Supabase 返回空數據 (user_id: {user_id})")
            return f"✅ 已記帳：{item} - {amount} 元 - {category} (資料庫已更新)"

    except ValueError as ve:
        logging.warning(f"記帳格式錯誤 (user_id: {user_id}, text: {message_text}): {ve}")
        return str(ve)
    except Exception as e:
        logging.error(f"處理記帳時發生未預期錯誤 (user_id: {user_id}, text: {message_text}): {e}", exc_info=True)
        return "❌ 記帳失敗，請稍後再試"

def handle_total_expense(user_id: str) -> str:
    """計算並回報當月總支出"""
    try:
        start_of_month, end_of_month, current_month_str = get_month_boundaries()

        data_response = supabase.table("expenses").select("amount").eq("user_id", user_id).gte(
            "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
        ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

        if data_response.error:
            logging.error(f"Supabase 查詢總額錯誤 (user_id: {user_id}): {data_response.error}")
            return f"❌ 查詢總額失敗，Supabase 回報錯誤：{data_response.error.get('message', '未知錯誤')}"

        total = sum(entry["amount"] for entry in data_response.data) if data_response.data else 0
        count = len(data_response.data)
        
        logging.info(f"成功查詢總額 (user_id: {user_id}): {current_month_str} 總支出 {total} 元，共 {count} 筆。")
        return f"💰 {current_month_str} 總支出：{total:.0f} 元，共 {count} 筆 (個人)"

    except Exception as e:
        logging.error(f"處理總額查詢時發生未預期錯誤 (user_id: {user_id}): {e}", exc_info=True)
        return "❌ 查詢總額失敗，請稍後再試"

def handle_monthly_report(user_id: str) -> str:
    """生成當月月度報表"""
    try:
        start_of_month, end_of_month, current_month_str = get_month_boundaries()

        data_response = supabase.table("expenses").select("*").eq("user_id", user_id).gte(
            "expense_date", start_of_month.isoformat(timespec='milliseconds') + "Z"
        ).lte("expense_date", end_of_month.isoformat(timespec='milliseconds') + "Z").execute()

        if data_response.error:
            logging.error(f"Supabase 查詢月報錯誤 (user_id: {user_id}): {data_response.error}")
            return f"❌ 生成月度報表失敗，Supabase 回報錯誤：{data_response.error.get('message', '未知錯誤')}"

        total = sum(entry["amount"] for entry in data_response.data) if data_response.data else 0
        count = len(data_response.data)

        category_stats = {}
        for entry in data_response.data:
            cat = entry.get("category", "未分類") # 處理可能沒有類別的情況
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "count": 0, "items": []}
            category_stats[cat]["total"] += entry["amount"]
            category_stats[cat]["count"] += 1
            # 只儲存最近的幾筆或限制列表長度以避免訊息過長
            if len(category_stats[cat]["items"]) < 5: # 例如，每個類別只顯示前5項
                category_stats[cat]["items"].append((entry["description"], entry["amount"]))

        report = f"💰 {current_month_str} 月度報表 💰\n------------------------\n- 總支出：{total:.0f} 元\n- 總筆數：{count} 筆\n\n📊 按類別統計：\n"
        for cat, stats in sorted(category_stats.items()): # 按類別名稱排序
            report += f"- {cat}: {stats['total']:.0f} 元 ({stats['count']} 筆)\n"
            for desc, amt in stats["items"]:
                report += f"  - {desc}: {amt:.0f} 元\n"
        
        if not category_stats: # 如果沒有數據
            report += "  (本月尚無支出記錄)"

        report += f"\n⏰ 報表生成時間：{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        
        logging.info(f"成功生成月度報表 (user_id: {user_id})")
        return report

    except Exception as e:
        logging.error(f"處理月度報表時發生未預期錯誤 (user_id: {user_id}): {e}", exc_info=True)
        return "❌ 生成月度報表失敗，請稍後再試"

def handle_delete_expense(user_id: str, message_text: str) -> str:
    """刪除最近一筆指定項目的記帳記錄"""
    try:
        item_to_delete = message_text.split(" ", 1)[1].strip()
        if not item_to_delete:
            return "請輸入要刪除的項目，例如：刪除 午餐"

        # 查詢最近一筆符合條件的記錄
        data_response = supabase.table("expenses").select("id").eq("user_id", user_id).eq("description", item_to_delete).order("expense_date", desc=True).limit(1).execute()

        if data_response.error:
            logging.error(f"Supabase 查詢刪除項目錯誤 (user_id: {user_id}, item: {item_to_delete}): {data_response.error}")
            return f"❌ 刪除失敗，查詢資料庫時發生錯誤：{data_response.error.get('message', '未知錯誤')}"

        if data_response.data:
            record_id_to_delete = data_response.data[0]["id"]
            delete_response = supabase.table("expenses").delete().eq("id", record_id_to_delete).execute()
            
            if delete_response.error:
                logging.error(f"Supabase 執行刪除錯誤 (user_id: {user_id}, record_id: {record_id_to_delete}): {delete_response.error}")
                return f"❌ 刪除失敗，執行刪除操作時發生錯誤：{delete_response.error.get('message', '未知錯誤')}"
            
            logging.info(f"成功刪除記帳記錄 (user_id: {user_id}, item: {item_to_delete}, id: {record_id_to_delete})")
            return f"🗑️ 已刪除最近一筆「{item_to_delete}」記錄"
        else:
            logging.info(f"找不到要刪除的記帳記錄 (user_id: {user_id}, item: {item_to_delete})")
            return f"⚠️ 找不到「{item_to_delete}」的記帳紀錄"

    except IndexError:
        return "請輸入格式：刪除 項目"
    except Exception as e:
        logging.error(f"處理刪除指令時發生未預期錯誤 (user_id: {user_id}, text: {message_text}): {e}", exc_info=True)
        return "❌ 刪除失敗，請稍後再試"

# --- 指令分派器 ---
command_handlers = {
    "記帳": handle_record_expense,
    "總額": handle_total_expense,
    "月報": handle_monthly_report,
    "刪除": handle_delete_expense,
}

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    logging.info(f"使用者 {user_id} 傳送訊息: {text}")

    reply_text = "🤖 指令錯誤，請輸入：記帳、總額、月報 或 刪除"

    # 根據訊息開頭來判斷並呼叫對應的處理函數
    if text.startswith("記帳"):
        reply_text = command_handlers["記帳"](user_id, text)
    elif text == "總額":
        reply_text = command_handlers["總額"](user_id)
    elif text == "月報":
        reply_text = command_handlers["月報"](user_id)
    elif text.startswith("刪除"):
        reply_text = command_handlers["刪除"](user_id, text)
    
    try:
        logging.info(f"準備回覆使用者 {user_id}: {reply_text}")
        messaging_api.reply_message(
            reply_message_request={
                "replyToken": event.reply_token,
                "messages": [TextMessage(text=reply_text)]
            }
        )
    except Exception as e:
        logging.error(f"回覆訊息時發生錯誤 (user_id: {user_id}, reply_text: {reply_text}): {e}", exc_info=True)

if __name__ == "__main__":
    # 在生產環境中，建議使用 Gunicorn 或其他 WSGI 伺服器來運行 Flask
    # 例如: gunicorn -w 4 -b 0.0.0.0:5000 app:app
    app.run(host="0.0.0.0", port=5000)