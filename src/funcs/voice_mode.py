"""Память о том, каким языком пользователь пользуется: голосом или текстом.

Бэкенд отвечает текстом, а бот озвучивает ответ только тем, кто сам написал
голосовое: так синтез не мешает обычной текстовой переписке.
"""

import threading

# Как и дедупликация запросов, хранится в памяти процесса:
# перезапуск бота сбрасывает режим до текстового.
_voice_users: set[int] = set()
_lock = threading.Lock()


def mark_voice(user_id: int) -> None:
    """Пользователь написал голосовое — его ответы стоит озвучивать."""
    with _lock:
        _voice_users.add(user_id)


def mark_text(user_id: int) -> None:
    """Пользователь написал текстом — возвращаемся к текстовым ответам."""
    with _lock:
        _voice_users.discard(user_id)


def is_voice_user(user_id: int) -> bool:
    with _lock:
        return user_id in _voice_users
