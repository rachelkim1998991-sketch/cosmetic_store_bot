"""Savat (mahsulotlarni belgilab tanlash) va buyurtma berish."""
import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.api_client import SITE_DOWN, api, money
from app.config import ADMIN_ID
from app.keyboards import MENU_TEXTS, main_menu, phone_menu
from app.states import Order
from app.store import cart_cache, carts, unchecked

router = Router()


# ---------- buyurtmani boshlash ----------

async def begin_order(message: Message, state: FSMContext, items: list[tuple[int, int]],
                      from_cart: bool, intro: str = "Ismingizni yozing:"):
    """items: [(product_id, miqdor), ...]. from_cart=True bo'lsa, buyurtmadan keyin shular savatdan olinadi."""
    await state.set_state(Order.name)
    await state.update_data(order_items=[list(i) for i in items], from_cart=from_cart)
    await message.answer(intro)


# ---------- savat ----------

async def cart_items(uid: int, refresh: bool = True):
    """Savatdagi mahsulotlar ro'yxati. Sayt javob bermasa None qaytaradi."""
    if not refresh and uid in cart_cache:
        cart = carts.get(uid, {})
        cached = [i for i in cart_cache[uid] if i["id"] in cart]
        if len(cached) == len(cart):
            return cached
    items = []
    for pid, qty in list(carts.get(uid, {}).items()):
        status, p = await api("GET", f"/products/{pid}/")
        if status == 404 or (status == 200 and p["stock"] < 1):
            carts[uid].pop(pid, None)       # mahsulot o'chirilgan yoki tugagan
            continue
        if status != 200:
            return None
        qty = min(qty, p["stock"])
        carts[uid][pid] = qty
        items.append({"id": pid, "name": p["name"], "qty": qty, "sub": p["final_price"] * qty})
    cart_cache[uid] = items
    return items


def cart_view(uid: int, items: list[dict]):
    off = unchecked.setdefault(uid, set())
    chosen = [i for i in items if i["id"] not in off]
    total = sum(i["sub"] for i in chosen)

    lines = [f"{'✅' if i['id'] not in off else '⬜'} {html.escape(i['name'])} × {i['qty']} = {money(i['sub'])}"
             for i in items]
    text = ("🛒 <b>Savat</b>\nBuyurtma qilmoqchi bo'lganlarni belgilang:\n\n" + "\n".join(lines) +
            f"\n\n<b>Tanlangan jami: {money(total)}</b>")

    rows = [[InlineKeyboardButton(
        text=f"{'✅' if i['id'] not in off else '⬜'} {i['name'][:28]} × {i['qty']}",
        callback_data=f"sel:{i['id']}")] for i in items]
    if len(chosen) == len(items):
        rows.append([InlineKeyboardButton(text="⬜ Tanlovni bekor qilish", callback_data="sel:none")])
    else:
        rows.append([InlineKeyboardButton(text="☑️ Hammasini tanlash", callback_data="sel:all")])
    rows.append([InlineKeyboardButton(text=f"✅ Buyurtma berish ({len(chosen)} ta)", callback_data="checkout")])
    rows.append([InlineKeyboardButton(text="🗑 Savatni tozalash", callback_data="clear")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "🛒 Savat")
async def show_cart(m: Message, state: FSMContext):
    await state.clear()
    items = await cart_items(m.from_user.id)
    if items is None:
        return await m.answer(SITE_DOWN)
    if not items:
        return await m.answer("Savat bo'sh.")
    text, kb = cart_view(m.from_user.id, items)
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("sel:"))
async def toggle_selection(cb: CallbackQuery):
    uid = cb.from_user.id
    key = cb.data.split(":")[1]
    off = unchecked.setdefault(uid, set())
    if key == "all":
        off.clear()
    elif key == "none":
        off.update(carts.get(uid, {}))
    else:
        off ^= {int(key)}

    items = await cart_items(uid, refresh=False)
    if items is None:
        return await cb.answer(SITE_DOWN, show_alert=True)
    if not items:
        await cb.message.answer("Savat bo'sh.")
        return await cb.answer()
    text, kb = cart_view(uid, items)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise
    await cb.answer()


@router.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    carts.pop(cb.from_user.id, None)
    unchecked.pop(cb.from_user.id, None)
    cart_cache.pop(cb.from_user.id, None)
    await cb.message.answer("Savat tozalandi.")
    await cb.answer()


@router.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    items = await cart_items(uid)
    if items is None:
        return await cb.answer(SITE_DOWN, show_alert=True)
    off = unchecked.get(uid, set())
    chosen = [(i["id"], i["qty"]) for i in items if i["id"] not in off]
    if not chosen:
        return await cb.answer("Avval kamida bitta mahsulotni belgilang", show_alert=True)
    await begin_order(cb.message, state, chosen, from_cart=True,
                      intro=f"Tanlangan {len(chosen)} ta mahsulot uchun buyurtma.\n\nIsmingizni yozing:")
    await cb.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_now(cb: CallbackQuery, state: FSMContext):
    """Mahsulot sahifasidagi «Hozir buyurtma berish»: savatga tegmasdan, faqat shu mahsulot."""
    pid = int(cb.data.split(":")[1])
    status, p = await api("GET", f"/products/{pid}/")
    if status != 200:
        await cb.message.answer("Bu mahsulot endi mavjud emas." if status else SITE_DOWN)
        return await cb.answer()
    await begin_order(cb.message, state, [(pid, 1)], from_cart=False,
                      intro=f"⚡ <b>{html.escape(p['name'])}</b> — {money(p['final_price'])}\n\n"
                            "Buyurtma uchun ismingizni yozing:")
    await cb.answer()


# ---------- ism va telefon ----------

@router.message(Order.name, F.text, ~F.text.in_(MENU_TEXTS))
async def got_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip()[:100])
    await state.set_state(Order.phone)
    await m.answer("Telefon raqamingizni yuboring (tugmani bosing yoki yozing, masalan: +998901234567):",
                   reply_markup=phone_menu())


@router.message(Order.name, ~F.text)
async def name_wrong(m: Message):
    await m.answer("Iltimos, ismingizni matn ko'rinishida yozing.")


@router.message(Order.phone, ~F.text.in_(MENU_TEXTS))
async def got_phone(m: Message, state: FSMContext, bot: Bot):
    phone = m.contact.phone_number if m.contact else (m.text or "").strip()
    if len(re.sub(r"\D", "", phone)) < 9:
        return await m.answer("Raqam noto'g'ri ko'rinyapti. Masalan: +998901234567")

    d = await state.get_data()
    await state.clear()
    uid = m.from_user.id
    items = [(int(pid), int(q)) for pid, q in d.get("order_items") or []]
    if not items:
        return await m.answer("Buyurtma uchun mahsulot topilmadi. Savatni qaytadan oching.",
                              reply_markup=main_menu())

    payload = {
        "telegram_user_id": str(uid),
        "telegram_username": m.from_user.username or "",
        "customer_name": d.get("name", ""),
        "customer_phone": phone,
        "payment_method": "cash",
        "items": [{"product_id": pid, "quantity": q} for pid, q in items],
    }
    status, res = await api("POST", "/orders/create/", json=payload)
    if status == 409:
        return await m.answer("Kechirasiz, ayrim mahsulotlar tugagan yoki yetarli emas. "
                              "Savatni tekshiring.", reply_markup=main_menu())
    if status != 201:
        return await m.answer("Xatolik yuz berdi, keyinroq urinib ko'ring.", reply_markup=main_menu())

    # faqat buyurtma qilinganlar savatdan olinadi, belgilanmaganlari qoladi
    left = 0
    if d.get("from_cart"):
        cart = carts.get(uid, {})
        for pid, _ in items:
            cart.pop(pid, None)
            unchecked.get(uid, set()).discard(pid)
        cart_cache.pop(uid, None)
        left = len(cart)

    done = (f"✅ Buyurtma #{res['id']} qabul qilindi!\nJami: {money(res['total_amount'])}\n"
            "Tez orada siz bilan bog'lanamiz.")
    if left:
        done += f"\n\n🛒 Savatda yana {left} ta mahsulot qoldi."
    await m.answer(done, reply_markup=main_menu())

    try:
        names = "\n".join(f"• {html.escape(i['name'])} × {i['quantity']}" for i in res["items"])
        await bot.send_message(
            ADMIN_ID,
            f"🆕 Buyurtma #{res['id']}\n{html.escape(d.get('name', ''))} | {html.escape(phone)} | "
            f"@{m.from_user.username or '-'}\n{names}\nJami: {money(res['total_amount'])}\n\n"
            "Saytdagi admin panelda 'To'landi' qilsangiz, ombor avtomatik kamayadi.")
    except Exception:
        logging.exception("Adminga xabar yuborib bo'lmadi")