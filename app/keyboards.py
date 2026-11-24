from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

MENU_TEXTS = {"🛍 Katalog", "🔎 Qidiruv", "🤖 AI Maslahatchi", "🛒 Savat", "📊 Statistika",
              "⬅️ Asosiy menyu"}


def main_menu() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="🛍 Katalog"), KeyboardButton(text="🔎 Qidiruv")],
            [KeyboardButton(text="🤖 AI Maslahatchi"), KeyboardButton(text="🛒 Savat")]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📊 Statistika")], [KeyboardButton(text="⬅️ Asosiy menyu")]],
        resize_keyboard=True)


def phone_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
                  [KeyboardButton(text="⬅️ Asosiy menyu")]],
        resize_keyboard=True, one_time_keyboard=True)


def product_kb(pid: int, back_cb: str) -> InlineKeyboardMarkup:
    """Mahsulot tavsifi ostidagi tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Savatga", callback_data=f"add:{pid}"),
         InlineKeyboardButton(text="⚡ Hozir buyurtma berish", callback_data=f"buy:{pid}")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=back_cb)],
    ])
