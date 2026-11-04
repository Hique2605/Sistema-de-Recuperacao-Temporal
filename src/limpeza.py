"""
Limpeza automática de vídeos antigos (retenção em disco/pen drive).

Chamada depois de cada gravação: varre PASTA_VIDEOS e apaga qualquer
vídeo mais antigo que RETENCAO_DIAS dias, evitando lotar o pen drive.

Usa a data de MODIFICAÇÃO do arquivo (os.path.getmtime), não o nome —
assim continua funcionando mesmo se o padrão de nome do vídeo mudar
no futuro.

Exemplo com RETENCAO_DIAS=2: hoje é dia 16/09 -> vídeos do dia 14/09
(e anteriores) são apagados; vídeos dos dias 15 e 16 são mantidos.
"""

import os
from datetime import datetime

from . import config


def limpar_videos_antigos(logger):
    try:
        arquivos = os.listdir(config.PASTA_VIDEOS)
    except FileNotFoundError:
        return

    agora = datetime.now()
    removidos = 0

    for nome_arquivo in arquivos:
        caminho = os.path.join(config.PASTA_VIDEOS, nome_arquivo)

        # Só mexe em vídeos gerados por este sistema (video_*.mp4). Sem
        # esse filtro, um PASTA_VIDEOS apontando para a pasta errada
        # apagaria qualquer arquivo com mais de RETENCAO_DIAS dias.
        if not (nome_arquivo.startswith("video_") and nome_arquivo.endswith(".mp4")):
            continue

        if not os.path.isfile(caminho):
            continue

        data_arquivo = datetime.fromtimestamp(os.path.getmtime(caminho))
        idade_dias = (agora.date() - data_arquivo.date()).days

        if idade_dias >= config.RETENCAO_DIAS:
            try:
                os.remove(caminho)
                removidos += 1
                logger.info(
                    "Vídeo antigo removido (retenção de %s dias, %s dia(s) de idade): %s",
                    config.RETENCAO_DIAS, idade_dias, nome_arquivo,
                )
            except OSError as erro:
                logger.warning("Não foi possível remover %s: %s", nome_arquivo, erro)

    if removidos:
        logger.info("Limpeza concluída: %s vídeo(s) antigo(s) removido(s).", removidos)
