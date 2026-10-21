import asyncio

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import AttachmentTypeRule

from src.funcs.stt import transcribe_vk_audio

labeler = BotLabeler()
labeler.vbml_ignore_case = True


@labeler.private_message(text=["начать"])
async def handler_menu(message: Message):
    await message.answer("Привет")


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

    await message.answer("Скачиваю голосовое сообщение и распознаю текст...")

    try:
        # 3. Скачиваем файл в бинарном виде с помощью встроенного http-клиента vkbottle
        # Файлы сохраняются во временный буфер в памяти, не засоряя диск
        http_client = message.ctx_api.http_client
        file_bytes = await http_client.request_content(file_url)

        # 4. Запускаем "тяжелую" функцию Vosk в отдельном потоке,
        # чтобы бот не зависал во время распознавания аудио
        text_result = await asyncio.to_thread(transcribe_vk_audio, file_bytes)

        # 5. Возвращаем результат пользователю
        if text_result.strip():
            await message.answer(f"📝 Текст вашего сообщения:\n\n{text_result}")
        else:
            await message.answer("⚠️ Не удалось разобрать слова в аудио.")

    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при обработке: {e}")
