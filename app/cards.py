"""Mahsulot kartochkalari: rasm + nom/narx + inline tugmalar. Qidiruv va katalog uchun umumiy."""
from __future__ import annotations

import asyncio
import html
import io
import logging
import math
from typing import Callable

import httpx
from aiogram.types import (BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message)

try:
    from PIL import Image
except ImportError:  # Pillow bo'lmasa rasmlar kichraytirilmaydi, lekin bot ishlayveradi
    Image = None

from app.api_client import money

PAGE_SIZE = 8       # sayt API'dagi sahifa hajmi bilan bir xil bo'lishi kerak
THUMB_SIZE = 320    # kartochkadagi rasmning eng katta tomoni (piksel)

# {rasm manzili: Telegram file_id}: bir marta yuborilgan rasm keyingi safar darrov yuboriladi
thumb_ids: dict[str, str] = {}


# ---------- rasmlar ----------

def _make_thumb(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGB")
    im.thumbnail((THUMB_SIZE, THUMB_SIZE))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


async def fetch_thumbs(urls: list[str]) -> dict[str, bytes]:
    """Rasmlarni parallel yuklab, kichraytiradi. Muvaffaqiyatsizlari natijada bo'lmaydi."""
    todo = [u for u in dict.fromkeys(urls) if u and u not in thumb_ids]
    if not todo or Image is None:
        return {}
    out: dict[str, bytes] = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        async def one(url: str):
            try:
                r = await c.get(url)
                r.raise_for_status()
                out[url] = await asyncio.to_thread(_make_thumb, r.content)
            except Exception:
                logging.warning("Rasmni kichraytirib bo'lmadi: %s", url, exc_info=True)
        await asyncio.gather(*(one(u) for u in todo))
    return out


# ---------- matn va tugmalar ----------

def card_text(idx: int, p: dict) -> str:
    price = money(p["final_price"])
    if p.get("is_on_discount"):
        price = f"<s>{money(p['price'])}</s> {price}"
    return f"<b>{idx}. {html.escape(p['name'])}</b>\n{price}"


def title_text(label: str, total: int, page: int, has_next: bool) -> str:
    text = f"{label}: jami {total} ta"
    if page > 1 or has_next:
        text += f" (sahifa {page}/{max(1, math.ceil(total / PAGE_SIZE))})"
    return text


def pager_row(page: int, has_next: bool, page_cb: Callable[[int], str]) -> list[InlineKeyboardButton]:
    row = []
    if page > 1:
        row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=page_cb(page - 1)))
    if has_next:
        row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=page_cb(page + 1)))
    return row


# ---------- yuborish ----------

async def send_card(message: Message, idx: int, p: dict, src: str, page: int, thumbs: dict[str, bytes]):
    """Bitta mahsulot: rasm + nom/narx (rasm tagida) + inline tugmalar.

    src: mahsulot qayerdan ochilgani ('s' = qidiruv, aks holda kategoriya id'si), «Orqaga» uchun kerak.
    """
    caption = card_text(idx, p)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👀 Batafsil", callback_data=f"p:{p['id']}:{src}:{page}"),
        InlineKeyboardButton(text="➕ Savatga", callback_data=f"add:{p['id']}")]])
    url = p.get("image")
    if url:
        if url in thumb_ids:
            photo = thumb_ids[url]
        elif url in thumbs:
            photo = BufferedInputFile(thumbs[url], filename="product.jpg")
        else:
            photo = url          # kichraytirib bo'lmadi: Telegram'ning o'zi manzildan oladi
        try:
            sent = await message.answer_photo(photo, caption=caption, reply_markup=kb)
            if sent.photo:
                thumb_ids[url] = sent.photo[-1].file_id
            return
        except Exception:
            thumb_ids.pop(url, None)
            logging.exception("Kartochka rasmini yuborib bo'lmadi")
    await message.answer(caption, reply_markup=kb)      # rasmsiz kartochka


async def send_cards(message: Message, results: list[dict], *, src: str, page: int, has_next: bool,
                     total: int, label: str, page_cb: Callable[[int], str],
                     footer: list[list[InlineKeyboardButton]], plain_footer_text: str):
    """Sarlavha + har mahsulot uchun kartochka + oxirida sahifa/navigatsiya tugmalari."""
    start = (page - 1) * PAGE_SIZE + 1          # raqamlar sahifalar bo'ylab davom etadi
    thumbs = await fetch_thumbs([p.get("image") for p in results])
    await message.answer(title_text(label, total, page, has_next))
    for i, p in enumerate(results, start):
        await send_card(message, i, p, src, page, thumbs)
    rows = []
    pager = pager_row(page, has_next, page_cb)
    if pager:
        rows.append(pager)
    rows.extend(footer)
    await message.answer("Davom etish 👇" if pager else plain_footer_text,
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def send_compact_list(message: Message, results: list[dict], *, src: str, page: int, has_next: bool,
                            total: int, label: str, page_cb: Callable[[int], str],
                            footer: list[list[InlineKeyboardButton]]):
    """Mahsulotdan «Orqaga» qaytganda: rasmsiz ixcham ro'yxat (kartochkalar yuqorida turibdi)."""
    start = (page - 1) * PAGE_SIZE + 1
    rows = [[InlineKeyboardButton(text=f"{i}. {p['name']} — {money(p['final_price'])}",
                                  callback_data=f"p:{p['id']}:{src}:{page}")]
            for i, p in enumerate(results, start)]
    pager = pager_row(page, has_next, page_cb)
    if pager:
        rows.append(pager)
    rows.extend(footer)
    await message.answer(title_text(label, total, page, has_next),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))