"""
Wrapper de captura de vídeo via RTSP.

PROBLEMA QUE ISSO RESOLVE
--------------------------
Uma thread dedicada (`_loop`) lê a câmera continuamente e SEMPRE
sobrescreve `self._frame` com o frame mais novo. Nunca enfileira nada:
se o consumidor for mais lento, frames antigos são descartados em vez de
acumulados (era isso que inflava o FPS medido para ~300 no código antigo).

ONDE FICA O CUSTO DE CPU
------------------------
O decoder H.264/H.265 precisa processar TODO pacote que a câmera manda
(o FPS configurado no .env não muda isso — quem muda é o FPS/resolução/
bitrate configurados na própria câmera, ou usar o sub-stream). Mas a
parte de converter para BGR (`retrieve`) e redimensionar só precisa
acontecer nos frames que realmente vão ser amostrados. Por isso o loop
usa `grab()` em todo pacote e `retrieve()` só no ritmo de `fps_alvo`.

RECONEXÃO
---------
Se a leitura falhar `falhas_para_reconectar` vezes seguidas, a conexão é
fechada e reaberta (com espera de 2 s entre tentativas). Enquanto isso o
último frame válido continua sendo entregue (a gravação "congela" em vez
de ficar com buraco na linha do tempo).
"""

import threading
import time

import cv2


class CameraStream:
    def __init__(self, rtsp_url, width, height, buffersize=1, logger=None,
                 fps_alvo=None, falhas_para_reconectar=100):
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self.buffersize = buffersize
        self.logger = logger
        self.falhas_para_reconectar = falhas_para_reconectar

        # Só converte/redimensiona um frame a cada ~1/fps_alvo s. O fator
        # 0.8 dá folga para jitter de chegada (evita pular um frame que
        # chegou um pouco cedo e abrir um buraco de 2 intervalos).
        self._intervalo_min = (0.8 / fps_alvo) if fps_alvo else 0.0

        self.cap = self._abrir()

        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError("Não foi possível conectar à câmera IP.")

        self._lock = threading.Lock()
        self._frame = None
        self._frame_time = None
        self._running = threading.Event()
        self._running.set()
        self._falhas_consecutivas = 0

        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _abrir(self):
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        # Nem todo backend respeita isso, mas quando respeita, reduz
        # o acúmulo de frames atrasados.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.buffersize)
        return cap

    def start(self):
        self._thread.start()
        return self

    def _reconectar(self):
        if self.logger:
            self.logger.warning("Conexão RTSP perdida — tentando reconectar...")

        try:
            self.cap.release()
        except Exception:
            pass

        while self._running.is_set():
            novo = self._abrir()
            if novo.isOpened():
                self.cap = novo
                if self.logger:
                    self.logger.info("Reconectado à câmera.")
                return
            novo.release()

            for _ in range(20):  # espera 2 s, mas sai rápido se for encerrar
                if not self._running.is_set():
                    return
                time.sleep(0.1)

    def _loop(self):
        ultimo_retrieve = 0.0

        while self._running.is_set():
            if not self.cap.grab():
                self._falhas_consecutivas += 1

                if self.logger and self._falhas_consecutivas % 30 == 1:
                    self.logger.warning(
                        "Falha ao ler frame da câmera (tentativa %s).",
                        self._falhas_consecutivas,
                    )

                if self._falhas_consecutivas >= self.falhas_para_reconectar:
                    self._reconectar()
                    self._falhas_consecutivas = 0
                    continue

                time.sleep(0.05)
                continue

            self._falhas_consecutivas = 0

            agora = time.monotonic()
            if agora - ultimo_retrieve < self._intervalo_min:
                continue  # frame já decodificado e descartado: sem BGR/resize

            ret, frame = self.cap.retrieve()
            if not ret:
                continue
            ultimo_retrieve = agora

            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))

            with self._lock:
                self._frame = frame
                self._frame_time = time.monotonic()

    def read(self):
        """
        Retorna (ret, frame, frame_time) do frame mais recente. Não
        bloqueia: se nada mudou, devolve o mesmo frame de novo.

        O frame NÃO é copiado: a thread de captura sempre publica um
        array novo e nunca altera um já publicado, então quem consome
        pode ler à vontade — só não deve modificá-lo no lugar.
        """
        with self._lock:
            if self._frame is None:
                return False, None, None
            return True, self._frame, self._frame_time

    def stop(self):
        self._running.clear()
        self._thread.join(timeout=5)
        # Se a thread ainda estiver presa dentro de um read() de rede,
        # liberar o cap por baixo dela pode derrubar o processo.
        if not self._thread.is_alive():
            self.cap.release()

    @property
    def fps_informado(self):
        return self.cap.get(cv2.CAP_PROP_FPS)

    @property
    def resolucao_informada(self):
        return (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
