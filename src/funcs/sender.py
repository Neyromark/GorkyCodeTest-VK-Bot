import uuid, aiohttp, logging, os

from vkbottle.bot import Message
from vkbottle.http import ABCHTTPClient

logger = logging.getLogger(__name__)

BACKEND_HOST = os.getenv("HOST", "localhost")
BACKEND_PORT = os.getenv("PORT", "8000")

async def send_registration(
    session: ABCHTTPClient, 
    user_id: int, 
    user_name: str,  
    timezone: str
) -> dict | None:
    """
    Отправляет данные регистрации пользователя на бэкенд.
    """
    payload = {
        "type": "registration",
        "user_id": user_id,
        "user_name": f"{user_name}".strip(), 
        "user_timezone": timezone
    }
    
    request_id = str(uuid.uuid4())
    headers = {
        "X-Request-ID": request_id,
    }

    try:
        data = await session.request_json(
            url=f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/registration",
            method="POST",
            json=payload, 
            headers=headers, 
            timeout=10
        )
        logger.info(f"Регистрация пользователя {user_id} успешно отправлена. Ответ: {data}")
        return data
    
    except aiohttp.ClientError as e:
        logger.error(f"Не удалось отправить данные регистрации на бэкенд: {e}")
        return None

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
            timeout=10  # Таймаут в секундах
        )
        logger.info(f"Бэкенд успешно обработал {request_id}. Статус: {data.get('status')}")
        return data

    except aiohttp.ClientError as e:
        logger.error(f"Не удалось достучаться до бэкенда: {e}")
        return None

