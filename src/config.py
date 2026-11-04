"""
Configurações centrais do sistema de gravação.

Todas as constantes usadas pelos outros módulos vêm daqui. Nada de
número mágico espalhado pelo código — se precisar mudar algo, muda
aqui (ou no .env).
"""

import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

# Opções do FFmpeg usadas pelo OpenCV nas conexões RTSP (precisa ser
# definido ANTES do primeiro cv2.VideoCapture). TCP evita artefatos por
# perda de pacote UDP; nobuffer/low_delay reduzem o atraso interno.
# Se quiser sobrescrever, defina OPENCV_FFMPEG_CAPTURE_OPTIONS no ambiente.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
)


# =========================================================
# Câmera IP
# =========================================================

CAMERA_IP = os.getenv("CAMERA_IP")
CAMERA_USUARIO = os.getenv("CAMERA_USUARIO")
CAMERA_SENHA = os.getenv("CAMERA_SENHA")

if not CAMERA_IP or not CAMERA_USUARIO or not CAMERA_SENHA:
    raise SystemExit(
        "\n[ERRO] Configuração da câmera não encontrada.\n\n"
        "Verifique o arquivo .env e configure:\n"
        "CAMERA_IP=\n"
        "CAMERA_USUARIO=\n"
        "CAMERA_SENHA=\n"
    )

# Caminho RTSP padrão (Intelbras/Dahua). Pode ser trocado por câmera
# com CAMERA_RTSP_PATH / CAMERA2_RTSP_PATH no .env.
RTSP_PATH_PADRAO = "/cam/realmonitor?channel=1&subtype=0"


def _montar_rtsp(usuario, senha, ip, caminho):
    if not caminho.startswith("/"):
        caminho = "/" + caminho
    # quote(): senha com @ : / # etc. quebraria a URL se fosse colada crua.
    return f"rtsp://{quote(usuario, safe='')}:{quote(senha, safe='')}@{ip}:554{caminho}"


# Lista de câmeras. A câmera 1 usa CAMERA_IP/USUARIO/SENHA (como
# sempre foi). As demais (CAMERA2_*, CAMERA3_*, ... até CAMERA9_*)
# são opcionais: se CAMERAn_IP não existir no .env, a câmera n não
# é usada. Usuário e senha da câmera n herdam os da câmera 1 se não
# forem informados.
CAMERAS = [
    {
        "id": 1,
        "nome": "cam1",
        "ip": CAMERA_IP,
        "rtsp": _montar_rtsp(
            CAMERA_USUARIO, CAMERA_SENHA, CAMERA_IP,
            os.getenv("CAMERA_RTSP_PATH", RTSP_PATH_PADRAO),
        ),
    }
]

for _n in range(2, 10):
    _ip = os.getenv(f"CAMERA{_n}_IP")
    if not _ip:
        continue
    CAMERAS.append(
        {
            "id": _n,
            "nome": f"cam{_n}",
            "ip": _ip,
            "rtsp": _montar_rtsp(
                os.getenv(f"CAMERA{_n}_USUARIO", CAMERA_USUARIO),
                os.getenv(f"CAMERA{_n}_SENHA", CAMERA_SENHA),
                _ip,
                os.getenv(f"CAMERA{_n}_RTSP_PATH", RTSP_PATH_PADRAO),
            ),
        }
    )

# Mantido por compatibilidade (câmera 1).
CAMERA_RTSP = CAMERAS[0]["rtsp"]


# =========================================================
# Vídeo / Buffer
# =========================================================

BUFFER_SECONDS = int(os.getenv("BUFFER_SECONDS", "30"))

# FPS ALVO do sistema (não é imposto pela câmera, é o ritmo que
# nós escolhemos amostrar os frames — ver src/camera.py).
FPS = max(1, int(os.getenv("FPS", "30")))

FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "1280"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "720"))

MAX_FRAMES = BUFFER_SECONDS * FPS

# Tamanho do buffer interno do OpenCV/FFmpeg. Mantido baixo para
# evitar acúmulo de frames atrasados (a causa do "salto pra 300").
CAPTURE_BUFFERSIZE = int(os.getenv("CAPTURE_BUFFERSIZE", "1"))

# Compressão JPEG dos frames guardados no buffer circular (1-100;
# 0 = desligada, guarda o frame cru).
#
# Um frame 1280x720 cru ocupa ~2,7 MB: 900 frames (30s a 30fps) =
# ~2,5 GB POR CÂMERA. Com 2 câmeras isso não cabe num Raspberry Pi de
# 4 GB. Em JPEG cada frame fica em ~100 KB (~90 MB por câmera), ao
# custo de um pouco de CPU para codificar/decodificar.
#
# Padrão: ligada (80), com qualquer número de câmeras: sem compressão,
# 1 câmera 720p@30 chegou a ~3,2 GB de RAM nas medições. Defina
# BUFFER_JPEG_QUALIDADE=0 no .env para guardar frames crus.
_jpeg_padrao = "80"
BUFFER_JPEG_QUALIDADE = int(os.getenv("BUFFER_JPEG_QUALIDADE", _jpeg_padrao))


# Quanto esperar (s) o primeiro frame de cada câmera antes de começar.
TIMEOUT_PRIMEIRO_FRAME_S = float(os.getenv("TIMEOUT_PRIMEIRO_FRAME_S", "10"))

# Falhas seguidas de leitura (~0,05 s cada) até a thread de captura
# fechar e reabrir a conexão RTSP sozinha (queda de rede/câmera reiniciou).
RECONEXAO_APOS_FALHAS = int(os.getenv("RECONEXAO_APOS_FALHAS", "100"))


# =========================================================
# Pastas de saída
# =========================================================

PASTA_VIDEOS = os.getenv("PASTA_VIDEOS", "gravacoes")
PASTA_METRICAS = os.getenv("PASTA_METRICAS", "metricas")
PASTA_LOGS = os.getenv("PASTA_LOGS", "logs")

for pasta in (PASTA_VIDEOS, PASTA_METRICAS, PASTA_LOGS):
    os.makedirs(pasta, exist_ok=True)


# =========================================================
# Monitoramento
# =========================================================

INTERVALO_AMOSTRAGEM_METRICAS = float(
    os.getenv("INTERVALO_AMOSTRAGEM_METRICAS", "1.0")
)


# =========================================================
# Botão físico (GPIO — Raspberry Pi, opcional)
# =========================================================

# Se não definido no .env, o botão físico fica desativado e o
# sistema segue funcionando só com o teclado (S / Q).

_gpio_salvar = os.getenv("GPIO_SALVAR_PIN")
GPIO_SALVAR_PIN = int(_gpio_salvar) if _gpio_salvar else None

# false = pull-down interno (botão liga o GPIO ao 3,3 V)  -> padrão atual
# true  = pull-up interno   (botão liga o GPIO ao GND)
GPIO_PULL_UP = os.getenv("GPIO_PULL_UP", "false").lower() == "true"

_gpio_encerrar = os.getenv("GPIO_ENCERRAR_PIN")
GPIO_ENCERRAR_PIN = int(_gpio_encerrar) if _gpio_encerrar else None


# =========================================================
# E-mail (envio automático do vídeo após cada gravação)
# =========================================================

# Se não ativado, o sistema segue funcionando normalmente sem
# enviar nada — só salva o vídeo localmente, como já fazia.
EMAIL_ATIVADO = os.getenv("EMAIL_ATIVADO", "false").lower() == "true"

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USUARIO = os.getenv("SMTP_USUARIO")
SMTP_SENHA = os.getenv("SMTP_SENHA")
EMAIL_REMETENTE = os.getenv("EMAIL_REMETENTE", SMTP_USUARIO)
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO")

if EMAIL_ATIVADO and not all([SMTP_HOST, SMTP_USUARIO, SMTP_SENHA, EMAIL_DESTINATARIO]):
    raise SystemExit(
        "\n[ERRO] EMAIL_ATIVADO=true mas faltam configurações de e-mail.\n\n"
        "Verifique o arquivo .env e configure:\n"
        "SMTP_HOST=\nSMTP_PORT=587\nSMTP_USUARIO=\nSMTP_SENHA=\nEMAIL_DESTINATARIO=\n"
    )

# Tamanho máximo (em MB) dos vídeos anexados no e-mail, SOMADOS (um
# único e-mail leva o vídeo de todas as câmeras). Vídeos que não
# couberem nesse total vão sem anexo (o e-mail só avisa onde o arquivo
# está salvo) — evita o provedor SMTP rejeitar o envio por causa de
# anexo grande. Anexos viajam em base64 (+33%), então 18 MB viram ~24 MB
# no envio — cabe no limite de ~25 MB do Gmail; 20 MB não caberia.
EMAIL_TAMANHO_MAX_MB = float(os.getenv("EMAIL_TAMANHO_MAX_MB", "18"))


# =========================================================
# Retenção de vídeos (limpeza automática do pen drive/disco)
# =========================================================

# A cada vídeo salvo, o sistema também varre PASTA_VIDEOS e apaga
# qualquer vídeo mais antigo que RETENCAO_DIAS dias (baseado na data
# do arquivo). Ex: RETENCAO_DIAS=2 e hoje é dia 16 -> vídeos do dia
# 14 (e anteriores) são apagados; dias 15 e 16 ficam.
# Mínimo 1: com 0 o vídeo recém-salvo seria apagado na hora.
RETENCAO_DIAS = max(1, int(os.getenv("RETENCAO_DIAS", "2")))
