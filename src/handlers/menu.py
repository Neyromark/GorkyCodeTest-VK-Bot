import asyncio
import logging

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import AttachmentTypeRule, MessageLengthRule

from src.funcs.stt import transcribe_vk_audio
from src.funcs import voice_mode
from src.bot import bot
from src.funcs.sender import send_http

logger = logging.getLogger(__name__)

labeler = BotLabeler()
labeler.vbml_ignore_case = True

# Ограничиваем число одновременных распознаваний, чтобы не перегружать CPU/память
MAX_CONCURRENT_TRANSCRIPTIONS = 2
_transcribe_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TRANSCRIPTIONS)


@labeler.private_message(text=["начать"])
async def handler_menu(message: Message):
    await message.answer("Привет")

@labeler.private_message(MessageLengthRule(min_length=1))
async def text_handler(message: Message):
    if not message.text:
        return

    # Пишет текстом — и ответы бота остаются текстовыми
    voice_mode.mark_text(message.from_id)

    try:
        result = await send_http(
            session=message.ctx_api.http_client,
            user_id=message.from_id,
            text=message.text
        )

        if result is None:
            await message.answer("❌ Сервер недоступен или вернул ошибку. Попробуйте позже.")
    except Exception:
        logger.exception("Ошибка при отправке сообщения на сервер")
        await message.answer("❌ Ошибка при отправке на сервер. Попробуйте позже.")

@labeler.private_message(AttachmentTypeRule("audio_message"))
async def voice_handler(message: Message):
    # 1. Находим объект голосового сообщения среди вложений
    audio_msg = next(
        (att.audio_message for att in message.attachments if att.audio_message), None
    )

    if not audio_msg:
        await message.answer("Не удалось прочитать голосовое сообщение.")
        return

    # 2. Получаем прямую URL-ссылку на аудиофайл (ВК обычно отдает .ogg)
    file_url = audio_msg.link_ogg or audio_msg.link_mp3
    if not file_url:
        await message.answer("Не удалось получить ссылку на файл.")
        return

    status_msg = await message.answer("Скачиваю голосовое сообщение и распознаю текст...")

    try:
        # 3. Скачиваем файл в бинарном виде с помощью встроенного http-клиента vkbottle
        # Файлы сохраняются во временный буфер в памяти, не засоряя диск
        http_client = message.ctx_api.http_client
        file_bytes = await http_client.request_content(
            file_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://vk.com/"
            }
        )
        logger.info(f"Скачано байт: {len(file_bytes)}")
        logger.info(f"Первые 20 байт: {file_bytes[:20]}")

        if file_bytes.startswith(b"<") or file_bytes.startswith(b"{"):
            logger.error("ВК вернул ошибку вместо аудиофайла! Проверь ссылку и User-Agent.")
            await message.ctx_api.messages.delete(
                message_ids=[status_msg.message_id], delete_for_all=True
            )
            await message.answer("⚠️ ВКонтакте не отдал файл. Пожалуйста, попробуйте отправить голосовое ещё раз.")
            return

        # 4. Запускаем "тяжелую" функцию Vosk в отдельном потоке,
        # чтобы бот не зависал во время распознавания аудио
        async with _transcribe_semaphore:
            text_result = await asyncio.to_thread(transcribe_vk_audio, file_bytes)

        # 5. Удаляем промежуточное сообщение перед отправкой результата
        try:
            await message.ctx_api.messages.delete(
                message_ids=[status_msg.message_id],
                delete_for_all=True
            )
        except Exception:
            # Логируем ошибку, но не прерываем отправку результата
            logger.warning("Не удалось удалить промежуточное сообщение", exc_info=True)

        # 6. Возвращаем результат пользователю
        if text_result.strip():
            # Просил голосом — ответ бота продублируется голосовым сообщением
            voice_mode.mark_voice(message.from_id)
            result = await send_http(
                session=message.ctx_api.http_client,
                user_id=message.from_id,
                text=text_result
            )
            if result is None:
                await message.answer("❌ Сервер недоступен или вернул ошибку. Попробуйте позже.")
        else:
            await message.answer("⚠️ Не удалось разобрать слова в аудио. Повторите Ваш запрос.")

    except Exception:
        logger.exception("Ошибка в voice_handler")
        await message.answer("❌ Произошла ошибка при обработке аудиофайла. Попробуйте написать текстом или повторите позднее.")
