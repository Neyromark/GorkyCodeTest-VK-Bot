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

# Озвучка идёт фоновой задачей: HTTP-ответ бэкенду не ждёт синтеза.
# Иначе ответ задерживается на десятки секунд, у бэкенда срабатывает его
# собственный таймаут (10 сек), диалог завершается ошибкой — а голосовое
# к тому моменту может ещё не уложиться в свой лимит и потеряться.
# Таймаут здесь уже не граница запроса, а страховка от зависшего синтеза:
# раньше стояло 60 сек, и синтез под нагрузкой (длинный ответ, параллельное
# распознавание) в них не укладывался — голосовое молча не отправлялось.
VOICE_REPLY_TIMEOUT = 180
# ВК может ответить ошибкой на загрузку файла или отправку — повторяем один раз
VOICE_SEND_ATTEMPTS = 2
VOICE_SEND_RETRY_DELAY = 2.0

# Незавершённые задачи озвучки держим в сильных ссылках: задача, на которую
# не осталось ссылок, сборщик мусора может закрыть до отправки голосового.
_voice_tasks: set[asyncio.Task] = set()

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

        # Решение «озвучивать или нет» принимаем сейчас, пока отправлен именно
        # этот ответ: к концу синтеза (секунды) пользователь мог уже написать
        # текстом, но этот бот отвечал на его голосовое
        if voice_mode.is_voice_user(payload.user_id):
            _spawn_voice_reply(payload.user_id, payload.message)

        return {
            "query_id": str(query_id), 
            "status": "done", 
            "result": {"sent": True}
        }
    except Exception as e:
        logger.exception(f"Failed to send message for request {query_id}")
        await idempotency.release(query_id)
        raise HTTPException(status_code=500, detail=str(e))


def _spawn_voice_reply(user_id: int, text: str) -> None:
    """Ставит озвучку ответа в фон и сразу освобождает HTTP-запрос бэкенда."""
    task = asyncio.create_task(_run_voice_reply(user_id, text))
    _voice_tasks.add(task)
    task.add_done_callback(_voice_tasks.discard)


async def _run_voice_reply(user_id: int, text: str) -> None:
    """Озвучка с таймаутом-страховкой; ошибки не поднимаем выше — текст уже ушёл."""
    try:
        await asyncio.wait_for(send_voice_reply(user_id, text), timeout=VOICE_REPLY_TIMEOUT)
    except (asyncio.TimeoutError, TimeoutError):
        logger.exception(f"Voice reply timed out for user {user_id}")
    except Exception:
        logger.exception(f"Voice reply failed for user {user_id}")


async def send_voice_reply(user_id: int, text: str) -> bool:
    """
    Озвучивает текст ответа и отправляет его голосовым сообщением.
    Возвращает True, если голосовое ушло. Ошибка синтеза или загрузки не
    ломает ответ: текст уже отправлен, поэтому логируем и выходим.
    Загрузка и отправка повторяются один раз (сетевые сбои ВК); random_id
    одинаковый во всех попытках, поэтому дубликата пользователь не увидит.
    """
    try:
        voice = await tts.synthesize_voice(text)
    except Exception:
        logger.exception(f"Voice synthesis failed for user {user_id}")
        return False

    if not voice:
        # В тексте нечего произносить (пустой ответ или в нём только эмодзи)
        return False

    # Отдельный random_id: это уже не тот запрос, что с текстом
    random_id = int.from_bytes(uuid.uuid4().bytes[:4], "big")
    for attempt in range(1, VOICE_SEND_ATTEMPTS + 1):
        try:
            attachment = await VoiceMessageUploader(api=bot.api).upload(
                file_source=voice,
                peer_id=user_id,
                # Имя файла влияет на то, как ВК определит тип вложения
                title="voice.ogg",
            )
            await bot.api.messages.send(
                user_id=user_id,
                message="",
                attachment=attachment,
                random_id=random_id,
            )
            logger.info(f"Voice reply sent to user {user_id}")
            return True
        except Exception:
            logger.exception(
                f"Failed to send voice reply to user {user_id} "
                f"(attempt {attempt}/{VOICE_SEND_ATTEMPTS})"
            )
            if attempt < VOICE_SEND_ATTEMPTS:
                await asyncio.sleep(VOICE_SEND_RETRY_DELAY)
    return False