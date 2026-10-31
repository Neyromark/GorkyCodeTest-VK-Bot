import uuid, aiohttp, logging, os

from vkbottle.bot import Message
from vkbottle.http import ABCHTTPClient

logger = logging.getLogger(__name__)

BACKEND_HOST = os.getenv("HOST", "localhost")
BACKEND_PORT = os.getenv("PORT", "8000")

# Бэкенд прогоняет сообщение через LLM, поэтому обычных 10 сек не хватало:
# на живом диалоге запрос падал в таймаут, пользователь видел ошибку
# (и совет «написать текстом»), а ответ на голосовое приходил текстом.
REQUEST_TIMEOUT = 30

async def send_http(session: ABCHTTPClient, user_id: int, text: str) -> dict | None:
    """
    Отправляет сообщение пользователя на бэкенд.
    """
    payload = {
        "type": "message",
        "user_id": user_id,
        "message": text,
    }
    
    # Генерируем уникальный ID для этого запроса
    request_id = str(uuid.uuid4())
    headers = {
        "X-Request-ID": request_id,
    }

    try:
        # Делаем POST запрос
        data = await session.request_json(
            url=f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/get-message",
            method="POST",
            json=payload, 
            headers=headers, 
            timeout=REQUEST_TIMEOUT  # Таймаут в секундах
        )
        logger.info(f"Бэкенд успешно обработал {request_id}. Статус: {data.get('status')}")
        return data

    # Таймаут (asyncio.TimeoutError — это TimeoutError в Python 3.11+) тоже
    # означает «сервер не ответил»: возвращаем None, а не кидаем исключение,
    # иначе выше печатается общая ошибка обработки аудиофайла
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.error(f"Не удалось достучаться до бэкенда: {e}")
        return None

