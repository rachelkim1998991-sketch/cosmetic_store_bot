"""Kirish nuqtasi: botni ishga tushiradi (Render'da webhook, lokalda polling)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.config import BOT_TOKEN, PORT, WEBHOOK_PATH, WEBHOOK_URL
from app.handlers import routers

logging.basicConfig(level=logging.INFO)


async def health(request):
    return web.Response(text="OK")


async def on_startup(bot: Bot):
    await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
    logging.info("Webhook o'rnatildi: %s%s", WEBHOOK_URL, WEBHOOK_PATH)


def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    for r in routers:
        dp.include_router(r)

    if WEBHOOK_URL:
        dp.startup.register(on_startup)
        app = web.Application()
        app.router.add_get("/", health)
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        web.run_app(app, host="0.0.0.0", port=PORT)
    else:
        async def run_polling():
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
