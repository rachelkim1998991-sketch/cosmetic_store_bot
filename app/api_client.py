"""Sayt API'si bilan aloqa va umumiy yordamchi funksiyalar."""
import html
import logging
import re

import httpx

from app.config import API_TOKEN, SITE_URL

SITE_DOWN = "Sayt bilan bog'lanib bo'lmadi, birozdan keyin qayta urinib ko'ring."


def money(v) -> str:
    return f"{int(v):,}".replace(",", ".") + " so'm"


async def api(method: str, path: str, timeout: int = 30, **kw):
    """(status_code, json) qaytaradi. Tarmoq xatosida (0, {})."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.request(method, f"{SITE_URL}/api{path}",
                                headers={"X-Bot-Token": API_TOKEN}, **kw)
        try:
            data = r.json()
        except ValueError:
            data = {}
        return r.status_code, data
    except httpx.HTTPError:
        logging.exception("API so'rovi muvaffaqiyatsiz: %s %s", method, path)
        return 0, {}


def fmt_ai(text: str) -> str:
    """AI javobidagi **qalin** belgilarni Telegram HTML'ga aylantiradi."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text))


def split_html(text: str, limit: int = 3500) -> list[str]:
    """Uzun matnni Telegram limitiga (4096) sig'adigan, HTML-xavfsiz bo'laklarga bo'ladi."""
    chunks, cur = [], ""
    for line in (text or "").splitlines():
        # juda uzun qatorni escape qilishdan OLDIN bo'lamiz (entity o'rtasidan kesilmasin)
        for i in range(0, max(len(line), 1), 800):
            piece = html.escape(line[i:i + 800])
            if len(cur) + len(piece) + 1 > limit:
                chunks.append(cur)
                cur = ""
            cur += piece + "\n"
    if cur.strip():
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]
