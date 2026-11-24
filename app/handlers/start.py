from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import ADMIN_ID
from app.keyboards import admin_menu, main_menu

router = Router()


@router.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Cosmetic Store botiga xush kelibsiz! 💄", reply_markup=main_menu())


@router.message(Command("admin"))
async def admin_panel(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await m.answer("🔐 Admin panel", reply_markup=admin_menu())


@router.message(F.text == "⬅️ Asosiy menyu")
async def to_main_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Asosiy menyu 👇", reply_markup=main_menu())
