import psycopg2

# 資料庫連線設定
conn = psycopg2.connect(
    dbname="lineuser",
    user="lineuser_user",
    password="YYHO3ULmmYUfNJeLqULHU0hCCUH6P2WO",
    host="dpg-d0iqhc15pdvs739p5e1g-a.oregon-postgres.render.com",
    port="5432",
    sslmode="require"
)

# 建立資料表 expenses
create_table_sql = """
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    expense_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

try:
    cur = conn.cursor()
    cur.execute(create_table_sql)
    conn.commit()
    cur.close()
    print("✅ 資料表 expenses 已建立或已存在")
except Exception as e:
    print(f"❌ 建立資料表時發生錯誤: {e}")
finally:
    conn.close()