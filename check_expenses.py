import psycopg2

conn = psycopg2.connect(
    dbname="lineuser",
    user="lineuser_user",
    password="YYHO3ULmmYUfNJeLqULHU0hCCUH6P2WO",
    host="dpg-d0iqhc15pdvs739p5e1g-a.oregon-postgres.render.com",
    port="5432",
    sslmode="require"
)

try:
    cur = conn.cursor()
    cur.execute("SELECT user_id, description, amount, category, expense_date FROM expenses")
    records = cur.fetchall()
    if records:
        print("資料庫中的記錄：")
        for record in records:
            print(record)
    else:
        print("資料庫中沒有記錄！")
except Exception as e:
    print(f"查詢失敗: {e}")
finally:
    cur.close()
    conn.close()