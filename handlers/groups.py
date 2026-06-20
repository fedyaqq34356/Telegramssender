from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from config import ADMIN_IDS
from storage import storage
from states import Group
import keyboards as kb

router = Router()


@router.message(F.text == "📺 Додати джерело")
async def add_source_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(Group.source)
    await msg.answer("Введіть @username або ID групи:", reply_markup=kb.cancel())


@router.message(Group.source)
async def add_source_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    storage.add_source_group(msg.text)
    await state.clear()
    await msg.answer(f"Додано джерело: {msg.text}", reply_markup=kb.main())


@router.message(F.text == "📤 Додати отримувач")
async def add_target_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(Group.target)
    await msg.answer("Введіть @username або ID групи:", reply_markup=kb.cancel())


@router.message(Group.target)
async def add_target_input(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    storage.add_target_group(msg.text)
    await state.clear()
    await msg.answer(f"Додано отримувач: {msg.text}", reply_markup=kb.main())


@router.message(F.text == "📋 Всі групи")
async def list_groups(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    text = "Джерела:\n"
    if storage.source_groups:
        for i, g in enumerate(storage.source_groups, 1):
            text += f"{i}. {g}\n"
    else:
        text += "Немає\n"
    
    text += "\nОтримувачі:\n"
    if storage.target_groups:
        for i, g in enumerate(storage.target_groups, 1):
            text += f"{i}. {g}\n"
    else:
        text += "Немає\n"
    
    await msg.answer(text)


@router.message(F.text == "🗑 Видалити групу")
async def delete_group_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    if not storage.source_groups and not storage.target_groups:
        await msg.answer("Груп немає")
        return
    
    await state.set_state(Group.delete_type)
    await msg.answer("Виберіть тип:", reply_markup=kb.group_type())


@router.message(Group.delete_type)
async def delete_group_type(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    if msg.text == "📺 Джерело":
        if not storage.source_groups:
            await state.clear()
            await msg.answer("Немає джерел", reply_markup=kb.main())
            return
        
        text = "Джерела:\n\n"
        for i, g in enumerate(storage.source_groups, 1):
            text += f"{i}. {g}\n"
        
        await state.update_data(type="source")
        await state.set_state(Group.delete_choice)
        await msg.answer(text + "\nВведіть номер:", reply_markup=kb.cancel())
    
    elif msg.text == "📤 Отримувач":
        if not storage.target_groups:
            await state.clear()
            await msg.answer("Немає отримувачів", reply_markup=kb.main())
            return
        
        text = "Отримувачі:\n\n"
        for i, g in enumerate(storage.target_groups, 1):
            text += f"{i}. {g}\n"
        
        await state.update_data(type="target")
        await state.set_state(Group.delete_choice)
        await msg.answer(text + "\nВведіть номер:", reply_markup=kb.cancel())


@router.message(Group.delete_choice)
async def delete_group_confirm(msg: Message, state: FSMContext):
    if msg.text == "❌ Скасувати":
        await state.clear()
        await msg.answer("Скасовано", reply_markup=kb.main())
        return
    
    try:
        data = await state.get_data()
        idx = int(msg.text) - 1
        
        if data["type"] == "source":
            if 0 <= idx < len(storage.source_groups):
                group = storage.source_groups[idx]
                storage.remove_source_group(group)
                await state.clear()
                await msg.answer(f"Видалено: {group}", reply_markup=kb.main())
            else:
                await msg.answer("Невірний номер")
        else:
            if 0 <= idx < len(storage.target_groups):
                group = storage.target_groups[idx]
                storage.remove_target_group(group)
                await state.clear()
                await msg.answer(f"Видалено: {group}", reply_markup=kb.main())
            else:
                await msg.answer("Невірний номер")
    except ValueError:
        await msg.answer("Введіть номер:")