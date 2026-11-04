"""
Configuração de logging do projeto.

Substitui os prints espalhados pelo código original por um logger
de verdade: grava em arquivo (para depois analisar no TCC) e mostra
no console ao mesmo tempo.
"""

import logging
import os
from datetime import datetime

from . import config


def configurar_logger(nome="sistema_gravacao"):
    logger = logging.getLogger(nome)

    if logger.handlers:
        # Evita duplicar handlers se a função for chamada mais de uma vez.
        return logger

    logger.setLevel(logging.INFO)

    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Console ---
    handler_console = logging.StreamHandler()
    handler_console.setFormatter(formato)
    logger.addHandler(handler_console)

    # --- Arquivo ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_log = os.path.join(config.PASTA_LOGS, f"execucao_{timestamp}.log")

    handler_arquivo = logging.FileHandler(caminho_log, encoding="utf-8")
    handler_arquivo.setFormatter(formato)
    logger.addHandler(handler_arquivo)

    return logger
