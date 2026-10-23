import sqlite3

con = sqlite3.connect('data/exchange.db')
cursor = con.cursor()

rates = [
    ("rate_usdt_buy", "95"),
    ("rate_usdt_sell", "90"),
    ("rate_trx_buy", "12"),
    ("rate_trx_sell", "10"),
    ("rate_btc_buy", "7000000"),
    ("rate_btc_sell", "6800000"),
    ("rate_ltc_buy", "6000"),
    ("rate_ltc_sell", "5500")
]

for key, value in rates:
    cursor.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', (key, value))

con.commit()
con.close()
print("✅ Курсы успешно добавлены в базу!")