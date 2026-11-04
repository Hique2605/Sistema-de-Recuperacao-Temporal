"""
Câmera falsa (sintética) — mesma interface pública de CameraStream,
usada só para testes/demonstração sem depender de uma câmera real.

Gera frames com um contador e o timestamp desenhados, num ritmo
configurável (útil pra simular câmera "lenta" ou "engasgando").
"""

import threading
import time

import cv2
import numpy as np


class FakeCameraStream:
    def __init__(self, width, height, fps_simulado=30, logger=None):
        self.width = width
        self.height = height
        self.fps_simulado = fps_simulado
        self.logger = logger

        self._lock = threading.Lock()
        self._frame = None
        self._frame_time = None
        self._contador = 0
        self._running = threading.Event()
        self._running.set()

        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _loop(self):
        intervalo = 1.0 / self.fps_simulado
        proxima = time.monotonic()

        while self._running.is_set():
            agora = time.monotonic()
            if agora < proxima:
                time.sleep(proxima - agora)
            proxima += intervalo

            frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            frame[:] = (40, 40, 40)

            self._contador += 1
            texto = f"frame {self._contador}"
            hora = time.strftime("%H:%M:%S")

            cv2.putText(frame, texto, (20, self.height // 2 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, hora, (20, self.height // 2 + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            with self._lock:
                self._frame = frame
                self._frame_time = time.monotonic()

    def read(self):
        with self._lock:
            if self._frame is None:
                return False, None, None
            return True, self._frame, self._frame_time

    def stop(self):
        self._running.clear()
        self._thread.join(timeout=2)

    @property
    def fps_informado(self):
        return float(self.fps_simulado)

    @property
    def resolucao_informada(self):
        return (self.width, self.height)
