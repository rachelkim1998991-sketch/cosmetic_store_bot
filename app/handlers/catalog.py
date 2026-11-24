"""Katalog: kategoriyalar -> mahsulotlar -> mahsulot sahifasi."""
import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.api_client import SITE_DOWN, api, money, split_html
from app.cards import send_cards, send_compact_list
from app.keyboards import product_kb
from app.store import carts

router = Router()


async def send_categories(message: Message):
    status, data = await api("GET", "/categories/")
    if status != 200:
        return await message.answer(SITE_DOWN)
    rows = [[InlineKeyboardButton(text=c["name"], callback_data=f"cat:{c['id']}:1")]
            for c in data["results"]]
    rows.append([InlineKeyboardButton(text="Barchasi", callback_data="cat:0:1")])
    await message.answer("Kategoriyani tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(F.text == "🛍 Katalog")
async def catalog(m: Message, state: FSMContext):
    await state.clear()
    await send_categories(m)


@router.callback_query(F.data == "cats")
async def back_to_categories(cb: CallbackQuery):
    await send_categories(cb.message)
    await cb.answer()


LABEL = "🛍 Mahsulotlar"
FOOTER = [[InlineKeyboardButton(text="⬅️ Kategoriyalar", callback_data="cats")]]


async def show_category(message: Message, cat: str, page: int, compact: bool):
    params = {"page": page}
    if cat != "0":
        params["category"] = cat
    status, data = await api("GET", "/products/", params=params)
    if status != 200:
        return await message.answer(SITE_DOWN)
    results = data["results"]
    if not results:
        return await message.answer("Hozircha mahsulot yo'q.", reply_markup=InlineKeyboardMarkup(inline_keyboard=FOOTER))
    common = dict(src=cat, page=page, has_next=bool(data.get("has_next")),
                  total=data.get("total", len(results)), label=LABEL,
                  page_cb=lambda n: f"cat:{cat}:{n}", footer=FOOTER)
    if compact:
        await send_compact_list(message, results, **common)
    else:
        await send_cards(message, results, plain_footer_text="Boshqa kategoriyani tanlaysizmi?", **common)


@router.callback_query(F.data.startswith("cat:"))
async def show_products(cb: CallbackQuery):
    """Kategoriya (yoki «Barchasi») mahsulotlari: rasmli kartochkalar."""
    _, cat, page = cb.data.split(":")
    await cb.answer()          # kartochkalar yuborilguncha tugma "aylanib" turmasin
    await show_category(cb.message, cat, max(1, int(page)), compact=False)


@router.callback_query(F.data.startswith("cb:"))
async def back_to_list(cb: CallbackQuery):
    """Mahsulot sahifasidan «Orqaga»: shu sahifaning ixcham ro'yxati (kartochkalar qayta yuborilmaydi)."""
    _, cat, page = cb.data.split(":")
    await cb.answer()
    await show_category(cb.message, cat, max(1, int(page)), compact=True)


@router.callback_query(F.data.startswith("p:"))
async def product(cb: CallbackQuery):
    # p:<id>:<kategoriya yoki 's' (qidiruv)>:<sahifa>; eski "p:<id>" ham ishlaydi
    parts = cb.data.split(":")
    pid = int(parts[1])
    src = parts[2] if len(parts) > 2 else "0"
    page = parts[3] if len(parts) > 3 else "1"
    if src == "s":
        back_cb = f"sback:{page}"
    elif src == "ai":
        back_cb = "aib"
    else:
        back_cb = f"cb:{src}:{page}"

    status, p = await api("GET", f"/products/{pid}/")
    if status != 200:
        await cb.message.answer("Bu mahsulot endi mavjud emas.")
        return await cb.answer()

    price = money(p["final_price"])
    if p["is_on_discount"]:
        price = f"<s>{money(p['price'])}</s> {price}"
    head = (f"<b>{html.escape(p['name'])}</b>\n{html.escape(p['brand'])} — {html.escape(p['category'])}"
            f"\n\n{price}\nOmborda: {p['stock']} dona")
    chunks = split_html(p["description"] or "") or ["Tavsif qo'shilmagan."]
    kb = product_kb(pid, back_cb)

    sent_photo = False
    if p["image"]:
        try:
            await cb.message.answer_photo(p["image"], caption=head)
            sent_photo = True
        except Exception:
            pass
    if not sent_photo:
        chunks[0] = f"{head}\n\n{chunks[0]}"
    # tugmalar OXIRGI xabarda: mijoz tavsifni oxirigacha o'qib bo'lgach ko'radi
    for i, text in enumerate(chunks):
        await cb.message.answer(text, reply_markup=kb if i == len(chunks) - 1 else None)
    await cb.answer()


@router.callback_query(F.data.startswith("add:"))
async def add(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    cart = carts.setdefault(cb.from_user.id, {})
    cart[pid] = cart.get(pid, 0) + 1
    await cb.answer("Savatga qo'shildi ✓")