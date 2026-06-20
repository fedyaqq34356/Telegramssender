from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS, BROADCAST_CONFIG, get_random_delay
from storage import storage
from states import Broadcaster
import keyboards as kb
import auth
from logger import logger
from export import create_export_files
import asyncio
from telethon.tl.types import ChannelParticipantsAdmins, Channel
from telethon.errors.rpcerrorlist import (
    PeerFloodError, UserPrivacyRestrictedError,
    FloodWaitError, UserIsBlockedError
)
import re

router = Router()


def extract_username_from_link(link):
    if link.startswith('@'):
        return link
    patterns = [
        r't\.me/([a-zA-Z0-9_]+)',
        r'telegram\.me/([a-zA-Z0-9_]+)',
        r'tg://resolve\?domain=([a-zA-Z0-9_]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return '@' + match.group(1)
    if link.lstrip('-').isdigit():
        return link
    return link


@router.message(F.text == "📨 Рассылка")
async def broadcast_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.accounts:
        await msg.answer("Додайте акаунт спочатку")
        return
    if not storage.source_groups:
        await msg.answer("Додайте джерело спочатку")
        return
    text = "Виберіть акаунт:\n\n"
    for i, (name, data) in enumerate(storage.accounts.items(), 1):
        today_broadcasts = storage.get_today_broadcasts(name)
        remaining = BROADCAST_CONFIG["max_broadcasts_per_day"] - today_broadcasts
        text += f"{i}. {name} ({data['phone']}) - залишилось: {remaining}\n"
    await state.set_state(Broadcaster.select_account)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(Broadcaster.select_account)
async def broadcast_select_account(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    try:
        idx = int(msg.text) - 1
        accounts_list = list(storage.accounts.keys())
        if 0 <= idx < len(accounts_list):
            account_name = accounts_list[idx]
            today_broadcasts = storage.get_today_broadcasts(account_name)
            if today_broadcasts >= BROADCAST_CONFIG["max_broadcasts_per_day"]:
                await state.clear()
                await msg.answer(f"Досягнуто денний ліміт ({BROADCAST_CONFIG['max_broadcasts_per_day']})", reply_markup=kb.main())
                return
            remaining = BROADCAST_CONFIG["max_broadcasts_per_day"] - today_broadcasts
            await state.update_data(account_name=account_name)
            text = f"Залишилось на сьогодні: {remaining}\n\nВиберіть джерело:\n\n"
            for i, g in enumerate(storage.source_groups, 1):
                text += f"{i}. {g}\n"
            await state.set_state(Broadcaster.select_source)
            await msg.answer(text, reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(Broadcaster.select_source)
async def broadcast_select_source(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    try:
        idx = int(msg.text) - 1
        if 0 <= idx < len(storage.source_groups):
            group = storage.source_groups[idx]
            await state.update_data(group=group)
            await state.set_state(Broadcaster.messages_limit)
            await msg.answer("Скільки повідомлень проаналізувати? (10-10000):", reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(Broadcaster.messages_limit)
async def broadcast_messages_limit(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    try:
        limit = int(msg.text)
        if not (10 <= limit <= 10000):
            await msg.answer("Введіть число від 10 до 10000:")
            return
        await state.update_data(messages_limit=limit)
        await state.set_state(Broadcaster.message_text)
        await msg.answer("Введіть текст розсилки:", reply_markup=kb.cancel())
    except ValueError:
        await msg.answer("Введіть число:")


@router.message(Broadcaster.message_text)
async def broadcast_execute(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    data = await state.get_data()
    account_name = data["account_name"]
    account_data = storage.accounts[account_name]
    group = data["group"]
    messages_limit = data["messages_limit"]
    broadcast_text = msg.text
    today_broadcasts = storage.get_today_broadcasts(account_name)
    session_limit = min(
        BROADCAST_CONFIG["max_broadcasts_per_session"],
        BROADCAST_CONFIG["max_broadcasts_per_day"] - today_broadcasts
    )
    if session_limit <= 0:
        await state.clear()
        await msg.answer("Досягнуто денний ліміт", reply_markup=kb.main())
        return
    await msg.answer(f"Перевірка джерела...")
    client = await auth.get_client(account_name, account_data["api_id"], account_data["api_hash"])
    try:
        group_identifier = extract_username_from_link(group)
        group_entity = None
        try:
            if group_identifier.startswith('@'):
                group_entity = await client.get_entity(group_identifier)
            elif group_identifier.lstrip('-').isdigit():
                group_entity = await client.get_entity(int(group_identifier))
            else:
                group_entity = await client.get_entity(group_identifier)
        except ValueError:
            search_term = group_identifier.lstrip('@').lower()
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    username_match = (hasattr(dialog.entity, 'username') and
                                      dialog.entity.username and
                                      dialog.entity.username.lower() == search_term)
                    id_match = str(dialog.entity.id) == group_identifier.lstrip('-')
                    if username_match or id_match:
                        group_entity = dialog.entity
                        await msg.answer(f"Знайдено: {dialog.title}")
                        break
            if not group_entity:
                raise ValueError(f"Група '{group}' не знайдена")

        is_channel = isinstance(group_entity, Channel) and group_entity.broadcast
        
        if is_channel:
            await state.clear()
            await msg.answer(
                "❌ ЦЕ КАНАЛ!\n\n"
                "Повідомлення в каналах від імені каналу.\n"
                "Парсинг користувачів неможливий.\n\n"
                "💡 Використовуйте ГРУПИ!",
                reply_markup=kb.main()
            )
            return

        await msg.answer("✅ Це група - можна парсити!")
        await msg.answer("Отримання адміністраторів...")
        admin_ids = set()
        try:
            admins = await client.get_participants(group_entity, filter=ChannelParticipantsAdmins())
            admin_ids = {admin.id for admin in admins}
        except Exception as e:
            logger.error(f"Помилка адмінів: {e}")

        unique_users = {}
        messages_checked = 0
        await msg.answer(f"Парсинг з {messages_limit} повідомлень...")

        async for message in client.iter_messages(group_entity, limit=messages_limit):
            messages_checked += 1
            if messages_checked % 500 == 0:
                await msg.answer(f"Повідомлень: {messages_checked}, юзерів: {len(unique_users)}")
            if not message.sender:
                continue
            sender = message.sender
            if not hasattr(sender, 'bot'):
                continue
            if sender.id in admin_ids or sender.bot or sender.deleted:
                continue
            if sender.id not in unique_users:
                try:
                    if not hasattr(sender, 'access_hash') or not sender.access_hash:
                        continue
                    unique_users[sender.id] = {
                        "id": sender.id,
                        "access_hash": sender.access_hash,
                        "username": getattr(sender, 'username', '') or "",
                        "first_name": getattr(sender, 'first_name', '') or "",
                        "has_avatar": sender.photo is not None
                    }
                except Exception as e:
                    logger.error(f"Помилка: {e}")

        real_users = list(unique_users.values())
        await msg.answer(f"Знайдено {len(real_users)} юзерів. Початок розсилки (ліміт: {session_limit})...")

        success = 0
        failed = 0
        privacy_errors = 0
        session_count = 0
        skipped = 0
        sent_users = []

        for user in real_users:
            if session_count >= session_limit:
                await msg.answer(f"Ліміт сесії ({session_limit})")
                break
            if not await auth.check_client_connection(client):
                await msg.answer("⚠️ З'єднання втрачено")
                break
            try:
                if not user.get('access_hash') or user['access_hash'] == 0:
                    skipped += 1
                    continue
                await client.send_message(user['id'], broadcast_text)
                success += 1
                session_count += 1
                sent_users.append(user)
                storage.increment_broadcasts(account_name)
                if success % 2 == 0:
                    await msg.answer(f"Надіслано: {success}, Помилок: {failed}")
                await asyncio.sleep(get_random_delay(BROADCAST_CONFIG["delay_between_messages"]))
            except UserPrivacyRestrictedError:
                privacy_errors += 1
                failed += 1
                await asyncio.sleep(get_random_delay(BROADCAST_CONFIG["delay_after_error"]))
            except UserIsBlockedError:
                failed += 1
                await asyncio.sleep(get_random_delay(BROADCAST_CONFIG["delay_after_error"]))
            except PeerFloodError:
                failed += 1
                await msg.answer("⚠️ PEER_FLOOD!")
                break
            except FloodWaitError as e:
                if e.seconds > 300:
                    await msg.answer(f"⚠️ FloodWait {e.seconds//60} хв")
                    break
                await asyncio.sleep(e.seconds + 10)
            except Exception as e:
                failed += 1
                logger.error(f"Помилка: {e}")
                if "PEER_FLOOD" in str(e):
                    break
                await asyncio.sleep(get_random_delay(BROADCAST_CONFIG["delay_after_error"]))

        total_today = storage.get_today_broadcasts(account_name)
        text = (f"✅ Розсилка завершено!\n\n"
                f"Успішно: {success}\n"
                f"Невдало: {failed}\n"
                f"Приватність: {privacy_errors}\n"
                f"Всього сьогодні: {total_today}")
        await state.clear()
        await msg.answer(text, reply_markup=kb.main())

        if sent_users:
            xlsx, csv = create_export_files(sent_users, "broadcast")
            await msg.answer_document(FSInputFile(xlsx), caption=f"Отримувачі ({success})")

    except Exception as e:
        await state.clear()
        await msg.answer(f"Помилка: {e}", reply_markup=kb.main())
        logger.error(f"Помилка: {e}")


@router.message(F.text == "📊 Статистика розсилки")
async def broadcast_stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.accounts:
        await msg.answer("Акаунтів немає")
        return
    text = "Статистика:\n\n"
    for account_name in storage.accounts.keys():
        today = storage.get_today_broadcasts(account_name)
        remaining = BROADCAST_CONFIG["max_broadcasts_per_day"] - today
        text += f"{account_name}:\n  Сьогодні: {today}\n  Залишилось: {remaining}\n\n"
    await msg.answer(text)