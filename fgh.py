from bitcoinlib.keys import Key

# Ваш hex-ключ
hex_key = "cf3d8c37a548b60f80621ec2a1c00687f072e24522e0463e800a954d70a11985"

# Создаём объект Key из hex (указываем network='litecoin')
key = Key(import_key=hex_key, network='litecoin')

# Получаем адреса в разных форматах
print("Адрес (P2PKH, начинается с L):", key.address())
print("Адрес (P2SH, начинается с M):", key.address_p2sh())
print("Адрес (Bech32, начинается с ltc1):", key.address_bech32())

# Сравниваем с целевым адресом
target = "ltc1qwzmx3juhztf53txqz5mug7j34pd5wqduks7nfr"
if key.address_bech32() == target:
    print("✅ Ключ ПОДХОДИТ! Адрес совпадает.")
else:
    print("❌ Ключ НЕ ПОДХОДИТ к целевому адресу.")