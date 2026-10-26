import io
import json
import logging

from pydub import AudioSegment
from vosk import KaldiRecognizer, Model

logger = logging.getLogger(__name__)

# Изменили первый аргумент на file_bytes
def transcribe_vk_audio(file_bytes: bytes) -> str:
    """
    Принимает байты файла из vkbottle, конвертирует в WAV и распознает через Vosk.
    """

    logger.info("Загрузка аудиофайла и конвертация для Vosk...")
    try:
        audio = AudioSegment.from_file(io.BytesIO(file_bytes), format="ogg")
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    except Exception as e:
        logger.error(f"Не удалось распознать формат файла (возможно, это не аудио): {e}")
        return
  

    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)

    model = Model(model_name="vosk-model-small-ru-0.22")
    rec = KaldiRecognizer(model, 16000)
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
