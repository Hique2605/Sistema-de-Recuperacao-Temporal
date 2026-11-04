"""
Monitoramento de sistema (CPU, RAM, FPS real, tamanho do buffer de cada câmera).

O "FPS real" é o ritmo do loop principal (quantas rodadas de captura
por segundo); em cada rodada entra 1 frame de CADA câmera no seu buffer.

FIX DO BUG DE FPS
------------------
A versão original calculava:

    fps_real = (atual - ultimo_contador) / INTERVALO_AMOSTRAGEM_METRICAS

ou seja, dividia pelo intervalo NOMINAL (1.0s), assumindo que
`time.sleep(1.0)` sempre dorme exatamente 1 segundo. Na prática não
dorme: GIL, escalonamento do SO e outras threads (como a de gravação)
atrasam a volta do sleep. Se o intervalo real foi 1.4s mas você divide
por 1.0s, o FPS medido fica artificialmente mais alto.

Aqui usamos time.monotonic() para medir o tempo REAL decorrido entre
duas amostragens e dividimos por esse valor.

Durante o salvamento de vídeo a captura continua (roda em segundo
plano), então o FPS real segue sendo medido normalmente.
"""

import csv
import os
import time
from datetime import datetime

import psutil

from . import config


def inicializar_csv_sistema(caminho_csv, ids_cameras=(1,)):
    """Uma coluna de frames no buffer por câmera (frames_buffer_cam1, ...)."""
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["timestamp", "cpu_percent", "ram_percent", "ram_mb", "fps_real"]
            + [f"frames_buffer_cam{i}" for i in ids_cameras]
        )


def monitor_sistema(
    parar_evento,
    contador_frames,
    lock_contadores,
    buffers,
    caminho_csv_sistema,
    logger,
    salvando_em_andamento=None,
):
    processo = psutil.Process(os.getpid())

    # A primeira chamada de cpu_percent(None) sempre devolve 0.0; faz
    # uma leitura "descartável" para a primeira amostra do CSV valer.
    psutil.cpu_percent(interval=None)

    ultimo_tempo = time.monotonic()
    ultimo_contador = 0

    while not parar_evento.is_set():
        time.sleep(config.INTERVALO_AMOSTRAGEM_METRICAS)

        agora = time.monotonic()
        elapsed = agora - ultimo_tempo  # tempo real decorrido, não o nominal
        ultimo_tempo = agora

        cpu = psutil.cpu_percent(interval=None)
        ram_percent = processo.memory_percent()
        ram_mb = processo.memory_info().rss / (1024 * 1024)

        with lock_contadores:
            atual = contador_frames["capturados"]

        fps_real = (atual - ultimo_contador) / elapsed if elapsed > 0 else 0.0
        ultimo_contador = atual

        # buffers: {camera_id: FrameBuffer}
        quantidades = {cam_id: len(buf) for cam_id, buf in buffers.items()}

        with open(caminho_csv_sistema, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    round(cpu, 1),
                    round(ram_percent, 2),
                    round(ram_mb, 1),
                    round(fps_real, 1),
                ]
                + list(quantidades.values())
            )

        texto_buffers = " | ".join(
            f"cam{cam_id}: {qtd}/{config.MAX_FRAMES}" for cam_id, qtd in quantidades.items()
        )
        salvando = salvando_em_andamento is not None and salvando_em_andamento.is_set()
        logger.info(
            "CPU: %.1f%% | RAM: %.1f MB | FPS real: %.1f | Buffer %s%s",
            cpu,
            ram_mb,
            fps_real,
            texto_buffers,
            " | SALVANDO VÍDEO (em segundo plano)" if salvando else "",
        )
