from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import psycopg2
import os
from datetime import datetime  # ← 加入這行

app = Flask(__name__)

# 從環境變數取得 LINE 憑證
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")

if not channel_access_token or not channel_secret:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 必須設置")

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# 資料庫連線函數
def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname="lineuser",
            user="lineuser_user",
            password="YYHO3ULmmYUfNJeLqULHU0hCCUH6P2WO",
            host="dpg-d0iqhc15pdvs739p5e1g-a.oregon-postgres.render.com",
            port="5432",
            sslmode="require"
        )
        print("資料庫連線成功！")
        return conn
    except Exception as e:
        print(f"資料庫連線失敗: {e}")
        raise

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    print(f"User {user_id} said: {text}")

    if text == "記帳":
        reply_text = "請輸入格式：記帳 項目 金額 類別"

    elif text.startswith("記帳 "):
        try:
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("格式錯誤，請輸入：記帳 項目 金額 類別")

            _, item, amount_str, category = parts
            amount = float(amount_str)

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO expenses (user_id, description, amount, category, expense_date)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (user_id, item, amount, category))
            inserted_id = cur.fetchone()[0]
            conn.commit()
            print(f"成功插入記錄，ID: {inserted_id}")
            cur.close()
            conn.close()

            reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        except ValueError as ve:
            reply_text = str(ve)
            print(f"ValueError: {ve}")
        except Exception as e:
            print(f"Error while recording expense: {e}")
            reply_text = "❌ 記帳失敗，請稍後再試"

    elif text == "總額":
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(SUM(amount), 0), COUNT(*)
                FROM expenses
                WHERE user_id = %s
                  AND DATE_TRUNC('month', expense_date AT TIME ZONE 'UTC') = DATE_TRUNC('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
            """, (user_id,))
            result = cur.fetchone()
            if result:
                total, count = result
                print(f"查詢結果 - 總額: {total}, 筆數: {count}, 查詢時間: {datetime.now()}")  # ✅ 修正
            else:
                print("查詢結果為空！")
                total, count = 0, 0
            cur.close()
            conn.close()

            current_month = datetime.now().strftime("%Y-%m")  # ✅ 自動取得當月
            reply_text = f"💰 {current_month} 總支出：{total:.0f} 元，共 {count} 筆"

        except Exception as e:
            print(f"Error while calculating total: {e}")
            reply_text = "❌ 查詢總額失敗，請稍後再試"

    elif text.startswith("刪除 "):
        try:
            item_to_delete = text.split(" ", 1)[1].strip()
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM expenses 
                WHERE id = (
                    SELECT id FROM expenses 
                    WHERE user_id = %s AND description = %s
                    ORDER BY expense_date DESC
                    LIMIT 1
                )
            """, (user_id, item_to_delete))
            deleted_count = cur.rowcount
            conn.commit()
            cur.close()
            conn.close()

            if deleted_count > 0:
                reply_text = f"🗑️ 已刪除最近一筆「{item_to_delete}」記錄"
            else:
                reply_text = f"⚠️ 找不到「{item_to_delete}」的記帳紀錄"

        except Exception as e:
            print(f"Error while deleting expense: {e}")
            reply_text = "❌ 刪除失敗，請稍後再試"

    else:
        reply_text = "🤖 指令錯誤，請輸入：記帳、總額 或 刪除"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception as e:
        print(f"Error sending reply: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
