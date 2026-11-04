"""Buffer circular thread-safe para armazenar os últimos N frames."""

import threading
from collections import deque


class FrameBuffer:
    def __init__(self, max_frames):
        self._buffer = deque(maxlen=max_frames)
        self._lock = threading.Lock()

    def append(self, frame):
        with self._lock:
            self._buffer.append(frame)

    def snapshot(self):
        """Retorna uma cópia da lista de frames atual (para gravação)."""
        with self._lock:
            return list(self._buffer)

    def __len__(self):
        with self._lock:
            return len(self._buffer)
