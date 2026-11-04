"""
Sistema de gravação contínua em buffer circular — ponto de entrada.

MULTI-CÂMERA
------------
Cada câmera configurada no .env (CAMERA_IP, CAMERA2_IP, ...) tem a sua
própria thread de captura (CameraStream) e o seu próprio buffer
circular. Um único botão (GPIO / tecla S) dispara a gravação de TODAS
ao mesmo tempo: os snapshots dos buffers são tirados no mesmo instante
(vídeos sincronizados) e um único e-mail leva todos os vídeos.

LOOP PRINCIPAL
--------------
O loop principal amostra as CameraStream num intervalo fixo (1/FPS
segundos), medido com time.monotonic(). A câmera pode gerar frames em
qualquer ritmo — quem decide quantos frames por segundo entram nos
buffers circulares é este loop, não o FFmpeg. Isso é o que
efetivamente "trava" o sistema no FPS alvo de forma real.

SALVAMENTO EM SEGUNDO PLANO
---------------------------
Ao pedir para salvar, o snapshot dos buffers é tirado na hora (só copia
referências, é instantâneo) e a codificação dos .mp4 roda numa thread
separada, com prioridade menor (nice). A captura NÃO para: antes ela
ficava pausada por 60-100 s a cada salvamento (perdendo esse trecho),
sem nem aliviar a CPU, porque as threads de decodificação RTSP
continuavam rodando de qualquer forma.
"""

import os
import signal
import threading
import time
from datetime import datetime

import cv2

from . import config
from .buffer import FrameBuffer
from .camera import CameraStream
from .keyboard_control import ler_teclado
from .logger_config import configurar_logger
from .metrics import inicializar_csv_sistema, monitor_sistema
from .recorder import inicializar_csv_eventos, salvar_videos


def _aguardar_primeiro_frame(cameras, timeout_s, logger):
    """Espera até cada câmera entregar o 1º frame (ou estourar o timeout)."""
    limite = time.monotonic() + timeout_s
    pendentes = set(cameras)

    while pendentes and time.monotonic() < limite:
        for cam_id in list(pendentes):
            if cameras[cam_id].read()[0]:
                pendentes.discard(cam_id)
        if pendentes:
            time.sleep(0.05)

    for cam_id in pendentes:
        logger.warning("[cam%s] Nenhum frame recebido em %.0fs — seguindo mesmo assim.", cam_id, timeout_s)


def _salvar_em_segundo_plano(frames_para_salvar, timestamp_evento, csv_eventos, perdidos, logger, salvando_em_andamento):
    # Prioridade menor só para ESTA thread (Linux): a captura ganha a
    # briga por CPU, a gravação do .mp4 só demora um pouco mais.
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)
    except (AttributeError, OSError):
        pass

    try:
        salvar_videos(frames_para_salvar, timestamp_evento, csv_eventos, perdidos, logger)
    except Exception:
        logger.exception("Erro ao salvar os vídeos do evento %s.", timestamp_evento)
    finally:
        salvando_em_andamento.clear()
        logger.info("Gravação do evento %s concluída.", timestamp_evento)


def main():
    logger = configurar_logger()

    logger.info("=" * 42)
    logger.info(" SISTEMA DE GRAVAÇÃO - CÂMERA IP")
    logger.info("=" * 42)

    # -----------------------------------------------------
    # Conexão com as câmeras
    # -----------------------------------------------------
    cameras = {}  # {camera_id: CameraStream}

    for cfg in config.CAMERAS:
        logger.info("[%s] IP: %s — conectando via RTSP...", cfg["nome"], cfg["ip"])
        try:
            stream = CameraStream(
                cfg["rtsp"],
                config.FRAME_WIDTH,
                config.FRAME_HEIGHT,
                buffersize=config.CAPTURE_BUFFERSIZE,
                logger=logger,
                fps_alvo=config.FPS,
                falhas_para_reconectar=config.RECONEXAO_APOS_FALHAS,
            ).start()
        except RuntimeError as erro:
            logger.error("[%s] Falha ao conectar (%s) — %s Seguindo sem ela.", cfg["nome"], cfg["ip"], erro)
            continue

        cameras[cfg["id"]] = stream
        logger.info("[%s] Câmera IP conectada.", cfg["nome"])
        logger.info("[%s] FPS informado pela câmera: %s", cfg["nome"], stream.fps_informado)
        logger.info("[%s] Resolução informada pela câmera: %s", cfg["nome"], stream.resolucao_informada)

    if not cameras:
        logger.error("Nenhuma câmera conectada. Encerrando.")
        return

    if len(cameras) < len(config.CAMERAS):
        logger.warning(
            "Apenas %s de %s câmeras conectadas — o sistema segue com as que conectaram.",
            len(cameras), len(config.CAMERAS),
        )

    logger.info("Resolução utilizada pelo sistema: %sx%s", config.FRAME_WIDTH, config.FRAME_HEIGHT)
    logger.info("FPS alvo do sistema: %s", config.FPS)

    comprimir = config.BUFFER_JPEG_QUALIDADE > 0
    if comprimir:
        logger.info("Buffer comprimido em JPEG (qualidade %s) para economizar RAM.", config.BUFFER_JPEG_QUALIDADE)
    else:
        logger.warning(
            "Buffer SEM compressão: ~%.1f GB de RAM por câmera. Com %s câmera(s) isso pode "
            "faltar memória — considere BUFFER_JPEG_QUALIDADE=80 no .env.",
            config.MAX_FRAMES * config.FRAME_WIDTH * config.FRAME_HEIGHT * 3 / 1e9,
            len(cameras),
        )
    parametros_jpeg = [cv2.IMWRITE_JPEG_QUALITY, config.BUFFER_JPEG_QUALIDADE]

    # Espera as threads de captura entregarem o primeiro frame.
    _aguardar_primeiro_frame(cameras, config.TIMEOUT_PRIMEIRO_FRAME_S, logger)

    # -----------------------------------------------------
    # Estado compartilhado
    # -----------------------------------------------------
    buffers = {cam_id: FrameBuffer(config.MAX_FRAMES) for cam_id in cameras}
    parar_evento = threading.Event()
    salvar_evento = threading.Event()
    salvando_em_andamento = threading.Event()

    contador_frames = {
        "capturados": 0,  # rodadas de captura do loop principal
        "perdidos": {cam_id: 0 for cam_id in cameras},  # por câmera
    }
    lock_contadores = threading.Lock()

    # -----------------------------------------------------
    # CSVs
    # -----------------------------------------------------
    timestamp_execucao = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_sistema = f"{config.PASTA_METRICAS}/sistema_{timestamp_execucao}.csv"
    csv_eventos = f"{config.PASTA_METRICAS}/eventos_{timestamp_execucao}.csv"

    inicializar_csv_sistema(csv_sistema, list(cameras))
    inicializar_csv_eventos(csv_eventos)

    # -----------------------------------------------------
    # Encerramento
    # -----------------------------------------------------
    def encerrar_sistema(signum=None, frame=None):
        logger.info("Encerrando sistema...")
        parar_evento.set()

    signal.signal(signal.SIGINT, encerrar_sistema)
    signal.signal(signal.SIGTERM, encerrar_sistema)

    # -----------------------------------------------------
    # Threads auxiliares
    # -----------------------------------------------------
    threading.Thread(
        target=monitor_sistema,
        args=(parar_evento, contador_frames, lock_contadores, buffers, csv_sistema, logger, salvando_em_andamento),
        daemon=True,
    ).start()

    threading.Thread(
        target=ler_teclado,
        args=(parar_evento, salvar_evento, encerrar_sistema, logger),
        daemon=True,
    ).start()

    # Botão físico (GPIO) — opcional, só ativa se configurado no .env.
    # É UM botão só: ele seta o mesmo salvar_evento, que grava todas
    # as câmeras de uma vez.
    _botoes_gpio = None  # precisa ficar vivo até o fim de main(); ver nota abaixo

    if config.GPIO_SALVAR_PIN is not None:
        try:
            from .gpio_control import iniciar_botoes

            # IMPORTANTE: guardamos o retorno em _botoes_gpio. Se o objeto
            # Button do gpiozero não tiver nenhuma referência viva, o
            # garbage collector do Python o destrói e a escuta do pino
            # para de funcionar silenciosamente (sem erro nenhum).
            _botoes_gpio = iniciar_botoes(
                config.GPIO_SALVAR_PIN,
                config.GPIO_ENCERRAR_PIN,
                salvar_evento,
                encerrar_sistema,
                logger,
            )
            logger.info(
                "Botão físico ativo: GPIO %s (salvar todas as câmeras)%s",
                config.GPIO_SALVAR_PIN,
                f" | GPIO {config.GPIO_ENCERRAR_PIN} (segurar p/ encerrar)"
                if config.GPIO_ENCERRAR_PIN
                else "",
            )
        except ImportError:
            logger.warning(
                "GPIO_SALVAR_PIN configurado mas 'gpiozero' não está instalado. "
                "Instale com: pip install gpiozero. Botão físico desabilitado por ora."
            )
        except Exception as erro:
            logger.warning("Não foi possível iniciar o botão GPIO: %s", erro)

    logger.info("Câmeras ativas: %s | Buffer: %ss (%s frames por câmera) | Vídeos: ./%s/ | Métricas: ./%s/",
                len(cameras), config.BUFFER_SECONDS, config.MAX_FRAMES, config.PASTA_VIDEOS, config.PASTA_METRICAS)
    logger.info("Controles: [S] salvar últimos %ss de todas as câmeras | [Q] encerrar%s", config.BUFFER_SECONDS,
                " | [Botão físico] disponível" if config.GPIO_SALVAR_PIN is not None else "")

    # -----------------------------------------------------
    # Loop principal — ritmo controlado por relógio monotônico
    # -----------------------------------------------------
    intervalo_alvo = 1.0 / config.FPS
    proxima_amostra = time.monotonic()
    ultimo_frame_time = {cam_id: None for cam_id in cameras}
    ultimo_item = {cam_id: None for cam_id in cameras}  # último frame (ou JPEG) guardado
    perdidos_ja_reportados = {cam_id: 0 for cam_id in cameras}
    thread_salvar = None

    try:
        while not parar_evento.is_set():
            agora = time.monotonic()

            if agora < proxima_amostra:
                time.sleep(proxima_amostra - agora)

            proxima_amostra += intervalo_alvo

            # Se atrasamos muito (ex: sistema sobrecarregado), não
            # tentamos "recuperar o tempo perdido" empilhando amostras —
            # isso é o que causaria rajadas. Simplesmente realinhamos.
            if time.monotonic() - proxima_amostra > intervalo_alvo:
                proxima_amostra = time.monotonic()

            t_amostra = time.monotonic()
            algum_frame = False

            for cam_id, camera in cameras.items():
                ret, frame, frame_time = camera.read()

                if not ret:
                    continue

                if ultimo_frame_time[cam_id] is not None and frame_time == ultimo_frame_time[cam_id]:
                    # A câmera não entregou frame novo desde a última
                    # amostra (ela está mais lenta que o FPS alvo).
                    # Reaproveita o item já codificado: não gasta CPU
                    # recomprimindo o mesmo frame em JPEG.
                    with lock_contadores:
                        contador_frames["perdidos"][cam_id] += 1
                    item = ultimo_item[cam_id]
                else:
                    item = frame
                    if comprimir:
                        ok, item = cv2.imencode(".jpg", frame, parametros_jpeg)
                        if not ok:
                            continue
                    ultimo_item[cam_id] = item
                    ultimo_frame_time[cam_id] = frame_time

                # (instante da amostra, frame): o instante permite
                # gravar o vídeo no FPS real (ver recorder.py).
                buffers[cam_id].append((t_amostra, item))
                algum_frame = True

            if not algum_frame:
                continue

            with lock_contadores:
                contador_frames["capturados"] += 1

            if salvar_evento.is_set():
                salvar_evento.clear()

                if thread_salvar is not None and thread_salvar.is_alive():
                    logger.warning("Gravação anterior ainda em andamento — novo pedido ignorado.")
                    continue

                timestamp_evento = datetime.now().strftime("%Y%m%d_%H%M%S")

                # Snapshots de todas as câmeras tirados em sequência
                # imediata (só copiam referências), para os vídeos ficarem
                # alinhados no tempo.
                frames_para_salvar = {cam_id: buf.snapshot() for cam_id, buf in buffers.items()}

                logger.info(
                    "Salvando vídeos em segundo plano (%s)...",
                    ", ".join(f"cam{c}: {len(f)} frames" for c, f in frames_para_salvar.items()),
                )

                # Frames repetidos DESDE o último evento (o contador
                # global é acumulado desde o início da execução).
                with lock_contadores:
                    perdidos_total = dict(contador_frames["perdidos"])
                perdidos_evento = {c: perdidos_total[c] - perdidos_ja_reportados[c] for c in perdidos_total}
                perdidos_ja_reportados = perdidos_total

                salvando_em_andamento.set()
                thread_salvar = threading.Thread(
                    target=_salvar_em_segundo_plano,
                    args=(frames_para_salvar, timestamp_evento, csv_eventos, perdidos_evento, logger, salvando_em_andamento),
                )
                thread_salvar.start()

    finally:
        parar_evento.set()

        # Q/Ctrl+C durante uma gravação: espera terminar, senão o .mp4
        # fica truncado/corrompido.
        if thread_salvar is not None and thread_salvar.is_alive():
            logger.info("Aguardando a gravação em andamento terminar...")
            thread_salvar.join(timeout=600)

        for camera in cameras.values():
            camera.stop()

        logger.info("=" * 42)
        logger.info("EXECUÇÃO ENCERRADA")
        logger.info("Vídeos: ./%s/ | Métricas: ./%s/", config.PASTA_VIDEOS, config.PASTA_METRICAS)
        logger.info("=" * 42)


if __name__ == "__main__":
    main()
