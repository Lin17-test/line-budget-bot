from flask import Flask, request, abort
from linebot.v3.messaging import MessagingApi, ApiClient, Configuration
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import TextMessage
import psycopg2
import os
from datetime import datetime

app = Flask(__name__)

# 從環境變數取得 LINE 憑證
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")

if not channel_access_token or not channel_secret:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 必須設置")

# 初始化 LINE Bot API 和 Webhook 處理器
configuration = Configuration(access_token=channel_access_token)
line_bot_api = ApiClient(configuration=configuration)
messaging_api = MessagingApi(line_bot_api)
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

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO expenses (user_id, description, amount, category, expense_date)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                RETURNING id
            """, (user_id, item, amount, category))
            inserted_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

            reply_text = f"✅ 已記帳：{item} - {amount} 元 - {category}"

        except ValueError as ve:
            reply_text = str(ve)
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
            total, count = cur.fetchone()
            cur.execute("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")
            current_time = cur.fetchone()[0]
            cur.close()
            conn.close()

            current_month = datetime.utcnow().strftime("%Y-%m")
            reply_text = f"💰 {current_month} 總支出：{total:.0f} 元，共 {count} 筆 (個人)"

        except Exception as e:
            print(f"Error while calculating total: {e}")
            reply_text = "❌ 查詢總額失敗，請稍後再試"

    elif text == "月報":
        try:
            current_month = datetime.utcnow().strftime("%Y-%m")
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(SUM(amount), 0), COUNT(*)
                FROM expenses
                WHERE DATE_TRUNC('month', expense_date AT TIME ZONE 'UTC') = DATE_TRUNC('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
            """)
            total, count = cur.fetchone()
            cur.execute("""
                SELECT category, COALESCE(SUM(amount), 0), COUNT(*)
                FROM expenses
                WHERE DATE_TRUNC('month', expense_date AT TIME ZONE 'UTC') = DATE_TRUNC('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                GROUP BY category
            """)
            category_stats = cur.fetchall()
            cur.execute("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")
            current_time = cur.fetchone()[0]

            report = f"💰 {current_month} 月度報表 💰\n------------------------\n- 總支出：{total:.0f} 元\n- 總筆數：{count} 筆\n\n📊 按類別統計：\n"
            for cat, cat_total, cat_count in category_stats:
                report += f"- {cat}: {cat_total:.0f} 元 ({cat_count} 筆)\n"
                cur.execute("""
                    SELECT description, amount
                    FROM expenses
                    WHERE category = %s
                      AND DATE_TRUNC('month', expense_date AT TIME ZONE 'UTC') = DATE_TRUNC('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
                """, (cat,))
                items = cur.fetchall()
                for desc, amt in items:
                    report += f"  - {desc}: {amt:.0f} 元\n"

            report += f"\n⏰ 報表生成時間：{current_time.strftime('%Y-%m-%d %H:%M')} CST"
            cur.close()
            conn.close()

            reply_text = report

        except Exception as e:
            print(f"Error while generating monthly report: {e}")
            reply_text = "❌ 生成月度報表失敗，請稍後再試"

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
