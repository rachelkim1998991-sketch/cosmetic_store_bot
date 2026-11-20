"""Cosmetic Store Telegram boti (aiogram 3, webhook, Render).

Ma'lumotlar bazasiga TO'G'RIDAN-TO'G'RI ulanmaydi: hammasi saytning API si orqali.
Env: BOT_TOKEN, ADMIN_ID, SITE_URL, BOT_API_TOKEN, WEBHOOK_URL (Render URL), PORT
"""
import logging
import os

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
SITE_URL = os.environ["SITE_URL"].rstrip("/")
API_TOKEN = os.environ["BOT_API_TOKEN"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"

router = Router()
carts: dict[int, dict[int, int]] = {}  # user_id -> {product_id: qty}  (Render qayta ishga tushsa tozalanadi)


MENU_TEXTS = {"🛍 Katalog", "🔎 Qidiruv", "🤖 AI Maslahatchi", "🛒 Savat", "📊 Statistika",
              "⬅️ Asosiy menyu"}


class Search(StatesGroup):
    query = State()


class AI(StatesGroup):
    chat = State()
    photo = State()
    custom = State()


class Order(StatesGroup):
    name = State()
    phone = State()


def money(v) -> str:
    return f"{int(v):,}".replace(",", ".") + " so'm"


async def api(method: str, path: str, timeout: int = 30, **kw):
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.request(method, f"{SITE_URL}/api{path}",
                            headers={"X-Bot-Token": API_TOKEN}, **kw)
        return r.status_code, r.json()


def main_menu(uid: int = 0):
    rows = [[KeyboardButton(text="🛍 Katalog"), KeyboardButton(text="🔎 Qidiruv")],
            [KeyboardButton(text="🤖 AI Maslahatchi"), KeyboardButton(text="🛒 Savat")]]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def fmt_ai(text: str) -> str:
    import html, re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


@router.message(CommandStart())
async def start(m: Message):
    await m.answer("Cosmetic Store botiga xush kelibsiz! 💄", reply_markup=main_menu(m.from_user.id))


@router.message(Command("admin"))
async def admin_panel(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return  # oddiy foydalanuvchiga hech narsa ko'rsatilmaydi
    await state.clear()
    await m.answer("🔐 Admin panel", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📊 Statistika")], [KeyboardButton(text="⬅️ Asosiy menyu")]],
        resize_keyboard=True))


@router.message(F.text == "⬅️ Asosiy menyu")
async def to_main_menu(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Asosiy menyu 👇", reply_markup=main_menu(m.from_user.id))


@router.message(F.text == "🛍 Katalog")
async def catalog(m: Message):
    _, data = await api("GET", "/categories/")
    rows = [[InlineKeyboardButton(text=c["name"], callback_data=f"cat:{c['id']}:1")]
            for c in data["results"]]
    rows.append([InlineKeyboardButton(text="Barchasi", callback_data="cat:0:1")])
    await m.answer("Kategoriyani tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("cat:"))
async def show_products(cb: CallbackQuery):
    _, cat, page = cb.data.split(":")
    params = {"page": page}
    if cat != "0":
        params["category"] = cat
    _, data = await api("GET", "/products/", params=params)
    if not data["results"]:
        await cb.message.answer("Hozircha mahsulot yo'q.")
        return await cb.answer()
    rows = [[InlineKeyboardButton(text=f"{p['name']} — {money(p['final_price'])}",
                                  callback_data=f"p:{p['id']}")] for p in data["results"]]
    nav = []
    if int(page) > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cat:{cat}:{int(page)-1}"))
    if data["has_next"]:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cat:{cat}:{int(page)+1}"))
    if nav:
        rows.append(nav)
    await cb.message.answer("Mahsulotlar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@router.callback_query(F.data.startswith("p:"))
async def product(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    status, p = await api("GET", f"/products/{pid}/")
    if status != 200:
        await cb.message.answer("Bu mahsulot endi mavjud emas.")
        return await cb.answer()
    price = money(p["final_price"])
    if p["is_on_discount"]:
        price = f"<s>{money(p['price'])}</s> {price}"
    import html
    head = (f"<b>{html.escape(p['name'])}</b>\n{html.escape(p['brand'])} — {html.escape(p['category'])}"
            f"\n\n{price}\nOmborda: {p['stock']} dona")
    desc = html.escape(p["description"] or "")[:3500]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Savatga", callback_data=f"add:{pid}")]])
    sent_photo = False
    if p["image"]:
        try:
            await cb.message.answer_photo(p["image"], caption=head)
            sent_photo = True
        except Exception:
            pass
    if sent_photo:
        await cb.message.answer(desc or "Tavsif qo'shilmagan.", reply_markup=kb)
    else:
        await cb.message.answer(head + (f"\n\n{desc}" if desc else ""), reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("add:"))
async def add(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    cart = carts.setdefault(cb.from_user.id, {})
    cart[pid] = cart.get(pid, 0) + 1
    await cb.answer("Savatga qo'shildi ✓")


async def cart_lines(uid: int):
    lines, total, ok = [], 0, True
    for pid, qty in carts.get(uid, {}).items():
        status, p = await api("GET", f"/products/{pid}/")
        if status != 200:
            ok = False
            continue
        qty = min(qty, p["stock"])
        carts[uid][pid] = qty
        sub = p["final_price"] * qty
        total += sub
        lines.append(f"• {p['name']} × {qty} = {money(sub)}")
    return lines, total


@router.message(F.text == "🛒 Savat")
async def show_cart(m: Message):
    lines, total = await cart_lines(m.from_user.id)
    if not lines:
        return await m.answer("Savat bo'sh.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtma berish", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]])
    await m.answer("\n".join(lines) + f"\n\n<b>Jami: {money(total)}</b>", reply_markup=kb)


@router.callback_query(F.data == "clear")
async def clear(cb: CallbackQuery):
    carts.pop(cb.from_user.id, None)
    await cb.message.answer("Savat tozalandi.")
    await cb.answer()


@router.callback_query(F.data == "checkout")
async def checkout(cb: CallbackQuery, state: FSMContext):
    if not carts.get(cb.from_user.id):
        return await cb.answer("Savat bo'sh", show_alert=True)
    await state.set_state(Order.name)
    await cb.message.answer("Ismingizni yozing:")
    await cb.answer()


@router.message(Order.name)
async def got_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await state.set_state(Order.phone)
    await m.answer("Telefon raqamingizni yuboring:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True))


@router.message(Order.phone)
async def got_phone(m: Message, state: FSMContext, bot: Bot):
    phone = m.contact.phone_number if m.contact else (m.text or "")
    d = await state.get_data()
    await state.clear()
    payload = {
        "telegram_user_id": str(m.from_user.id),
        "telegram_username": m.from_user.username or "",
        "customer_name": d["name"],
        "customer_phone": phone,
        "payment_method": "cash",
        "items": [{"product_id": pid, "quantity": q} for pid, q in carts.get(m.from_user.id, {}).items()],
    }
    status, res = await api("POST", "/orders/create/", json=payload)
    if status == 409:
        await m.answer("Kechirasiz, ayrim mahsulotlar tugagan yoki yetarli emas. Savatni tekshiring.",
                       reply_markup=main_menu(m.from_user.id))
        return
    if status != 201:
        await m.answer("Xatolik yuz berdi, keyinroq urinib ko'ring.", reply_markup=main_menu(m.from_user.id))
        return
    carts.pop(m.from_user.id, None)
    await m.answer(f"✅ Buyurtma #{res['id']} qabul qilindi!\nJami: {money(res['total_amount'])}\n"
                   "Tez orada siz bilan bog'lanamiz.", reply_markup=main_menu(m.from_user.id))
    items = "\n".join(f"• {i['name']} × {i['quantity']}" for i in res["items"])
    await bot.send_message(ADMIN_ID, f"🆕 Buyurtma #{res['id']}\n{d['name']} | {phone} | "
                           f"@{m.from_user.username or '-'}\n{items}\nJami: {money(res['total_amount'])}\n\n"
                           f"Saytdagi admin panelda 'To'landi' qilsangiz, ombor avtomatik kamayadi.")


@router.message(F.text == "🔎 Qidiruv")
async def search_start(m: Message, state: FSMContext):
    await state.set_state(Search.query)
    await m.answer("Mahsulot nomi yoki brendini yozing:")


@router.message(Search.query, ~F.text.in_(MENU_TEXTS))
async def search_run(m: Message, state: FSMContext):
    await state.clear()
    _, data = await api("GET", "/products/", params={"q": m.text, "tg": m.from_user.id})
    if not data["results"]:
        return await m.answer("Hech narsa topilmadi. 😔")
    rows = [[InlineKeyboardButton(text=f"{p['name']} — {money(p['final_price'])}",
                                  callback_data=f"p:{p['id']}")] for p in data["results"]]
    await m.answer("🔎 Natijalar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ---------- AI maslahatchi: anketa -> tavsiya -> buyurtma ----------
CONCERNS = {"acne": "Akne / husnbuzar", "postacne": "Postakne dog'lari", "pigment": "Pigmentatsiya",
            "wrinkle": "Ajinlar", "redness": "Qizarish / sezgirlik", "dry": "Quruqlik",
            "oily": "Yog'lilik / kengaygan poralar"}
SKIN = {"dry": "Quruq", "oily": "Yog'li", "comb": "Aralash", "normal": "Normal",
        "sens": "Sezgir", "unk": "Bilmayman"}
AGE = {"a1": "18 yoshgacha", "a2": "18-25", "a3": "26-35", "a4": "36-45", "a5": "45 dan katta"}
WANT = {"kit": "🧴 To'liq nabor", "cleanser": "Tozalovchi (ko'pik/gel)", "toner": "Toner",
        "serum": "Serum", "cream": "Krem", "spf": "SPF (quyoshdan himoya)"}

BACK_MENU = InlineKeyboardButton(text="⬅️ Orqaga", callback_data="ai:back")


async def render(target, text: str, kb: InlineKeyboardMarkup):
    """Xabarni tahrirlaydi (callback) yoki yangi xabar yuboradi."""
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await target.message.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


def options_kb(prefix: str, options: dict, back_step: int, per_row: int = 2) -> InlineKeyboardMarkup:
    btns = [InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}") for k, v in options.items()]
    rows = [btns[i:i + per_row] for i in range(0, len(btns), per_row)]
    rows.append([InlineKeyboardButton(text="✍️ Boshqa (o'zim yozaman)", callback_data=f"ai:c:{back_step + 1}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"ai:s:{back_step}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def concerns_kb(sel: set) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=("✅ " if k in sel else "▫️ ") + v, callback_data=f"aic:{k}")]
            for k, v in CONCERNS.items()]
    rows.append([InlineKeyboardButton(text="➡️ Davom etish", callback_data="aic:next")])
    rows.append([InlineKeyboardButton(text="✍️ Boshqa (o'zim yozaman)", callback_data="ai:c:1")])
    rows.append([InlineKeyboardButton(text="📷 Yuz rasmini yuborish", callback_data="ai:photo")])
    rows.append([BACK_MENU])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def get_prof(state: FSMContext) -> dict:
    d = await state.get_data()
    return d.get("prof") or {"concerns": []}


async def show_step(target, state: FSMContext, step: int):
    await state.set_state(None)  # yozma kiritish rejimidan chiqamiz (ma'lumotlar saqlanadi)
    prof = await get_prof(state)
    if step == 1:
        await render(target, "1/4. Yuzingizdagi muammolarni belgilang (bir nechtasini tanlash mumkin), "
                             "so'ng «Davom etish» ni bosing:", concerns_kb(set(prof.get("concerns", []))))
    elif step == 2:
        await render(target, "2/4. Teringiz turi qanday?", options_kb("ais", SKIN, 1))
    elif step == 3:
        await render(target, "3/4. Yoshingiz?", options_kb("aia", AGE, 2, per_row=2))
    elif step == 4:
        await render(target, "4/4. Sizga nima kerak?", options_kb("aiw", WANT, 3))


@router.message(F.text == "🤖 AI Maslahatchi")
async def ai_start(m: Message, state: FSMContext):
    await state.clear()
    await state.update_data(prof={"concerns": []})
    await m.answer("Men AI kosmetologingizman. Sizga eng mos mahsulotni tanlashim uchun 4 ta qisqa savol beraman.")
    await show_step(m, state, 1)


@router.callback_query(F.data == "ai:start")
async def ai_restart(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(prof={"concerns": []})
    await show_step(cb, state, 1)
    await cb.answer()


@router.callback_query(F.data.startswith("ai:s:"))
async def ai_goto(cb: CallbackQuery, state: FSMContext):
    await show_step(cb, state, int(cb.data.split(":")[2]))
    await cb.answer()


@router.callback_query(F.data.startswith("aic:"))
async def ai_concern(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":")[1]
    prof = await get_prof(state)
    sel = set(prof.get("concerns", []))
    if key == "next":
        if not sel and not prof.get("custom_concern"):
            return await cb.answer("Kamida bittasini tanlang yoki o'zingiz yozing", show_alert=True)
        await show_step(cb, state, 2)
        return await cb.answer()
    sel ^= {key}
    prof["concerns"] = [k for k in CONCERNS if k in sel]
    await state.update_data(prof=prof)
    await render(cb, "1/4. Yuzingizdagi muammolarni belgilang (bir nechtasini tanlash mumkin), "
                     "so'ng «Davom etish» ni bosing:", concerns_kb(sel))
    await cb.answer()


@router.callback_query(F.data.startswith("ais:"))
async def ai_skin(cb: CallbackQuery, state: FSMContext):
    prof = await get_prof(state)
    prof["skin"] = cb.data.split(":")[1]
    await state.update_data(prof=prof)
    await show_step(cb, state, 3)
    await cb.answer()


@router.callback_query(F.data.startswith("aia:"))
async def ai_age(cb: CallbackQuery, state: FSMContext):
    prof = await get_prof(state)
    prof["age"] = cb.data.split(":")[1]
    await state.update_data(prof=prof)
    await show_step(cb, state, 4)
    await cb.answer()


def label(prof: dict, key: str, mapping: dict) -> str:
    v = prof.get(key)
    if v == "custom":
        return prof.get(f"{key}_custom", "")
    return mapping.get(v, "")


def wait_text(prof: dict) -> str:
    if prof.get("photo"):
        return "📷 Rasmingizni tahlil qilib, mahsulot tanlayapman, bir oz kuting..."
    return "⏳ Siz uchun mahsulotlarni tanlayapman, bir oz kuting..."


async def run_recommendation(wait: Message, state: FSMContext, bot: Bot):
    """Anketa (va rasm) bo'yicha saytdan tavsiya oladi va natijani `wait` xabariga yozadi."""
    prof = await get_prof(state)
    photo_id = prof.pop("photo", None)
    await state.update_data(prof=prof)

    concerns = [CONCERNS[k] for k in prof.get("concerns", []) if k in CONCERNS]
    if prof.get("custom_concern"):
        concerns.append(prof["custom_concern"])
    payload = {"profile": {
        "concerns": concerns,
        "skin": label(prof, "skin", SKIN),
        "age": label(prof, "age", AGE),
        "want": label(prof, "want", WANT).replace("🧴 ", ""),
    }}

    retry_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Qaytadan", callback_data="ai:start")], [BACK_MENU]])

    if photo_id:
        try:
            import base64
            buf = await bot.download(photo_id)
            payload["profile"]["photo_b64"] = base64.b64encode(buf.getvalue()).decode()
            payload["profile"]["photo_mime"] = "image/jpeg"
        except Exception:
            await wait.edit_text("Rasmni yuklab bo'lmadi, qaytadan urinib ko'ring.", reply_markup=retry_kb)
            return
    try:
        status, res = await api("POST", "/ai/", json=payload, timeout=90)
    except Exception:
        status, res = 0, {}

    if status != 200 or "reply" not in res:
        await wait.edit_text("AI tizimida uzilish bo'ldi, birozdan keyin qayta urinib ko'ring.",
                             reply_markup=retry_kb)
        return

    products = res.get("products", [])
    await state.update_data(ai_ids=[p["id"] for p in products])

    rows = [[InlineKeyboardButton(text=f"➕ {p['name'][:30]} — {money(p['final_price'])}",
                                  callback_data=f"ai:add:{p['id']}")] for p in products]
    if products:
        rows.append([InlineKeyboardButton(text="✅ Hammasini buyurtma qilish", callback_data="ai:order")])
    rows.append([InlineKeyboardButton(text="💬 Savol berish", callback_data="ai:ask"),
                 InlineKeyboardButton(text="🔄 Qaytadan", callback_data="ai:start")])
    rows.append([BACK_MENU])
    await wait.edit_text(fmt_ai(res["reply"]), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("aiw:"))
async def ai_want(cb: CallbackQuery, state: FSMContext):
    prof = await get_prof(state)
    prof["want"] = cb.data.split(":")[1]
    await state.update_data(prof=prof)
    await cb.answer()
    wait = await cb.message.edit_text(wait_text(prof))
    await run_recommendation(wait, state, cb.bot)


CUSTOM_PROMPTS = {
    1: "✍️ Muammoingizni o'zingiz yozing (masalan: ko'z atrofidagi qorayish):",
    2: "✍️ Teringiz turi yoki holatini yozing:",
    3: "✍️ Yoshingizni yozing (masalan: 29):",
    4: "✍️ Sizga nima kerakligini yozing (masalan: lab parvarishi):",
}


@router.callback_query(F.data.startswith("ai:c:"))
async def ai_custom_ask(cb: CallbackQuery, state: FSMContext):
    step = int(cb.data.split(":")[2])
    await state.set_state(AI.custom)
    await state.update_data(custom_step=step)
    await cb.message.answer(CUSTOM_PROMPTS.get(step, CUSTOM_PROMPTS[1]),
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"ai:s:{step}")]]))
    await cb.answer()


@router.message(AI.custom, F.text, ~F.text.in_(MENU_TEXTS))
async def ai_custom_got(m: Message, state: FSMContext):
    d = await state.get_data()
    step = d.get("custom_step", 1)
    prof = await get_prof(state)
    text = " ".join(m.text.split())[:200]
    if step == 1:
        prof["custom_concern"] = text
    elif step == 2:
        prof["skin"], prof["skin_custom"] = "custom", text
    elif step == 3:
        prof["age"], prof["age_custom"] = "custom", text
    else:
        prof["want"], prof["want_custom"] = "custom", text
    await state.update_data(prof=prof)
    await state.set_state(None)
    if step < 4:
        await show_step(m, state, step + 1)
    else:
        wait = await m.answer(wait_text(prof))
        await run_recommendation(wait, state, m.bot)


@router.message(AI.custom, ~F.text)
async def ai_custom_wrong(m: Message):
    await m.answer("Iltimos, javobingizni matn ko'rinishida yozing.")


@router.callback_query(F.data.startswith("ai:add:"))
async def ai_add(cb: CallbackQuery):
    pid = int(cb.data.split(":")[2])
    cart = carts.setdefault(cb.from_user.id, {})
    cart[pid] = cart.get(pid, 0) + 1
    await cb.answer("Savatga qo'shildi ✓")


@router.callback_query(F.data == "ai:order")
async def ai_order(cb: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    ids = d.get("ai_ids") or []
    if not ids:
        return await cb.answer("Tavsiya topilmadi, qaytadan boshlang.", show_alert=True)
    cart = carts.setdefault(cb.from_user.id, {})
    for pid in ids:
        cart[pid] = max(cart.get(pid, 0), 1)
    await state.set_state(Order.name)
    await cb.message.answer("Buyurtma uchun ismingizni yozing:")
    await cb.answer()


@router.callback_query(F.data == "ai:photo")
async def ai_photo_ask(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AI.photo)
    await cb.message.answer(
        "📷 Yuzingizning aniq rasmini yuboring: tabiiy yorug'likda, makiyajsiz, to'g'ridan-to'g'ri qarab.\n\n"
        "Rasm faqat tahlil uchun AI xizmatiga (Google Gemini) yuboriladi, do'konda saqlanmaydi. "
        "Natija tibbiy tashxis emas.\n\nRasmni oddiy rasm sifatida yuboring (fayl emas).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[BACK_MENU]]))
    await cb.answer()


@router.message(AI.photo, F.photo)
async def ai_photo_got(m: Message, state: FSMContext):
    prof = await get_prof(state)
    prof["photo"] = m.photo[-1].file_id
    prof["concerns"] = []
    await state.update_data(prof=prof)
    await state.set_state(None)
    await m.answer("Rasm qabul qilindi ✅ Endi 3 ta qisqa savol:")
    await show_step(m, state, 2)


@router.message(AI.photo, ~F.text.in_(MENU_TEXTS))
async def ai_photo_wrong(m: Message):
    await m.answer("Iltimos, yuzingiz rasmini oddiy rasm sifatida yuboring yoki «Orqaga» ni bosing.")


@router.callback_query(F.data == "ai:ask")
async def ai_ask(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AI.chat)
    await state.update_data(history=[])
    await cb.message.answer("Savolingizni yozing. Tugatish uchun «Orqaga» ni bosing.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[BACK_MENU]]))
    await cb.answer()


@router.callback_query(F.data == "ai:back")
async def ai_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Asosiy menyu 👇", reply_markup=main_menu(cb.from_user.id))
    await cb.answer()


@router.message(AI.chat, ~F.text.in_(MENU_TEXTS))
async def ai_chat(m: Message, state: FSMContext):
    d = await state.get_data()
    history = d.get("history", [])
    status, res = await api("POST", "/ai/", json={"message": m.text, "history": history}, timeout=90)
    reply = res.get("reply") if status == 200 else "AI tizimida uzilish bo'ldi."
    history += [{"role": "user", "text": m.text}, {"role": "assistant", "text": reply}]
    await state.update_data(history=history[-10:])
    await m.answer(fmt_ai(reply))


@router.message(F.text == "📊 Statistika")
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    _, d = await api("GET", "/stats/")
    text = f"📊 <b>Do'kon statistikasi</b>\n\n💰 Daromad: {money(d['revenue'])}\n📈 Sof foyda: {money(d['profit'])}\n\n🛍 Sotilgan:\n"
    text += "".join(f" • {r['name']}: {r['qty']} ta\n" for r in d["top_sales"]) or " • Sotuv yo'q\n"
    text += "\n🔍 Ko'p qidirilgan:\n"
    text += "".join(f" • \"{r['text']}\" — {r['count']} marta\n" for r in d["top_queries"]) or " • Qidiruv yo'q\n"
    await m.answer(text)


async def on_startup(bot: Bot):
    if WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL + WEBHOOK_PATH, drop_pending_updates=True)


def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    dp.startup.register(on_startup)
    if not WEBHOOK_URL:
        # Lokal sinov: webhook yo'q bo'lsa polling ishlaydi
        import asyncio

        async def run():
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        return asyncio.run(run())

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ok"))  # Render health check
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


if __name__ == "__main__":
    main()