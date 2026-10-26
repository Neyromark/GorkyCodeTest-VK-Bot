import asyncio
import time
import uuid

class InMemoryIdempotency:
    """Хранит UUID запросов, которые уже были выполнены."""

    def __init__(self, ttl_seconds: int = 86400):  # ограничение на хранение запроса 24 часа
        self._seen: dict[uuid.UUID, float] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl_seconds

    async def try_acquire(self, query_id: uuid.UUID) -> bool:
        """True — запрос новый, можно выполнять.
        False — уже был, пропускаем."""
        async with self._lock:
            self._gc()
            if query_id in self._seen:
                return False
            self._seen[query_id] = time.time()
            return True

    async def release(self, query_id: uuid.UUID) -> None:
        """Удаляет UUID при ошибке, чтобы бэкенд мог повторить запрос."""
        async with self._lock:
            self._seen.pop(query_id, None)
    def _gc(self):
        now = time.time()
        expired = [k for k, t in self._seen.items() if now - t > self._ttl]
        for k in expired:
            del self._seen[k]