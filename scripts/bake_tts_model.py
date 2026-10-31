"""Запекание модели Silero TTS в Docker-образ (см. шаг сборки в Dockerfile).

torch.hub в сборке виснет: байты доходят до 100%, а соединение не закрывается.
Поэтому качаем сами — с таймаутом на сокет, повторами и проверкой размера.
Если не вышло, скрипт возвращает ненулевой код, Dockerfile печатает
предупреждение и не роняет сборку: модель докачается при старте
(см. tts.preload в main.py).
"""

from __future__ import annotations

import os
import socket
import sys
import time
import urllib.request

from omegaconf import OmegaConf

MODELS_YML_URL = "https://raw.githubusercontent.com/snakers4/silero-models/master/models.yml"
LANGUAGE = "ru"
# Та же переменная, что у src/funcs/tts.py: в образе запекаем голос по умолчанию
SPEAKER = os.getenv("TTS_MODEL", "v5_6_ru")

# Таймаут одной операции сокета: обрыв или подвисание не должно висеть минутами
SOCKET_TIMEOUT = 30
ATTEMPTS = 3
RETRY_DELAY = 5
CHUNK_SIZE = 1 << 16  # 64 КБ
PROGRESS_STEP = 25 << 20  # каждые 25 МБ — строчка в лог сборки

# torch.package пишет модель в zip — такой заголовок и проверяем
ZIP_MAGIC = b"PK\x03\x04"


def _retry(func, what: str):
    """Вызывает func до ATTEMPTS раз: обрыв сети на повторе — обычное дело."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 — любая ошибка сети/диска повторяема
            print(f"{what}: попытка {attempt}/{ATTEMPTS} не удалась: {exc}", flush=True)
            if attempt == ATTEMPTS:
                raise
            time.sleep(RETRY_DELAY)


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "silero-bake"})
    return urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT)


def _fetch(url: str) -> bytes:
    """Скачивает небольшой файл целиком."""
    with _open(url) as response:
        return response.read()


def _download_package(url: str, dst: str) -> None:
    """Качает пакет модели по частям: сначала в .partial, потом атомарно подменяет."""
    partial = dst + ".partial"
    with _open(url) as response:
        length_header = response.headers.get("Content-Length")
        expected = int(length_header) if length_header else None
        written = 0
        with open(partial, "wb") as file:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                file.write(chunk)
                written += len(chunk)
                if written % PROGRESS_STEP < CHUNK_SIZE:
                    print(f"  скачано {written // (1 << 20)} МБ", flush=True)

    if expected is not None and written != expected:
        raise IOError(f"получено {written} из {expected} байт")

    with open(partial, "rb") as file:
        if file.read(4) != ZIP_MAGIC:
            raise IOError("файл не похож на torch-пакет модели")
    os.replace(partial, dst)
    print(f"  готово: {written} байт", flush=True)


def _clean_partials(folder: str) -> None:
    """Убирает недокачанные *.partial от прерванных попыток."""
    for name in os.listdir(folder):
        if name.endswith(".partial"):
            os.remove(os.path.join(folder, name))


def main() -> int:
    socket.setdefaulttimeout(SOCKET_TIMEOUT)

    import silero

    silero_dir = os.path.dirname(silero.__file__)

    # 1. models.yml: silero ищет его в <site-packages>/../.., затем в каталоге запуска.
    #    Пишем в оба места: /app при docker compose монтируется каталогом хоста.
    print(f"Скачивание {MODELS_YML_URL} ...", flush=True)
    yml_bytes = _retry(lambda: _fetch(MODELS_YML_URL), "models.yml")
    yml_paths = [
        os.path.abspath(os.path.join(silero_dir, "..", "..", "models.yml")),
        os.path.join(os.getcwd(), "latest_silero_models.yml"),
    ]
    for path in yml_paths:
        with open(path, "wb") as file:
            file.write(yml_bytes)

    # 2. Адрес пакета модели — из свежего models.yml, как это делает сам silero
    models = OmegaConf.load(yml_paths[0])
    try:
        package_url = models.tts_models[LANGUAGE][SPEAKER].latest.package
    except Exception:
        print(f"Модель {SPEAKER} не найдена в models.yml — запекание пропущено", flush=True)
        return 1

    # 3. Сама модель (~140 МБ)
    model_dir = os.path.join(silero_dir, "model")
    os.makedirs(model_dir, exist_ok=True)
    _clean_partials(model_dir)

    dst = os.path.join(model_dir, os.path.basename(package_url))
    if os.path.isfile(dst):
        print(f"Модель уже на месте: {dst} ({os.path.getsize(dst)} байт)", flush=True)
        return 0

    print(f"Скачивание модели {SPEAKER}: {package_url} ...", flush=True)
    _retry(lambda: _download_package(package_url, dst), f"модель {SPEAKER}")
    print(f"Модель запечена: {dst} ({os.path.getsize(dst)} байт)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — Dockerfile напечатает предупреждение
        print(f"Не удалось запечь модель Silero: {exc}", flush=True)
        sys.exit(1)
