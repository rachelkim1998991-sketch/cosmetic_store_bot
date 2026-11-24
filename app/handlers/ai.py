"""AI maslahatchi: 4 qadamli so'rovnoma, rasm orqali tahlil va erkin savol-javob."""
import asyncio
import base64
import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.api_client import api, fmt_ai, money
from app.cards import fetch_thumbs, send_card
from app.config import ADMIN_ID
from app.handlers.cart import begin_order
from app.keyboards import MENU_TEXTS, main_menu
from app.states import AI
from app.store import carts

router = Router()

CONCERNS = {"acne": "Akne / husnbuzar", "postacne": "Postakne dog'lari", "pigment": "Pigmentatsiya",
            "wrinkle": "Ajinlar", "redness": "Qizarish / sezgirlik", "dry": "Quruqlik",
            "oily": "Yog'lilik / kengaygan poralar"}
SKIN = {"dry": "Quruq", "oily": "Yog'li", "comb": "Aralash", "normal": "Normal",
        "sens": "Sezgir", "unk": "Bilmayman"}
AGE = {"a1": "18 yoshgacha", "a2": "18-25", "a3": "26-35", "a4": "36-45", "a5": "45 dan katta"}
WANT = {"kit": "🧴 To'liq nabor", "cleanser": "Tozalovchi (ko'pik/gel)", "toner": "Toner",
        "serum": "Serum", "cream": "Krem", "spf": "SPF (quyoshdan himoya)"}

CUSTOM_PROMPTS = {
    1: "✍️ Muammoingizni o'zingiz yozing (masalan: ko'z atrofidagi qorayish):",
    2: "✍️ Teringiz turi yoki holatini yozing:",
    3: "✍️ Yoshingizni yozing (masalan: 29):",
    4: "✍️ Sizga nima kerakligini yozing (masalan: lab parvarishi):",
}

STEP1_TEXT = ("1/4. Yuzingizdagi muammolarni belgilang (bir nechtasini tanlash mumkin), "
              "so'ng «Davom etish» ni bosing:")

BACK_MENU = InlineKeyboardButton(text="⬅️ Orqaga", callback_data="ai:back")


# ---------- yordamchilar ----------

def ai_failure_text(chat_id: int, status: int, res: dict) -> str:
    """Mijozga chiroyli xabar; adminga (sizga) qo'shimcha ravishda xatoning haqiqiy sababi ham ko'rsatiladi."""
    logging.warning("AI so'rovi muvaffaqiyatsiz: status=%s javob=%s", status, str(res)[:300])
    text = "AI tizimida uzilish bo'ldi, birozdan keyin qayta urinib ko'ring."
    if chat_id == ADMIN_ID:
        why = res.get("detail") or res.get("error") or (
            "sayt javob bermadi (tarmoq xatosi yoki 90 soniya kutish tugadi)" if status == 0
            else "javobda 'reply' yo'q")
        text += f"\n\n🛠 Admin uchun: status={status}\n{html.escape(str(why)[:300])}"
    return text


async def render(target, text: str, kb: InlineKeyboardMarkup):
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
    await state.set_state(None)
    prof = await get_prof(state)
    if step == 1:
        await render(target, STEP1_TEXT, concerns_kb(set(prof.get("concerns", []))))
    elif step == 2:
        await render(target, "2/4. Teringiz turi qanday?", options_kb("ais", SKIN, 1))
    elif step == 3:
        await render(target, "3/4. Yoshingiz?", options_kb("aia", AGE, 2))
    elif step == 4:
        await render(target, "4/4. Sizga nima kerak?", options_kb("aiw", WANT, 3))


def label(prof: dict, key: str, mapping: dict) -> str:
    v = prof.get(key)
    if v == "custom":
        return prof.get(f"{key}_custom", "")
    return mapping.get(v, "")


def wait_text(prof: dict) -> str:
    if prof.get("photo"):
        return "📷 Rasmingizni tahlil qilib, mahsulot tanlayapman, bir oz kuting..."
    return "⏳ Siz uchun mahsulotlarni tanlayapman, bir oz kuting..."


def ai_actions_rows(has_products: bool) -> list[list[InlineKeyboardButton]]:
    rows = []
    if has_products:
        rows.append([InlineKeyboardButton(text="✅ Hammasini buyurtma qilish", callback_data="ai:order")])
    rows.append([InlineKeyboardButton(text="💬 Savol berish", callback_data="ai:ask"),
                 InlineKeyboardButton(text="🔄 Qaytadan", callback_data="ai:start")])
    rows.append([BACK_MENU])
    return rows


async def load_ai_products(items: list[dict]) -> list[dict]:
    """AI tavsiya qilgan mahsulotlarning to'liq ma'lumotini (rasm, chegirma) saytdan parallel oladi."""
    results = await asyncio.gather(*(api("GET", f"/products/{p['id']}/") for p in items))
    full = []
    for p, (status, data) in zip(items, results):
        if status == 200 and data.get("id") == p["id"]:
            full.append(data)
        else:  # to'liq ma'lumot olinmadi: AI bergan qisqa ma'lumot bilan kartochka chiqadi
            price = int(p.get("final_price") or 0)
            full.append({"id": p["id"], "name": p.get("name") or "Mahsulot", "final_price": price,
                         "price": price, "is_on_discount": False, "image": None})
    return full


# ---------- so'rovnoma ----------

@router.message(F.text == "🤖 AI Maslahatchi")
async def ai_start(m: Message, state: FSMContext):
    await state.clear()
    await state.update_data(prof={"concerns": []})
    await m.answer("Men AI kosmetologingizman. Sizga eng mos mahsulotni tanlashim uchun "
                   "4 ta qisqa savol beraman.")
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
    await render(cb, STEP1_TEXT, concerns_kb(sel))
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


@router.callback_query(F.data.startswith("aiw:"))
async def ai_want(cb: CallbackQuery, state: FSMContext):
    prof = await get_prof(state)
    prof["want"] = cb.data.split(":")[1]
    await state.update_data(prof=prof)
    await cb.answer()
    wait = await cb.message.edit_text(wait_text(prof))
    await run_recommendation(wait, state, cb.bot)


async def run_recommendation(wait: Message, state: FSMContext, bot: Bot):
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
            buf = await bot.download(photo_id)
            payload["profile"]["photo_b64"] = base64.b64encode(buf.getvalue()).decode()
            payload["profile"]["photo_mime"] = "image/jpeg"
        except Exception:
            await wait.edit_text("Rasmni yuklab bo'lmadi, qaytadan urinib ko'ring.", reply_markup=retry_kb)
            return

    status, res = await api("POST", "/ai/", json=payload, timeout=90)
    if status != 200 or "reply" not in res:
        await wait.edit_text(ai_failure_text(wait.chat.id, status, res), reply_markup=retry_kb)
        return

    items = res.get("products", [])
    await state.update_data(
        ai_ids=[p["id"] for p in items],
        ai_items=[{"id": p["id"], "name": p.get("name", ""), "final_price": p.get("final_price", 0)}
                  for p in items])

    # 1) AI matni, 2) har mahsulot uchun rasmli kartochka, 3) amallar tugmalari
    await wait.edit_text(fmt_ai(res["reply"]))
    if items:
        full = await load_ai_products(items)
        thumbs = await fetch_thumbs([p.get("image") for p in full])
        for i, p in enumerate(full, 1):
            await send_card(wait, i, p, "ai", 0, thumbs)
    await wait.answer("Nima qilamiz? 👇",
                      reply_markup=InlineKeyboardMarkup(inline_keyboard=ai_actions_rows(bool(items))))


@router.callback_query(F.data == "aib")
async def ai_back_to_results(cb: CallbackQuery, state: FSMContext):
    """Mahsulot sahifasidan qaytish: tavsiya qilingan mahsulotlarning ixcham ro'yxati."""
    await cb.answer()
    d = await state.get_data()
    items = d.get("ai_items") or []
    if not items:
        return await cb.message.answer(
            "Tavsiya eskirgan, qaytadan boshlang.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=ai_actions_rows(False)))
    rows = [[InlineKeyboardButton(text=f"{i}. {p['name']} — {money(p['final_price'])}",
                                  callback_data=f"p:{p['id']}:ai:0")] for i, p in enumerate(items, 1)]
    rows.extend(ai_actions_rows(True))
    await cb.message.answer("🤖 Tavsiya qilingan mahsulotlar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ---------- "Boshqa" (o'zi yozadi) ----------

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


# ---------- natijadan keyingi amallar ----------

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
    # faqat AI tavsiya qilganlar buyurtma qilinadi (savatdagi boshqa mahsulotlarga tegmaydi)
    await begin_order(cb.message, state, [(pid, cart[pid]) for pid in ids], from_cart=True,
                      intro="Buyurtma uchun ismingizni yozing:")
    await cb.answer()


# ---------- rasm ----------

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


# ---------- erkin savol-javob ----------

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
    await cb.message.answer("Asosiy menyu 👇", reply_markup=main_menu())
    await cb.answer()


@router.message(AI.chat, F.text, ~F.text.in_(MENU_TEXTS))
async def ai_chat(m: Message, state: FSMContext):
    d = await state.get_data()
    history = d.get("history", [])
    status, res = await api("POST", "/ai/", json={"message": m.text, "history": history}, timeout=90)
    reply = res.get("reply") if status == 200 else None
    if not reply:
        return await m.answer(ai_failure_text(m.chat.id, status, res))
    history += [{"role": "user", "text": m.text}, {"role": "assistant", "text": reply}]
    await state.update_data(history=history[-10:])
    await m.answer(fmt_ai(reply))