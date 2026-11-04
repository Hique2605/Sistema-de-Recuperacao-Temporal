"""Testes do cálculo de FPS de gravação e da limpeza de vídeos antigos."""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# src.config exige estas variáveis na importação.
os.environ.setdefault("CAMERA_IP", "0.0.0.0")
os.environ.setdefault("CAMERA_USUARIO", "teste")
os.environ.setdefault("CAMERA_SENHA", "teste")

from src.recorder import calcular_fps_gravacao


def test_fps_real_menor_que_alvo_e_respeitado():
    # 19 amostras/s durante 10 s -> o vídeo deve ser gravado a ~19 fps,
    # não a 30 (senão tocaria acelerado).
    tempos = [i / 19 for i in range(190)]
    assert abs(calcular_fps_gravacao(tempos, 30) - 19) < 0.2


def test_fps_nunca_passa_do_alvo():
    tempos = [i / 40 for i in range(400)]  # jitter: 40 amostras/s medidas
    assert calcular_fps_gravacao(tempos, 30) == 30.0


def test_fps_com_poucos_frames_usa_alvo():
    assert calcular_fps_gravacao([], 30) == 30.0
    assert calcular_fps_gravacao([1.0], 30) == 30.0
    assert calcular_fps_gravacao([1.0, 1.0], 30) == 30.0


def test_url_rtsp_escapa_senha_com_caracteres_especiais():
    from src.config import _montar_rtsp

    url = _montar_rtsp("admin", "p@ss:w/rd#1", "10.0.0.5", "/cam")
    assert url == "rtsp://admin:p%40ss%3Aw%2Frd%231@10.0.0.5:554/cam"


def test_limpeza_so_apaga_videos_antigos_do_sistema(tmp_path, monkeypatch):
    import logging
    from src import config, limpeza

    monkeypatch.setattr(config, "PASTA_VIDEOS", str(tmp_path))
    monkeypatch.setattr(config, "RETENCAO_DIAS", 2)

    antigo = time.time() - 5 * 86400
    arquivos = {
        "video_20200101_000000_cam1.mp4": antigo,   # apagar
        "video_novo_cam1.mp4": time.time(),         # manter (recente)
        "importante.py": antigo,                    # manter (não é vídeo do sistema)
        "notas.txt": antigo,                        # manter
    }
    for nome, mtime in arquivos.items():
        caminho = tmp_path / nome
        caminho.write_text("x")
        os.utime(caminho, (mtime, mtime))

    limpeza.limpar_videos_antigos(logging.getLogger("teste"))

    restantes = sorted(p.name for p in tmp_path.iterdir())
    assert restantes == ["importante.py", "notas.txt", "video_novo_cam1.mp4"]
