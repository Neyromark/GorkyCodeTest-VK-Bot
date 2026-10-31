FROM python:3.12-slim

# Устанавливаем ffmpeg и очищаем кэш apt для уменьшения размера слоя
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# PyTorch только для CPU: сборка с CUDA тянет несколько гигабайт, боту она не нужна
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
# Модель Silero TTS (~140 МБ) запекаем на этапе сборки, чтобы бот стартовал сразу.
# Качаем своим скриптом: torch.hub в сборке виснет после получения байт.
# Если не вышло — сборку не роняем: модель докачается при старте
# (см. tts.preload в main.py). TTS_MODEL переопределяет модель по умолчанию.
COPY scripts/bake_tts_model.py scripts/
RUN python scripts/bake_tts_model.py \
    || echo "ПРЕДУПРЕЖДЕНИЕ: модель Silero не скачалась при сборке, будет загружена при старте"

COPY . .
CMD ["python", "main.py"]
