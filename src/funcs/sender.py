import uuid, aiohttp, logging, os

from vkbottle.bot import Message

logger = logging.getLogger(__name__)

BACKEND_HOST = os.getenv("HOST", "localhost")
BACKEND_PORT = os.getenv("PORT", "8000")

async def send_http(session: aiohttp.ClientSession, user_id: int, text: str) -> dict | None:
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
            timeout=10  # Таймаут в секундах
        )
        logger.info(f"Бэкенд успешно обработал {request_id}. Статус: {data.get('status')}")
        return data

    except aiohttp.ClientError as e:
        logger.error(f"Не удалось достучаться до бэкенда: {e}")
        return None

