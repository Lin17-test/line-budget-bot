import psycopg2

# 資料庫連線資訊
DB_NAME = "lineuser"
DB_USER = "lineuser_user"
DB_PASSWORD = "YYHO3ULmmYUfNJeLqULHU0hCCUH6P2WO"
DB_HOST = "dpg-d0iqhc15pdvs739p5e1g-a.oregon-postgres.render.com"
DB_PORT = "5432"

try:
    # 連線到資料庫
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode="require"
    )
    cur = conn.cursor()

    # 查詢所有記錄
    cur.execute("SELECT user_id, amount, category, description, expense_date FROM expenses")
    records = cur.fetchall()

    print("資料庫中的記錄：")
    for record in records:
        print(record)

    cur.close()
    conn.close()

except Exception as e:
    print(f"查詢失敗: {e}")