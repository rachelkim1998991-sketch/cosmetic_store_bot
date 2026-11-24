from aiogram import F, Router
from aiogram.types import Message

from app.api_client import SITE_DOWN, api, money
from app.config import ADMIN_ID

router = Router()


@router.message(F.text == "📊 Statistika")
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    status, d = await api("GET", "/stats/")
    if status != 200:
        return await m.answer(SITE_DOWN)
    text = (f"📊 <b>Do'kon statistikasi</b>\n\n💰 Daromad: {money(d['revenue'])}\n"
            f"📈 Sof foyda: {money(d['profit'])}\n\n🛍 Sotilgan:\n")
    text += "".join(f" • {r['name']}: {r['qty']} ta\n" for r in d["top_sales"]) or " • Sotuv yo'q\n"
    text += "\n🔍 Ko'p qidirilgan:\n"
    text += "".join(f" • {r['text']}: {r['count']} marta\n"
                    for r in d.get("top_queries", [])) or " • Ma'lumot yo'q\n"
    await m.answer(text)
