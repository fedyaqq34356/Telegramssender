import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import accounts, groups, parser, inviter, broadcaster, publics
from handlers import public_inviter
from logger import logger


async def main():
    logger.info("Запуск бота")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(accounts.router)
    dp.include_router(groups.router)
    dp.include_router(parser.router)
    dp.include_router(inviter.router)
    dp.include_router(broadcaster.router)
    dp.include_router(publics.router)
    dp.include_router(public_inviter.router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())