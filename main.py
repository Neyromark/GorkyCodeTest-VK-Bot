import asyncio
import logging
import uvicorn

from src.bot import bot
from src.handlers import all_handlers
from src.api.listener import app  # <-- импортируем FastAPI приложение

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

#Загружаем все хэндлеры в бота
for handler in all_handlers:
    bot.labeler.load(handler)


async def main():
    logger.info("Запуск VK-бота и HTTP-сервера...")

    # 2. Настраиваем uvicorn для FastAPI
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=80,
        log_level="info",
    )
    server = uvicorn.Server(config)

    try:
        # 3. Запускаем longpoll и HTTP-сервер одновременно
        await asyncio.gather(
            bot.run_polling(),   # <-- асинхронный запуск бота
            server.serve()       # <-- запуск сервера
        )
    except asyncio.CancelledError:
        logger.info("Завершение работы...")

if __name__ == "__main__":
    asyncio.run(main())
