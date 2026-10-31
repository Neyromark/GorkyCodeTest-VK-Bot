import asyncio
import logging
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from vkbottle import VoiceMessageUploader

from src.bot import bot
from src.api.idempotency import InMemoryIdempotency
from src.funcs import tts, voice_mode

logger = logging.getLogger(__name__)

# Голосовое — по возможности: зависший синтез или загрузка не должны
# задерживать основной ответ, текст он уже получил
VOICE_REPLY_TIMEOUT = 60

class SendMessagePayload(BaseModel):
    type: str = Field(..., pattern="^message$")
    user_id: int
    message: str

app = FastAPI(title="VK Bot API")
idempotency = InMemoryIdempotency(ttl_seconds=86400)

def parse_request_id(request_id: str | None) -> uuid.UUID:
    if request_id is None:
        raise HTTPException(status_code=400, detail="Не передан заголовок X-Request-ID")
    try:
        query_id = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Request-ID не является UUID")
    if query_id.version != 4:
        raise HTTPException(status_code=400, detail="X-Request-ID должен быть UUID4")
    return query_id

@app.post("/api/v1/send-message")
async def send_message(
    payload: SendMessagePayload,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
):
    query_id = parse_request_id(x_request_id)

    if not await idempotency.try_acquire(query_id):
        logger.info(f"Request {query_id} already done, skipping")
        return {"query_id": str(query_id), "status": "already_done", "result": None}

    try:
        random_id = int.from_bytes(query_id.bytes[:4], "big")

        await bot.api.messages.send(
            user_id=payload.user_id,
            message=payload.message,
            random_id=random_id,
        )
        
        logger.info(f"Message sent to user {payload.user_id} (request {query_id})")

        if voice_mode.is_voice_user(payload.user_id):
            try:
                await asyncio.wait_for(
                    send_voice_reply(payload.user_id, payload.message),
                    timeout=VOICE_REPLY_TIMEOUT,
                )
            except (asyncio.TimeoutError, TimeoutError):
                logger.exception(f"Voice reply timed out for user {payload.user_id}")

        return {
            "query_id": str(query_id), 
            "status": "done", 
            "result": {"sent": True}
        }
    except Exception as e:
        logger.exception(f"Failed to send message for request {query_id}")
        await idempotency.release(query_id)
        raise HTTPException(status_code=500, detail=str(e))


async def send_voice_reply(user_id: int, text: str) -> None:
    """
    Озвучивает текст ответа и отправляет его голосовым сообщением.
    Ошибка синтеза или загрузки не ломает ответ: текст уже отправлен,
    поэтому логируем и выходим.
    """
    try:
        voice = await tts.synthesize_voice(text)
        if not voice:
            return

        attachment = await VoiceMessageUploader(api=bot.api).upload(
            file_source=voice,
            peer_id=user_id,
            # Имя файла влияет на то, как ВК определит тип вложения
            title="voice.ogg",
        )
        # Отдельный random_id: это уже не тот запрос, что с текстом
        random_id = int.from_bytes(uuid.uuid4().bytes[:4], "big")
        await bot.api.messages.send(
            user_id=user_id,
            message="",
            attachment=attachment,
            random_id=random_id,
        )
        logger.info(f"Voice reply sent to user {user_id}")
    except Exception:
        logger.exception(f"Failed to send voice reply to user {user_id}")