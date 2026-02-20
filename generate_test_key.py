from bitcoinlib.keys import Key

# Генерация нового ключа в тестовой сети Bitcoin
key = Key(network='testnet')

print("=== Bitcoin Testnet Key ===")
print(f"Приватный ключ (WIF): {key.wif()}")
print(f"Публичный адрес: {key.address()}")
print(f"Тип адреса: {key.address_type}")
print("\nЭти данные можно использовать для добавления кошелька в админку.")