from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from storage import storage
from states import PublicGroup
import keyboards as kb
import auth
from logger import logger
from export import create_export_files
from telethon.tl.types import ChannelParticipantsAdmins
import re

try:
    from telethon.tl.functions.channels import GetFullChannel
    _HAS_GET_FULL_CHANNEL = True
except ImportError:
    _HAS_GET_FULL_CHANNEL = False

try:
    from telethon.tl.functions.messages import GetMessageReactionsList
    _HAS_REACTIONS_LIST = True
except ImportError:
    _HAS_REACTIONS_LIST = False

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


def _collect_user(user, unique_users, admin_ids):
    if not user or getattr(user, 'deleted', False) or getattr(user, 'bot', False):
        return
    if not getattr(user, 'access_hash', None):
        return
    if user.id not in unique_users:
        unique_users[user.id] = {
            "id": user.id,
            "access_hash": user.access_hash,
            "username": getattr(user, 'username', '') or "",
            "first_name": getattr(user, 'first_name', '') or "",
            "last_name": getattr(user, 'last_name', '') or "",
            "has_avatar": user.photo is not None
        }


async def _parse_reactions(client, peer, msg_id, unique_users, admin_ids):
    """Парсить реакції до повідомлення. Повертає кількість нових юзерів."""
    if not _HAS_REACTIONS_LIST:
        return 0
    found = 0
    try:
        next_offset = None
        while True:
            kwargs = dict(peer=peer, id=msg_id, limit=100)
            if next_offset:
                kwargs["offset"] = next_offset
            result = await client(GetMessageReactionsList(**kwargs))
            for u in result.users:
                before = len(unique_users)
                _collect_user(u, unique_users, admin_ids)
                if len(unique_users) > before:
                    found += 1
            next_offset = result.next_offset
            if not next_offset or len(result.users) < 100:
                break
    except Exception as e:
        logger.debug(f"Помилка парсингу реакцій (peer={peer}, id={msg_id}): {e}")
    return found


@router.message(F.text == "🌐 Пабліки")
async def publics_menu(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("Розділ пабліків:", reply_markup=kb.publics_menu())


@router.message(F.text == "🔙 Головне меню")
async def back_to_main(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await msg.answer("Головне меню:", reply_markup=kb.main())


@router.message(F.text == "➕ Додати паблік")
async def add_public_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(PublicGroup.add_link)
    await msg.answer("Введіть посилання або @username пабліку:", reply_markup=kb.cancel())


@router.message(PublicGroup.add_link)
async def add_public_link(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    await state.update_data(link=msg.text)
    await state.set_state(PublicGroup.add_region)
    await msg.answer("Введіть регіон (наприклад: UA, RU, EU):")


@router.message(PublicGroup.add_region)
async def add_public_region(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    data = await state.get_data()
    link = data["link"]
    region = msg.text.strip().upper()

    description = ""
    if storage.accounts:
        try:
            account_name, account_data = next(iter(storage.accounts.items()))
            client = await auth.get_client(account_name, account_data["api_id"], account_data["api_hash"])
            identifier = extract_username_from_link(link)
            try:
                entity = await client.get_entity(identifier)
                description = getattr(entity, 'title', '') or getattr(entity, 'first_name', '') or ""
            except Exception:
                pass
        except Exception:
            pass

    storage.add_public(link, region, description)
    await state.clear()
    await msg.answer(f"Паблік додано!\nПосилання: {link}\nРегіон: {region}\nНазва: {description or '—'}", reply_markup=kb.publics_menu())


@router.message(F.text == "📋 Список пабліків")
async def list_publics(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.publics:
        await msg.answer("Пабліків немає")
        return
    text = "Пабліки:\n\n"
    for i, p in enumerate(storage.publics, 1):
        name = p.get("description") or p["link"]
        region = p.get("region", "—")
        user_count = len(p.get("users", []))
        text += f"{i}. {name}\n   🔗 {p['link']}\n   🌍 {region} | 👥 {user_count} юзерів\n\n"
    await msg.answer(text)


@router.message(F.text == "🔍 Парсити паблік")
async def parse_public_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.publics:
        await msg.answer("Додайте паблік спочатку")
        return
    if not storage.accounts:
        await msg.answer("Додайте акаунт спочатку")
        return
    text = "Виберіть акаунт:\n\n"
    for i, (name, data) in enumerate(storage.accounts.items(), 1):
        text += f"{i}. {name} ({data['phone']})\n"
    await state.set_state(PublicGroup.parse_account)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(PublicGroup.parse_account)
async def parse_public_account(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        idx = int(msg.text) - 1
        accounts_list = list(storage.accounts.keys())
        if 0 <= idx < len(accounts_list):
            await state.update_data(account_name=accounts_list[idx])
            text = "Виберіть паблік:\n\n"
            for i, p in enumerate(storage.publics, 1):
                name = p.get("description") or p["link"]
                text += f"{i}. {name} [{p.get('region','—')}]\n"
            await state.set_state(PublicGroup.parse_select)
            await msg.answer(text, reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(PublicGroup.parse_select)
async def parse_public_select(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        idx = int(msg.text) - 1
        if 0 <= idx < len(storage.publics):
            public = storage.publics[idx]
            await state.update_data(public_idx=idx, public_link=public["link"])
            progress = storage.get_parse_progress(public["link"])
            if progress:
                await state.set_state(PublicGroup.parse_resume)
                text = (f"Знайдено збережений прогрес:\n"
                        f"Перевірено: {progress['messages_checked']}\n"
                        f"Знайдено: {progress['found_count']}\n\n"
                        f"Продовжити або почати заново?")
                await msg.answer(text, reply_markup=kb.resume_choice())
            else:
                await state.set_state(PublicGroup.parse_limit)
                await msg.answer("Скільки постів проаналізувати? (10-1000):", reply_markup=kb.cancel())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(PublicGroup.parse_resume)
async def parse_public_resume(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    if msg.text == "🔄 Почати заново":
        data = await state.get_data()
        storage.clear_parse_progress(data["public_link"])
        await state.update_data(resume=False)
        await state.set_state(PublicGroup.parse_limit)
        await msg.answer("Скільки постів проаналізувати? (10-1000):", reply_markup=kb.cancel())
    elif msg.text == "▶️ Продовжити":
        await state.update_data(resume=True)
        await state.set_state(PublicGroup.parse_limit)
        await msg.answer("Скільки постів проаналізувати? (10-1000):", reply_markup=kb.cancel())
    else:
        await msg.answer("Виберіть варіант")


@router.message(PublicGroup.parse_limit)
async def parse_public_execute(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        limit = int(msg.text)
        if not (10 <= limit <= 1000):
            await msg.answer("Введіть число від 10 до 1000:")
            return

        data = await state.get_data()
        account_name = data["account_name"]
        public_idx = data["public_idx"]
        public_link = data["public_link"]
        resume = data.get("resume", False)
        account_data = storage.accounts[account_name]

        reactions_status = "увімкнено" if _HAS_REACTIONS_LIST else "вимкнено (стара версія telethon)"
        await msg.answer(f"Парсинг {limit} постів... (реакції: {reactions_status})")

        client = await auth.get_client(account_name, account_data["api_id"], account_data["api_hash"])

        try:
            group_identifier = extract_username_from_link(public_link)
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
                    raise ValueError(f"Паблік '{public_link}' не знайдено")

            admin_ids = set()
            try:
                admins_list = []
                async for admin in client.iter_participants(group_entity, filter=ChannelParticipantsAdmins()):
                    admins_list.append(admin)
                admin_ids = {a.id for a in admins_list}
                logger.info(f"[ADMINS] Знайдено {len(admin_ids)} адмінів")
            except Exception as e:
                logger.warning(f"[ADMINS] Не вдалося отримати адмінів: {e}")

            linked_chat_id = None
            if _HAS_GET_FULL_CHANNEL:
                try:
                    logger.info(f"[LINKED] Запит GetFullChannel для {public_link}")
                    full_channel = await client(GetFullChannel(group_entity))
                    linked_chat_id = full_channel.full_chat.linked_chat_id
                    if linked_chat_id:
                        logger.info(f"[LINKED] Знайдено linked_chat_id: {linked_chat_id}")
                        await msg.answer(f"Знайдено групу коментарів (ID: {linked_chat_id})")
                    else:
                        logger.info(f"[LINKED] linked_chat_id = None, коментарі вимкнені")
                        await msg.answer("Коментарі вимкнені — парсинг тільки реакцій")
                except Exception as e:
                    logger.warning(f"[LINKED] GetFullChannel помилка: {e}")
                    await msg.answer("Не вдалося отримати інфо про канал — продовжую без коментарів")
            else:
                logger.warning("[LINKED] GetFullChannel недоступний — коментарі пропускаємо")
                await msg.answer("⚠️ Стара версія telethon — парсинг коментарів вимкнено")

            progress = storage.get_parse_progress(public_link) if resume else None
            offset_id = progress["offset_id"] if progress else 0
            posts_checked = progress["messages_checked"] if progress else 0

            unique_users = {}
            last_post_id = offset_id

            logger.info(f"[PARSE] Початок парсингу. linked_chat_id={linked_chat_id}, limit={limit}, offset_id={offset_id}")

            async for post in client.iter_messages(group_entity, limit=limit, offset_id=offset_id):
                posts_checked += 1
                last_post_id = post.id
                has_replies = post.replies and post.replies.replies > 0
                has_reactions = bool(post.reactions)
                logger.info(f"[POST {post.id}] replies={post.replies.replies if has_replies else 0}, reactions={has_reactions}")

                if posts_checked % 50 == 0:
                    storage.save_parse_progress(public_link, last_post_id, posts_checked, len(unique_users))
                    await msg.answer(f"Постів: {posts_checked}, юзерів: {len(unique_users)}")

                if linked_chat_id and has_replies:
                    logger.info(f"[POST {post.id}] Парсинг коментарів через linked_chat_id={linked_chat_id}")
                    comments_found = 0
                    try:
                        async for comment in client.iter_messages(
                            linked_chat_id,
                            reply_to=post.id,
                            limit=500
                        ):
                            if not comment.sender:
                                continue
                            sender = comment.sender
                            if getattr(sender, 'bot', False) or getattr(sender, 'deleted', False):
                                continue
                            before = len(unique_users)
                            _collect_user(sender, unique_users, admin_ids)
                            if len(unique_users) > before:
                                comments_found += 1

                            if comment.reactions:
                                reactions_found = await _parse_reactions(
                                    client, linked_chat_id, comment.id, unique_users, admin_ids
                                )
                                if reactions_found:
                                    logger.info(f"[POST {post.id}] Реакції коментаря {comment.id}: +{reactions_found} юзерів")
                        logger.info(f"[POST {post.id}] Коментарі: +{comments_found} нових юзерів")
                    except Exception as e:
                        logger.warning(f"[POST {post.id}] Помилка парсингу коментарів: {e}")
                elif linked_chat_id and not has_replies:
                    logger.info(f"[POST {post.id}] Коментарів немає (replies=0)")
                elif not linked_chat_id:
                    logger.info(f"[POST {post.id}] linked_chat_id відсутній, коментарі пропускаємо")

                if has_reactions:
                    logger.info(f"[POST {post.id}] Парсинг реакцій поста")
                    post_reactions_found = await _parse_reactions(
                        client, group_entity, post.id, unique_users, admin_ids
                    )
                    logger.info(f"[POST {post.id}] Реакції поста: +{post_reactions_found} нових юзерів")

            real_users = list(unique_users.values())

            storage.update_public_users(public_link, real_users, [], [])
            storage.clear_parse_progress(public_link)

            await msg.answer(
                f"Парсинг завершено!\n\n"
                f"Постів перевірено: {posts_checked}\n"
                f"Унікальних юзерів: {len(real_users)}"
            )

            if real_users:
                name_prefix = f"public_{public_idx + 1}_users"
                xlsx, csv = create_export_files(real_users, name_prefix)
                await msg.answer_document(FSInputFile(xlsx), caption=f"Юзери пабліку ({len(real_users)}) — Excel")
                await msg.answer_document(FSInputFile(csv), caption=f"Юзери пабліку ({len(real_users)}) — CSV")

            await state.clear()
            await msg.answer("Готово", reply_markup=kb.publics_menu())

        except Exception as e:
            await state.clear()
            await msg.answer(f"Помилка парсингу: {e}", reply_markup=kb.publics_menu())
            logger.error(f"Помилка парсингу пабліку: {e}")

    except ValueError:
        await msg.answer("Введіть число:")


@router.message(F.text == "📦 Експорт підписників")
async def export_combined_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    parsed = [p for p in storage.publics if p.get("users")]
    if not parsed:
        await msg.answer("Немає спарсених пабліків")
        return
    text = "Виберіть пабліки для об'єднання (введіть номери через кому, наприклад: 1,3,5):\n\n"
    for i, p in enumerate(storage.publics, 1):
        name = p.get("description") or p["link"]
        user_count = len(p.get("users", []))
        text += f"{i}. {name} [{p.get('region','—')}] — {user_count} юзерів\n"
    await state.set_state(PublicGroup.select_for_export)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(PublicGroup.select_for_export)
async def export_combined_execute(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        indices = [int(x.strip()) - 1 for x in msg.text.split(",")]
        valid = [i for i in indices if 0 <= i < len(storage.publics)]
        if not valid:
            await msg.answer("Невірні номери")
            return
        combined = storage.get_combined_users(valid)
        if not combined:
            await msg.answer("Немає юзерів у вибраних пабліках")
            return
        await msg.answer(f"Об'єднано {len(combined)} унікальних юзерів. Формую файли...")
        xlsx, csv = create_export_files(combined, "combined_publics")
        await msg.answer_document(FSInputFile(xlsx), caption=f"Об'єднані підписники ({len(combined)}) — Excel")
        await msg.answer_document(FSInputFile(csv), caption=f"Об'єднані підписники ({len(combined)}) — CSV")
        await state.clear()
        await msg.answer("Готово", reply_markup=kb.publics_menu())
    except ValueError:
        await msg.answer("Введіть номери через кому (наприклад: 1,2,3):")


@router.message(F.text == "🗑 Видалити паблік")
async def delete_public_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.publics:
        await msg.answer("Пабліків немає")
        return
    text = "Виберіть паблік для видалення:\n\n"
    for i, p in enumerate(storage.publics, 1):
        name = p.get("description") or p["link"]
        text += f"{i}. {name} [{p.get('region','—')}]\n"
    await state.set_state(PublicGroup.delete_choice)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(PublicGroup.delete_choice)
async def delete_public_confirm(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        idx = int(msg.text) - 1
        if 0 <= idx < len(storage.publics):
            link = storage.publics[idx]["link"]
            storage.remove_public(idx)
            await state.clear()
            await msg.answer(f"Видалено: {link}", reply_markup=kb.publics_menu())
        else:
            await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")
