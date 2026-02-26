import sqlite3
conn = sqlite3.connect('data/exchange.db')
cursor = conn.cursor()
cursor.execute("SELECT user_id, is_active FROM partners WHERE user_id = 6422018512")
row = cursor.fetchone()
if row:
    print(f"Найден: user_id={row[0]}, is_active={row[1]}")
else:
    print("Запись не найдена")
conn.close()