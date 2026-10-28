import io
import json
import logging
import threading

from pydub import AudioSegment
from vosk import KaldiRecognizer, Model

logger = logging.getLogger(__name__)

MODEL_NAME = "vosk-model-small-ru-0.22"

_model: Model | None = None
_model_lock = threading.Lock()


def get_model() -> Model:
    """
    Загружает модель Vosk один раз и переиспользует её между вызовами.
    Блокировка не даёт нескольким потокам одновременно грузить/скачивать модель.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Инициализация модели Vosk...")
                _model = Model(model_name=MODEL_NAME)
    return _model


def transcribe_vk_audio(file_bytes: bytes) -> str:
    """
    Принимает байты файла из vkbottle, конвертирует в WAV и распознает через Vosk.
    """

    logger.info("Загрузка аудиофайла и конвертация для Vosk...")
    try:
        # Формат определяет ffmpeg: ВК может отдать как ogg, так и mp3
        audio = AudioSegment.from_file(io.BytesIO(file_bytes))
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    except Exception as e:
        logger.error(f"Не удалось распознать формат файла (возможно, это не аудио): {e}")
        return ""

    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)

    # Модель общая, распознаватель — свой на каждый вызов
    rec = KaldiRecognizer(get_model(), 16000)
    rec.SetWords(False)

    text_results = []
    chunk_size = 4000
    while True:
        data = wav_io.read(chunk_size)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            if res.get("text"):
                text_results.append(res["text"])

    final_res = json.loads(rec.FinalResult())
    if final_res.get("text"):
        text_results.append(final_res["text"])

    full_text = " ".join(text_results)
    return full_text
