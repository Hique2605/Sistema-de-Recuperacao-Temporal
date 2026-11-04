"""
Demonstração do sistema usando FakeCameraStream — não precisa de
câmera real nem de terminal interativo. Roda por um tempo fixo,
dispara um "salvar" automaticamente e encerra sozinho.
"""

import os

# Configura um cenário pequeno/rápido antes de importar o resto,
# já que src/config.py lê as variáveis de ambiente na importação.
os.environ.setdefault("CAMERA_IP", "0.0.0.0")
os.environ.setdefault("CAMERA_USUARIO", "demo")
os.environ.setdefault("CAMERA_SENHA", "demo")
os.environ["BUFFER_SECONDS"] = "5"
os.environ["FPS"] = "10"
os.environ["FRAME_WIDTH"] = "320"
os.environ["FRAME_HEIGHT"] = "240"
os.environ["BUFFER_JPEG_QUALIDADE"] = "0"  # demo guarda frames crus (são pequenos)
os.environ["INTERVALO_AMOSTRAGEM_METRICAS"] = "1.0"

import threading
import time
from datetime import datetime

from src import config
from src.buffer import FrameBuffer
from src.camera_fake import FakeCameraStream
from src.logger_config import configurar_logger
from src.metrics import inicializar_csv_sistema, monitor_sistema
from src.recorder import inicializar_csv_eventos, salvar_videos


def main():
    logger = configurar_logger("demo")

    logger.info("=== DEMONSTRAÇÃO COM CÂMERA SIMULADA ===")
    logger.info("Buffer: %ss | FPS alvo: %s | Resolução: %sx%s",
                config.BUFFER_SECONDS, config.FPS, config.FRAME_WIDTH, config.FRAME_HEIGHT)

    camera = FakeCameraStream(
        config.FRAME_WIDTH, config.FRAME_HEIGHT, fps_simulado=config.FPS, logger=logger
    ).start()

    time.sleep(0.3)

    cam_id = 1
    buffers = {cam_id: FrameBuffer(config.MAX_FRAMES)}
    parar_evento = threading.Event()

    contador_frames = {"capturados": 0, "perdidos": {cam_id: 0}}
    lock_contadores = threading.Lock()

    timestamp_execucao = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_sistema = f"{config.PASTA_METRICAS}/sistema_{timestamp_execucao}.csv"
    csv_eventos = f"{config.PASTA_METRICAS}/eventos_{timestamp_execucao}.csv"

    inicializar_csv_sistema(csv_sistema, [cam_id])
    inicializar_csv_eventos(csv_eventos)

    threading.Thread(
        target=monitor_sistema,
        args=(parar_evento, contador_frames, lock_contadores, buffers, csv_sistema, logger),
        daemon=True,
    ).start()

    intervalo_alvo = 1.0 / config.FPS
    proxima_amostra = time.monotonic()
    ultimo_frame_time = None

    inicio_execucao = time.monotonic()
    duracao_demo = 8.0
    ja_salvou = False
    thread_salvar = None

    while time.monotonic() - inicio_execucao < duracao_demo:
        agora = time.monotonic()
        if agora < proxima_amostra:
            time.sleep(proxima_amostra - agora)
        proxima_amostra += intervalo_alvo

        ret, frame, frame_time = camera.read()
        if not ret:
            continue

        if ultimo_frame_time is not None and frame_time == ultimo_frame_time:
            with lock_contadores:
                contador_frames["perdidos"][cam_id] += 1
        ultimo_frame_time = frame_time

        buffers[cam_id].append((time.monotonic(), frame))
        with lock_contadores:
            contador_frames["capturados"] += 1

        # Dispara um "salvar" automático aos 4 segundos, simulando a tecla S.
        if not ja_salvou and time.monotonic() - inicio_execucao > 4.0:
            ja_salvou = True
            timestamp_evento = datetime.now().strftime("%Y%m%d_%H%M%S")
            frames_para_salvar = {cam_id: buffers[cam_id].snapshot()}
            logger.info("Simulando tecla S — salvando %s frames...", len(frames_para_salvar[cam_id]))

            with lock_contadores:
                perdidos = dict(contador_frames["perdidos"])

            thread_salvar = threading.Thread(
                target=salvar_videos,
                args=(frames_para_salvar, timestamp_evento, csv_eventos, perdidos, logger),
            )
            thread_salvar.start()

    logger.info("Fim da demonstração (%ss). Encerrando...", duracao_demo)
    parar_evento.set()
    if thread_salvar is not None:
        thread_salvar.join()
    camera.stop()

    logger.info("=== DEMO ENCERRADA ===")


if __name__ == "__main__":
    main()
