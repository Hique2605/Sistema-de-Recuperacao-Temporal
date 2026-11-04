"""Gravação dos frames dos buffers em arquivos .mp4 (um por câmera) e registro em CSV."""

import csv
import os
import threading
import time

import cv2

from . import config
from .email_sender import enviar_email_videos
from .limpeza import limpar_videos_antigos


def inicializar_csv_eventos(caminho_csv):
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "timestamp_evento",
                "camera",
                "arquivo",
                "qtd_frames",
                "duracao_video_s",
                "latencia_gravacao_s",
                "frames_perdidos_estimado",
                "fps_gravacao",
            ]
        )


def calcular_fps_gravacao(tempos, fps_max):
    """
    FPS REAL com que os frames entraram no buffer.

    Se o loop principal não aguenta o FPS alvo (CPU saturada), entram
    menos frames por segundo do que `fps_max`. Gravar esse buffer com
    `fps_max` faria o vídeo tocar ACELERADO (ex.: 19 fps reais gravados
    como 30 fps -> 1,6x mais rápido). Usando o ritmo medido, o vídeo
    dura o tempo real que foi capturado.
    """
    if len(tempos) < 2:
        return float(fps_max)

    intervalo = tempos[-1] - tempos[0]
    if intervalo <= 0:
        return float(fps_max)

    fps = (len(tempos) - 1) / intervalo
    return max(1.0, min(float(fps_max), fps))


def _gravar_video(itens, nome_camera, timestamp_evento, caminho_csv_eventos, frames_perdidos, logger):
    """
    Grava o .mp4 de UMA câmera. `itens` é a lista [(t_amostra, frame), ...]
    do buffer. Retorna o caminho do arquivo ou None se falhou.
    """
    if not itens:
        logger.warning("[%s] Buffer vazio — nada para gravar.", nome_camera)
        return None

    inicio = time.time()

    tempos = [t for t, _ in itens]
    fps_video = calcular_fps_gravacao(tempos, config.FPS)

    nome_arquivo = f"video_{timestamp_evento}_{nome_camera}.mp4"
    caminho_arquivo = os.path.join(config.PASTA_VIDEOS, nome_arquivo)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(
        caminho_arquivo, fourcc, fps_video, (config.FRAME_WIDTH, config.FRAME_HEIGHT)
    )

    if not out.isOpened():
        logger.error("[%s] Não foi possível iniciar o VideoWriter para %s.", nome_camera, nome_arquivo)
        return None

    logger.info("[%s] Gravando %s frames em %s (%.1f fps)...", nome_camera, len(itens), nome_arquivo, fps_video)

    comprimido = config.BUFFER_JPEG_QUALIDADE > 0
    gravados = 0

    try:
        for indice, (_, frame) in enumerate(itens):
            if comprimido:
                # No buffer o frame está em JPEG (ver main.py); decodifica
                # um por vez para não estourar a memória aqui.
                frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

            out.write(frame)
            gravados += 1

            # Cede o GIL de vez em quando para a thread de métricas rodar.
            if indice % 30 == 0:
                time.sleep(0)
    finally:
        out.release()

    latencia = time.time() - inicio
    duracao_video = gravados / fps_video if fps_video > 0 else 0

    with open(caminho_csv_eventos, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                timestamp_evento,
                nome_camera,
                nome_arquivo,
                gravados,
                round(duracao_video, 3),
                round(latencia, 3),
                frames_perdidos,
                round(fps_video, 2),
            ]
        )

    logger.info(
        "[%s] Vídeo salvo: %s | frames=%s | duração=%.2fs | latência=%.3fs",
        nome_camera,
        caminho_arquivo,
        gravados,
        duracao_video,
        latencia,
    )

    return caminho_arquivo


def salvar_videos(frames_por_camera, timestamp_evento, caminho_csv_eventos, perdidos_por_camera, logger):
    """
    Salva um .mp4 por câmera (todos com o MESMO timestamp_evento, já que
    os snapshots foram tirados no mesmo instante) e depois dispara UM
    único e-mail com todos os vídeos.

    frames_por_camera:   {camera_id: [(t_amostra, frame), ...]}
    perdidos_por_camera: {camera_id: int}  (frames repetidos DESTE evento)

    A gravação é sequencial (uma câmera por vez) de propósito: codificar
    dois .mp4 em paralelo sobrecarrega a CPU.
    """
    caminhos = []

    for camera_id, itens in frames_por_camera.items():
        caminho = _gravar_video(
            itens,
            f"cam{camera_id}",
            timestamp_evento,
            caminho_csv_eventos,
            perdidos_por_camera.get(camera_id, 0),
            logger,
        )
        if caminho:
            caminhos.append(caminho)

    if not caminhos:
        return []

    # E-mail e limpeza são I/O (rede/disco) e só rodam depois dos vídeos
    # já estarem salvos; se falharem, a gravação em si não é afetada.
    threading.Thread(
        target=_pos_processamento,
        args=(caminhos, timestamp_evento, logger),
        daemon=True,
    ).start()

    return caminhos


def _pos_processamento(caminhos, timestamp_evento, logger):
    try:
        enviar_email_videos(caminhos, timestamp_evento, logger)
    except Exception as erro:
        logger.warning("Erro inesperado no envio de e-mail: %s", erro)
    try:
        limpar_videos_antigos(logger)
    except Exception as erro:
        logger.warning("Erro inesperado na limpeza de vídeos: %s", erro)
