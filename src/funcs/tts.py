"""Синтез речи (Silero TTS) и подготовка голосового сообщения для ВК."""

from __future__ import annotations

import array
import asyncio
import io
import logging
import os
import re
import threading
import unicodedata
import wave

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Русская модель Silero v5: автоударения, омографы, вопросительная интонация
MODEL_ID = os.getenv("TTS_MODEL", "v5_6_ru")
# Голос: aidar, baya, kseniya, xenia, eugene
SPEAKER = os.getenv("TTS_SPEAKER", "baya")

# Синтез в 24 кГц — для голосового сообщения этого достаточно
SAMPLE_RATE = 24000

# Голосовое сообщение ВК: Ogg Opus, 16 кГц, моно, 16 kbit/s, до 5 минут
VK_SAMPLE_RATE = 16000
VK_BITRATE = "16k"

# Ограничение длины: 5 минут записи, с запасом на разговорный темп
MAX_TEXT_LENGTH = 1500

# Модель работает на CPU, поэтому параллельных синтезов — не больше двух
MAX_CONCURRENT_SYNTHESIZATIONS = 2
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNTHESIZATIONS)

_model = None
_model_lock = threading.Lock()


def get_model():
    """
    Загружает модель Silero один раз и переиспользует её между вызовами.
    При первом вызове модель (около 140 МБ) скачивается — в Docker она уже
    скачана на этапе сборки образа, блокировка защищает от параллельной загрузки.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from silero import silero_tts

                logger.info(f"Инициализация модели Silero TTS ({MODEL_ID})...")
                model, _ = silero_tts(language="ru", speaker=MODEL_ID)
                _model = model
    return _model


def preload() -> None:
    """Грузит модель при старте бота, чтобы первый голосовой ответ не ждал скачивание."""
    get_model()


def clean_for_speech(text: str) -> str:
    """
    Готовит текст бота к озвучке: убирает эмодзи и знаки (✅, ⚠️, 💼) —
    Silero их не озвучивает, а ASCII-арт вокруг прочитается как мусор.
    За эмодзи прячутся невидимые символы (variation selector, zero-width joiner):
    их тоже убираем, иначе остаётся пустая на вид строка.
    """

    def keep(char: str) -> bool:
        category = unicodedata.category(char)
        if category[0] == "S":  # эмодзи и знаки
            return False
        if category == "Cf":  # невидимые, например zero-width joiner
            return False
        if 0xFE00 <= ord(char) <= 0xFE0F:  # variation selector, дописанный к эмодзи
            return False
        return True

    return re.sub(r"\s+", " ", "".join(ch for ch in text if keep(ch))).strip()


def _has_speech(text: str) -> bool:
    """Осталось ли в тексте что произнести: буквы или цифры."""
    return any(ch.isalnum() for ch in text)


def _limit_length(text: str) -> str:
    """Обрезает текст по границе предложения — голосовое сообщение ВК живёт до 5 минут."""
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    cut = text[:MAX_TEXT_LENGTH]
    sentence_end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return cut[: sentence_end + 1] if sentence_end > 0 else cut


def _to_wav_bytes(audio) -> bytes:
    """Тензор модели → WAV 16 бит моно, без numpy — через список и array."""
    import torch

    samples = audio.detach().cpu().clamp(-1, 1).mul(32767).to(torch.int16).tolist()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(array.array("h", samples).tobytes())
    return buffer.getvalue()


def synthesize_vk_voice(text: str) -> bytes | None:
    """
    Текст → Ogg Opus 16 кГц моно — формат голосового сообщения ВК.
    None, если озвучивать нечего (пустой текст или в нём только эмодзи).
    """
    text = _limit_length(clean_for_speech(text))
    if not _has_speech(text):
        return None

    model = get_model()
    audio = model.apply_tts(text=text, speaker=SPEAKER, sample_rate=SAMPLE_RATE)
    segment = AudioSegment.from_wav(io.BytesIO(_to_wav_bytes(audio)))

    voice = io.BytesIO()
    segment.export(
        voice,
        format="ogg",
        codec="libopus",
        bitrate=VK_BITRATE,
        # pydub сам не передаёт частоту дискретизации и каналы — задаём явно
        parameters=["-ar", str(VK_SAMPLE_RATE), "-ac", "1", "-application", "voip"],
    )
    return voice.getvalue()


async def synthesize_voice(text: str) -> bytes | None:
    """Синтез в отдельном потоке, не больше двух одновременно — модель занимает CPU."""
    async with _semaphore:
        return await asyncio.to_thread(synthesize_vk_voice, text)
