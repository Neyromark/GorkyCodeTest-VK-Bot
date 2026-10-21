import io
import json

from pydub import AudioSegment
from vosk import KaldiRecognizer, Model


# Изменили первый аргумент на file_bytes
def transcribe_vk_audio(file_bytes: bytes) -> str:
    """
    Принимает байты файла из vkbottle, конвертирует в WAV и распознает через Vosk.
    """
    print("Загрузка аудиофайла и конвертация для Vosk...")

    # ИСПРАВЛЕНИЕ: Оборачиваем байты в io.BytesIO, чтобы pydub прочитал их из памяти
    audio = AudioSegment.from_file(io.BytesIO(file_bytes))

    # Приводим к стандарту Vosk: моно, 16000 Гц, 16-бит
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    # Экспортируем в байты (WAV) в оперативной памяти
    wav_io = io.BytesIO()
    audio.export(wav_io, format="wav")
    wav_io.seek(0)

    print("Инициализация модели Vosk...")
    # Явное имя модели гарантирует стабильное автоскачивание
    model = Model(model_name="vosk-model-small-ru-0.22")
    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(False)

    print("Распознавание речи...")
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
