from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from pathlib import Path
from logger import logger
import asyncio
import random

DEVICE_MODELS = [
    "Honor HONOR 70", "Samsung Galaxy S21", "Xiaomi Mi 11", "Google Pixel 6",
    "OnePlus 9", "Sony Xperia 5", "Huawei P50", "Nokia X20", "Motorola Edge 20",
    "Apple iPhone 13", "Apple iPhone 14", "Apple iPhone 15", "PC"
]

SYSTEM_VERSIONS = [
    "SDK 35", "SDK 34", "SDK 33", "SDK 32", "SDK 31", "SDK 30",
    "SDK 29", "SDK 28", "SDK 27", "iOS 15.4", "iOS 16.0", "iOS 17.0",
    "Windows 11", "Ubuntu 22.04", "Arch Linux", "Fedora 38"
]

APP_VERSIONS = [
    "Telegram Android 11.13.1", "Telegram Android 11.12.0", "Telegram Android 11.11.0",
    "Telegram Android 11.10.0", "Telegram Android 11.9.0", "Telegram Android 11.8.0",
    "Telegram Android 11.7.0", "Telegram Android 11.6.0", "Telegram Android 11.5.0",
    "Telegram iOS 10.4.1", "Telegram iOS 10.0.0", "Telegram iOS 11.0.0", "1.0"
]

def get_random_device():
    return {
        "device_model": random.choice(DEVICE_MODELS),
        "system_version": random.choice(SYSTEM_VERSIONS),
        "app_version": random.choice(APP_VERSIONS),
        "lang_code": "ru",
        "system_lang_code": "ru-RU"
    }

sessions = {}
active_clients = {}


async def start(user_id, name, api_id, api_hash, phone):
    try:
        Path("sessions").mkdir(exist_ok=True)
        
        device = get_random_device()
        
        client = TelegramClient(
            f"sessions/{name}",
            api_id,
            api_hash,
            device_model=device["device_model"],
            system_version=device["system_version"],
            app_version=device["app_version"],
            lang_code=device["lang_code"],
            system_lang_code=device["system_lang_code"]
        )
        await client.connect()
        
        if await client.is_user_authorized():
            await client.disconnect()
            return False, "Акаунт вже авторизований"
        
        await client.send_code_request(phone)
        
        sessions[user_id] = {
            "client": client,
            "phone": phone,
            "name": name,
            "api_id": api_id,
            "api_hash": api_hash
        }
        
        logger.info(f"Запит коду для {phone}")
        return True, "Код надіслано"
    except Exception as e:
        logger.error(f"Помилка авторизації: {e}")
        return False, str(e)


async def verify_code(user_id, code):
    if user_id not in sessions:
        return False, "Сесія не знайдена"
    
    session = sessions[user_id]
    
    try:
        await session["client"].sign_in(session["phone"], code)
        
        from storage import storage
        storage.add_account(
            session["name"],
            session["api_id"],
            session["api_hash"],
            session["phone"]
        )
        
        await session["client"].disconnect()
        del sessions[user_id]
        
        logger.info(f"Авторизовано: {session['name']}")
        return True, "Акаунт додано"
        
    except SessionPasswordNeededError:
        return "2fa", "Введіть пароль 2FA"
    except PhoneCodeInvalidError:
        return "retry", "Невірний код"
    except Exception as e:
        logger.error(f"Помилка коду: {e}")
        return False, str(e)


async def verify_password(user_id, password):
    if user_id not in sessions:
        return False, "Сесія не знайдена"
    
    session = sessions[user_id]
    
    try:
        await session["client"].sign_in(password=password)
        
        from storage import storage
        storage.add_account(
            session["name"],
            session["api_id"],
            session["api_hash"],
            session["phone"]
        )
        
        await session["client"].disconnect()
        del sessions[user_id]
        
        logger.info(f"Авторизовано з 2FA: {session['name']}")
        return True, "Акаунт додано"
    except Exception as e:
        logger.error(f"Помилка паролю: {e}")
        return False, str(e)


async def cancel(user_id):
    if user_id in sessions:
        if sessions[user_id]["client"].is_connected():
            await sessions[user_id]["client"].disconnect()
        del sessions[user_id]
        logger.info(f"Скасовано авторизацію: {user_id}")


async def get_client(name, api_id, api_hash):
    if name in active_clients:
        client = active_clients[name]
        if client.is_connected():
            logger.info(f"Використання існуючого клієнта: {name}")
            return client
        else:
            logger.warning(f"Клієнт {name} відключений, перепідключення...")
            del active_clients[name]
    
    Path("sessions").mkdir(exist_ok=True)
    
    for attempt in range(3):
        try:
            device = get_random_device()
            
            client = TelegramClient(
                f"sessions/{name}",
                api_id,
                api_hash,
                device_model=device["device_model"],
                system_version=device["system_version"],
                app_version=device["app_version"],
                lang_code=device["lang_code"],
                system_lang_code=device["system_lang_code"]
            )
            await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Клієнт не авторизований")
            
            active_clients[name] = client
            logger.info(f"Створено новий клієнт: {name}")
            return client
        except Exception as e:
            if "database is locked" in str(e):
                logger.warning(f"База заблокована, спроба {attempt + 1}/3")
                await asyncio.sleep(1)
                continue
            logger.error(f"Помилка підключення {name}: {e}")
            raise
    
    raise Exception("Не вдалося підключитися: база даних заблокована")


async def disconnect_client(name):
    if name in active_clients:
        try:
            await active_clients[name].disconnect()
            del active_clients[name]
            logger.info(f"Відключено клієнт: {name}")
        except Exception as e:
            logger.error(f"Помилка відключення {name}: {e}")


async def check_client_connection(client):
    try:
        return client.is_connected()
    except:
        return False