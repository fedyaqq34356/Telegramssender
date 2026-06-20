from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS, INVITE_CONFIG, get_random_delay
from storage import storage
from states import PublicInviter
import keyboards as kb
import auth
from logger import logger
from export import create_export_files
import asyncio
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import InputPeerUser, InputPeerChannel
from telethon.errors.rpcerrorlist import (
    PeerFloodError, UserPrivacyRestrictedError,
    FloodWaitError, UserBotError, UserNotMutualContactError,
    UserChannelsTooMuchError
)

router = Router()


@router.message(F.text == "📬 Інвайтинг з пабліків")
async def public_invite_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if not storage.accounts:
        await msg.answer("Додайте акаунт спочатку")
        return
    if not storage.target_groups:
        await msg.answer("Додайте отримувач спочатку")
        return
    parsed = [p for p in storage.publics if p.get("users")]
    if not parsed:
        await msg.answer("Немає спарсених пабліків. Спочатку запустіть парсинг пабліків.")
        return

    text = "Виберіть пабліки для інвайтингу (номери через кому, наприклад: 1,2):\n\n"
    for i, p in enumerate(storage.publics, 1):
        name = p.get("description") or p["link"]
        user_count = len(p.get("users", []))
        text += f"{i}. {name} [{p.get('region','—')}] — {user_count} юзерів\n"

    await state.set_state(PublicInviter.select_publics)
    await msg.answer(text, reply_markup=kb.cancel())


@router.message(PublicInviter.select_publics)
async def public_invite_select_publics(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        indices = [int(x.strip()) - 1 for x in msg.text.split(",")]
        valid = [i for i in indices if 0 <= i < len(storage.publics) and storage.publics[i].get("users")]
        if not valid:
            await msg.answer("Невірні номери або пабліки без юзерів")
            return

        combined = storage.get_combined_users(valid)
        if not combined:
            await msg.answer("Немає юзерів у вибраних пабліках")
            return

        await state.update_data(public_indices=valid, users=combined)

        text = f"Вибрано {len(combined)} унікальних юзерів.\n\nВиберіть акаунт:\n\n"
        for i, (name, data) in enumerate(storage.accounts.items(), 1):
            today_invites = storage.get_today_invites(name)
            remaining = INVITE_CONFIG["max_invites_per_day"] - today_invites
            text += f"{i}. {name} ({data['phone']}) — залишилось: {remaining}\n"

        await state.set_state(PublicInviter.select_account)
        await msg.answer(text, reply_markup=kb.cancel())
    except ValueError:
        await msg.answer("Введіть номери через кому (наприклад: 1,2,3):")


@router.message(PublicInviter.select_account)
async def public_invite_select_account(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        idx = int(msg.text) - 1
        accounts_list = list(storage.accounts.keys())
        if not (0 <= idx < len(accounts_list)):
            await msg.answer("Невірний номер")
            return

        account_name = accounts_list[idx]
        today_invites = storage.get_today_invites(account_name)
        if today_invites >= INVITE_CONFIG["max_invites_per_day"]:
            await state.clear()
            await msg.answer(f"Досягнуто денний ліміт ({INVITE_CONFIG['max_invites_per_day']})", reply_markup=kb.publics_menu())
            return

        remaining = INVITE_CONFIG["max_invites_per_day"] - today_invites
        await state.update_data(account_name=account_name)

        text = f"Залишилось на сьогодні: {remaining}\n\nВиберіть отримувач:\n\n"
        for i, g in enumerate(storage.target_groups, 1):
            text += f"{i}. {g}\n"

        await state.set_state(PublicInviter.select_target)
        await msg.answer(text, reply_markup=kb.cancel())
    except ValueError:
        await msg.answer("Введіть номер:")


@router.message(PublicInviter.select_target)
async def public_invite_execute(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.publics_menu())
        return
    try:
        idx = int(msg.text) - 1
        if not (0 <= idx < len(storage.target_groups)):
            await msg.answer("Невірний номер")
            return

        target = storage.target_groups[idx]
        data = await state.get_data()
        account_name = data["account_name"]
        users = data["users"]
        account_data = storage.accounts[account_name]

        today_invites = storage.get_today_invites(account_name)
        session_limit = min(
            INVITE_CONFIG["max_invites_per_session"],
            INVITE_CONFIG["max_invites_per_day"] - today_invites
        )
        if session_limit <= 0:
            await state.clear()
            await msg.answer("Досягнуто денний ліміт", reply_markup=kb.publics_menu())
            return

        await msg.answer(f"Інвайтинг розпочато (ліміт: {session_limit}, юзерів: {len(users)})...")

        client = await auth.get_client(account_name, account_data["api_id"], account_data["api_hash"])

        try:
            if target.startswith('@'):
                target_entity = await client.get_entity(target)
            elif target.lstrip('-').isdigit():
                target_entity = await client.get_entity(int(target))
            else:
                target_entity = await client.get_entity(target)
            target_channel = InputPeerChannel(target_entity.id, target_entity.access_hash)
        except Exception as e:
            await state.clear()
            await msg.answer(f"Помилка отримання групи: {e}", reply_markup=kb.publics_menu())
            return

        success = 0
        failed = 0
        privacy_errors = 0
        session_count = 0
        skipped = 0
        invited_users = []
        storage.reset_old_stats()

        for user in users:
            if session_count >= session_limit:
                await msg.answer(f"Досягнуто ліміт сесії ({session_limit})")
                break
            if not await auth.check_client_connection(client):
                await msg.answer("⚠️ З'єднання втрачено — зупинка інвайтингу")
                break
            try:
                if not user.get('access_hash') or user['access_hash'] == 0:
                    skipped += 1
                    continue
                user_to_add = InputPeerUser(user['id'], user['access_hash'])
                await client(InviteToChannelRequest(target_channel, [user_to_add]))
                success += 1
                session_count += 1
                invited_users.append(user)
                storage.increment_invites(account_name)
                logger.info(f"Додано: {user.get('username', user['id'])}")
                if success % 2 == 0:
                    await msg.answer(f"Додано: {success}, Помилок: {failed}, Пропущено: {skipped}")
                await asyncio.sleep(get_random_delay(INVITE_CONFIG["delay_between_invites"]))
            except UserPrivacyRestrictedError:
                privacy_errors += 1
                failed += 1
                await asyncio.sleep(get_random_delay(INVITE_CONFIG["delay_after_privacy"]))
            except UserNotMutualContactError:
                failed += 1
                await asyncio.sleep(get_random_delay(INVITE_CONFIG["delay_after_privacy"]))
            except UserChannelsTooMuchError:
                failed += 1
                await asyncio.sleep(get_random_delay(INVITE_CONFIG["delay_after_privacy"]))
            except PeerFloodError:
                failed += 1
                await msg.answer("⚠️ PEER_FLOOD! Акаунт тимчасово заблокований (24-48 год)")
                break
            except FloodWaitError as e:
                wait_time = e.seconds
                if wait_time > 300:
                    await msg.answer(f"⚠️ FloodWait {wait_time//60} хв — зупинка!")
                    break
                await msg.answer(f"Очікування {wait_time} сек...")
                await asyncio.sleep(wait_time + 10)
            except UserBotError:
                failed += 1
            except Exception as e:
                failed += 1
                error_msg = str(e)
                logger.error(f"Помилка {user.get('username', user['id'])}: {error_msg}")
                if "PEER_FLOOD" in error_msg or "Cannot send requests while disconnected" in error_msg:
                    await msg.answer("⚠️ Критична помилка — зупинка!")
                    break
                await asyncio.sleep(get_random_delay(INVITE_CONFIG["delay_after_error"]))

        total_today = storage.get_today_invites(account_name)
        remaining_today = INVITE_CONFIG["max_invites_per_day"] - total_today
        text = (f"Інвайтинг завершено!\n\n"
                f"✅ Успішно: {success}\n"
                f"❌ Невдало: {failed}\n"
                f"🔒 Приватність: {privacy_errors}\n"
                f"⏭ Пропущено: {skipped}\n"
                f"📊 Всього сьогодні: {total_today}\n"
                f"📈 Залишилось: {remaining_today}")
        await state.clear()
        await msg.answer(text, reply_markup=kb.publics_menu())

        if invited_users:
            await msg.answer("Формую файли звіту...")
            xlsx, csv = create_export_files(invited_users, "public_invited")
            await msg.answer_document(FSInputFile(xlsx), caption=f"Запрошені з пабліків ({success}) — Excel")
            await msg.answer_document(FSInputFile(csv), caption=f"Запрошені з пабліків ({success}) — CSV")

        logger.info(f"Пабліки інвайтинг: {success} успішно, {failed} невдало, {skipped} пропущено")

    except ValueError:
        await msg.answer("Введіть номер:")