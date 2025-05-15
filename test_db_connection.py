import psycopg2

# 資料庫連線資訊
DB_NAME = "lineuser"
DB_USER = "lineuser_user"
DB_PASSWORD = "YYHO3ULmmYUfNJeLqULHU0hCCUH6P2WO"
DB_HOST = "dpg-d0iqhc15pdvs739p5e1g-a.oregon-postgres.render.com"
DB_PORT = "5432"

try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode="require"  # Render 要求 SSL 連線
    )
    print("資料庫連線成功！")
    conn.close()
except Exception as e:
    print(f"連線失敗: {e}")