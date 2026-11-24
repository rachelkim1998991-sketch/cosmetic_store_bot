from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.api_client import SITE_DOWN, api
from app.cards import send_cards, send_compact_list
from app.keyboards import MENU_TEXTS, main_menu
from app.states import Search
from app.store import last_search

router = Router()

PROMPT = "Mahsulot nomi yoki brendini yozing:"
LABEL = "🔎 Natijalar"


def nav_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="🔎 Yangi qidiruv", callback_data="snew"),
            InlineKeyboardButton(text="⬅️ Asosiy menyu", callback_data="smenu")]


def prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="smenu")]])


async def run_search(message: Message, uid: int, query: str, page: int = 1, compact: bool = False):
    status, data = await api("GET", "/products/", params={"q": query, "tg": uid, "page": page})
    if status != 200:
        return await message.answer(SITE_DOWN)
    results = data["results"]
    if not results:
        return await message.answer("Hech narsa topilmadi. 😔",
                                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav_row()]))
    common = dict(src="s", page=page, has_next=bool(data.get("has_next")),
                  total=data.get("total", len(results)), label=LABEL,
                  page_cb=lambda n: f"sp:{n}", footer=[nav_row()])
    if compact:
        await send_compact_list(message, results, **common)
    else:
        await send_cards(message, results, plain_footer_text="Boshqa mahsulot qidirasizmi?", **common)


@router.message(F.text == "🔎 Qidiruv")
async def search_start(m: Message, state: FSMContext):
    await state.set_state(Search.query)
    await m.answer(PROMPT, reply_markup=prompt_kb())


@router.message(Search.query, F.text, ~F.text.in_(MENU_TEXTS))
async def search_got(m: Message, state: FSMContext):
    await state.clear()
    query = m.text.strip()[:100]
    last_search[m.from_user.id] = query
    await run_search(m, m.from_user.id, query)


@router.callback_query(F.data == "snew")
async def search_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Search.query)
    await cb.message.answer(PROMPT, reply_markup=prompt_kb())
    await cb.answer()


@router.callback_query(F.data == "smenu")
async def search_to_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Asosiy menyu 👇", reply_markup=main_menu())
    await cb.answer()


@router.callback_query(F.data.startswith("sp:"))
async def search_page(cb: CallbackQuery):
    """Oldingi / Keyingi sahifa."""
    await cb.answer()
    query = last_search.get(cb.from_user.id)
    if not query:
        return await cb.message.answer("Qidiruvni qaytadan boshlang: «🔎 Qidiruv» tugmasini bosing.")
    await run_search(cb.message, cb.from_user.id, query, page=max(1, int(cb.data.split(":")[1])))


@router.callback_query(F.data.startswith("sback"))
async def search_back(cb: CallbackQuery):
    """Mahsulot sahifasidan qaytish: o'sha sahifaning ixcham ro'yxati."""
    await cb.answer()
    query = last_search.get(cb.from_user.id)
    parts = cb.data.split(":")
    page = max(1, int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else 1
    if not query:
        return await cb.message.answer("Qidiruvni qaytadan boshlang: «🔎 Qidiruv» tugmasini bosing.")
    await run_search(cb.message, cb.from_user.id, query, page=page, compact=True)