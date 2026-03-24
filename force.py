import requests
import time
import logging
import os
from dotenv import load_dotenv

load_dotenv()  # Загружаем переменные из .env

# Настройки
APP_URL = os.getenv('APP_URL', 'https://your-app.onrender.com')  # замените на реальный URL
SYNC_SECRET = os.getenv('SYNC_SECRET', 'your-secret-key')        # тот же ключ, что в app.py
PING_INTERVAL = 600  # 10 минут (в секундах)
SYNC_INTERVAL = 3600 # 1 час (в секундах)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def ping():
    try:
        r = requests.get(f"{APP_URL}/ping", timeout=10)
        if r.status_code == 200:
            logging.info("Ping successful")
        else:
            logging.warning(f"Ping failed with status {r.status_code}")
    except Exception as e:
        logging.error(f"Ping error: {e}")

def sync_ftp():
    try:
        headers = {'X-Sync-Secret': SYNC_SECRET}
        r = requests.post(f"{APP_URL}/sync-ftp", headers=headers, timeout=30)
        if r.status_code == 202:
            logging.info("FTP sync triggered")
        else:
            logging.warning(f"FTP sync failed with status {r.status_code}")
    except Exception as e:
        logging.error(f"FTP sync error: {e}")

def main():
    last_sync = time.time()
    while True:
        ping()
        now = time.time()
        if now - last_sync > SYNC_INTERVAL:
            sync_ftp()
            last_sync = now
        time.sleep(PING_INTERVAL)

if __name__ == '__main__':
    main()
