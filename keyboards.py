from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Додати акаунт")],
            [KeyboardButton(text="📋 Список акаунтів")],
            [KeyboardButton(text="🗑 Видалити акаунт")],
            [KeyboardButton(text="📺 Додати джерело")],
            [KeyboardButton(text="📤 Додати отримувач")],
            [KeyboardButton(text="📋 Всі групи")],
            [KeyboardButton(text="🗑 Видалити групу")],
            [KeyboardButton(text="🔍 Парсинг")],
            [KeyboardButton(text="📊 Статистика парсингу")],
            [KeyboardButton(text="📬 Запустити інвайтинг")],
            [KeyboardButton(text="📈 Статистика інвайтингу")],
            [KeyboardButton(text="📨 Рассылка")],
            [KeyboardButton(text="📊 Статистика розсилки")],
            [KeyboardButton(text="🧹 Очистити базу")],
            [KeyboardButton(text="🌐 Пабліки")],
        ],
        resize_keyboard=True
    )


def cancel():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати")]],
        resize_keyboard=True
    )


def group_type():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📺 Джерело")],
            [KeyboardButton(text="📤 Отримувач")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True
    )


def publics_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Додати паблік")],
            [KeyboardButton(text="📋 Список пабліків")],
            [KeyboardButton(text="🔍 Парсити паблік")],
            [KeyboardButton(text="📦 Експорт підписників")],
            [KeyboardButton(text="📬 Інвайтинг з пабліків")],
            [KeyboardButton(text="🗑 Видалити паблік")],
            [KeyboardButton(text="🔙 Головне меню")],
        ],
        resize_keyboard=True
    )


def resume_choice():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Продовжити")],
            [KeyboardButton(text="🔄 Почати заново")],
            [KeyboardButton(text="❌ Скасувати")]
        ],
        resize_keyboard=True
    )