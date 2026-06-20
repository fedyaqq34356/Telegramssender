# handlers/parser.py

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from storage import storage
from states import Parser
import keyboards as kb
import auth
from logger import logger
from export import create_export_files
from telethon.tl.types import ChannelParticipantsAdmins, Channel, Chat
from telethon.errors import ChatAdminRequiredError
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


@router.message(F.text == "🔍 Парсинг")
async def parse_start(msg: Message, state: FSMContext):
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
        text += f"{i}. {name} ({data['phone']})\n"
    
    await state.set_state(Parser.select_account)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(Parser.select_account)
async def parse_select_account(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    try:
        idx = int(msg.text) - 1
        accounts_list = list(storage.accounts.keys())
        
        if 0 <= idx < len(accounts_list):
            account_name = accounts_list[idx]
            await state.update_data(account_name=account_name)
            
            text = "Виберіть джерело:\n\n"
            for i, g in enumerate(storage.source_groups, 1):
                text += f"{i}. {g}\n"
            
            await state.set_state(Parser.select_group)
            await msg.answer(text, reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(Parser.select_group)
async def parse_messages_limit(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    try:
        idx = int(msg.text) - 1
        
        if 0 <= idx < len(storage.source_groups):
            group = storage.source_groups[idx]
            await state.update_data(group=group)
            await state.set_state(Parser.messages_limit)
            await msg.answer("Скільки повідомлень проаналізувати? (10-10000):", reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(Parser.messages_limit)
async def parse_group(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    try:
        limit = int(msg.text)
        
        if not (10 <= limit <= 10000):
            await msg.answer("Введіть число від 10 до 10000:")
            return
        
        data = await state.get_data()
        group = data["group"]
        account_name = data["account_name"]
        account_data = storage.accounts[account_name]
        
        await msg.answer(f"Перевірка типу чату...")
        
        client = await auth.get_client(
            account_name,
            account_data["api_id"],
            account_data["api_hash"]
        )
        
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
                    "В каналах:\n"
                    "• Список підписників ЗАКРИТИЙ\n"
                    "• Повідомлення від імені каналу\n"
                    "• Парсинг НЕМОЖЛИВИЙ без прав адміністратора\n\n"
                    "💡 Використовуйте ГРУПИ для парсингу!",
                    reply_markup=kb.main()
                )
                return
            
            await msg.answer("✅ Це ГРУПА - можна парсити!")
            await msg.answer("Отримання списку адміністраторів...")
            
            admin_ids = set()
            try:
                admins = await client.get_participants(
                    group_entity, 
                    filter=ChannelParticipantsAdmins()
                )
                admin_ids = {admin.id for admin in admins}
                await msg.answer(f"Знайдено {len(admin_ids)} адміністраторів")
            except Exception as e:
                logger.error(f"Помилка адмінів: {e}")
            
            unique_users = {}
            admin_users = {}
            bot_users = {}
            parse_method = None
            
            try:
                await msg.answer("Спроба парсити ВСІХ учасників...")
                participants_count = 0
                
                async for user in client.iter_participants(group_entity):
                    participants_count += 1
                    
                    if participants_count % 500 == 0:
                        await msg.answer(f"Оброблено: {participants_count}, знайдено: {len(unique_users)}")
                    
                    if not hasattr(user, 'bot'):
                        continue
                    
                    if user.deleted:
                        continue
                    
                    try:
                        if not hasattr(user, 'access_hash') or not user.access_hash:
                            continue
                        
                        user_data = {
                            "id": user.id,
                            "access_hash": user.access_hash,
                            "username": getattr(user, 'username', '') or "",
                            "first_name": getattr(user, 'first_name', '') or "",
                            "last_name": getattr(user, 'last_name', '') or "",
                            "has_avatar": user.photo is not None
                        }
                        
                        if user.bot:
                            bot_users[user.id] = user_data
                        elif user.id in admin_ids:
                            admin_users[user.id] = user_data
                        else:
                            unique_users[user.id] = user_data
                    except Exception as e:
                        logger.error(f"Помилка: {e}")
                
                parse_method = "all_participants"
                await msg.answer(f"✅ Спарсено учасників зі списку")
                
            except (ChatAdminRequiredError, Exception) as e:
                logger.warning(f"Немає доступу до списку: {e}")
                await msg.answer("⚠️ Список закритий - парсинг по повідомленнях")
                
                unique_users = {}
                admin_users = {}
                bot_users = {}
                messages_checked = 0
                
                async for message in client.iter_messages(group_entity, limit=limit):
                    messages_checked += 1
                    
                    if messages_checked % 500 == 0:
                        await msg.answer(f"Повідомлень: {messages_checked}, юзерів: {len(unique_users)}")
                    
                    if not message.sender:
                        continue
                    
                    sender = message.sender
                    
                    if not hasattr(sender, 'bot'):
                        continue
                    
                    if sender.deleted:
                        continue
                    
                    if sender.id not in unique_users and sender.id not in admin_users and sender.id not in bot_users:
                        try:
                            if not hasattr(sender, 'access_hash') or not sender.access_hash:
                                continue
                            
                            user_data = {
                                "id": sender.id,
                                "access_hash": sender.access_hash,
                                "username": getattr(sender, 'username', '') or "",
                                "first_name": getattr(sender, 'first_name', '') or "",
                                "last_name": getattr(sender, 'last_name', '') or "",
                                "has_avatar": sender.photo is not None
                            }
                            
                            if sender.bot:
                                bot_users[sender.id] = user_data
                            elif sender.id in admin_ids:
                                admin_users[sender.id] = user_data
                            else:
                                unique_users[sender.id] = user_data
                        except Exception as e:
                            logger.error(f"Помилка: {e}")
                
                parse_method = "messages"
            
            real_users = list(unique_users.values())
            real_admins = list(admin_users.values())
            real_bots = list(bot_users.values())
            
            storage.save_parsed_users(real_users, real_admins, real_bots)
            
            method_text = "всіх учасників" if parse_method == "all_participants" else "тих хто писав"
            text = (f"✅ Парсинг завершено!\n\n"
                    f"Юзерів: {len(real_users)}\n"
                    f"Адмінів: {len(real_admins)}\n"
                    f"Ботів: {len(real_bots)}\n"
                    f"Метод: {method_text}")
            
            await state.clear()
            await msg.answer(text, reply_markup=kb.main())
            
            if real_users:
                await msg.answer("Формую файли...")
                xlsx, csv = create_export_files(real_users, "parsed_users")
                await msg.answer_document(FSInputFile(xlsx), caption=f"Юзери ({len(real_users)})")
                await msg.answer_document(FSInputFile(csv), caption=f"Юзери ({len(real_users)})")
            
            if real_admins:
                xlsx, csv = create_export_files(real_admins, "parsed_admins")
                await msg.answer_document(FSInputFile(xlsx), caption=f"Адміни ({len(real_admins)})")
                await msg.answer_document(FSInputFile(csv), caption=f"Адміни ({len(real_admins)})")
            
            if real_bots:
                xlsx, csv = create_export_files(real_bots, "parsed_bots")
                await msg.answer_document(FSInputFile(xlsx), caption=f"Боти ({len(real_bots)})")
                await msg.answer_document(FSInputFile(csv), caption=f"Боти ({len(real_bots)})")
            
            logger.info(f"Завершено: {len(real_users)} користувачів, {len(real_admins)} адмінів, {len(real_bots)} ботів")
            
        except Exception as e:
            await state.clear()
            await msg.answer(f"Помилка: {e}", reply_markup=kb.main())
            logger.error(f"Помилка: {e}")
            
    except ValueError:
        await msg.answer("Введіть число:")


@router.message(F.text == "📊 Статистика парсингу")
async def parse_stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    if not storage.parsed_users:
        await msg.answer("База порожня")
        return
    
    total = len(storage.parsed_users)
    admins_count = len(storage.admin_users)
    bots_count = len(storage.bot_users)
    with_username = sum(1 for u in storage.parsed_users if u["username"])
    with_avatar = sum(1 for u in storage.parsed_users if u["has_avatar"])
    
    text = f"Статистика:\n\n"
    text += f"Юзерів: {total}\n"
    text += f"Адмінів: {admins_count}\n"
    text += f"Ботів: {bots_count}\n"
    text += f"З username: {with_username}\n"
    text += f"З аватаркою: {with_avatar}"
    
    await msg.answer(text)


@router.message(F.text == "🧹 Очистити базу")
async def clear_database(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    storage.clear_parsed_users()
    await msg.answer("База очищена", reply_markup=kb.main())