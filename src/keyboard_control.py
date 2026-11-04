"""
Leitura do teclado diretamente pelo terminal (sem interface gráfica).

S = solicita salvar os últimos N segundos
Q = encerra o sistema
"""

import os
import select
import sys
import termios
import tty


def ler_teclado(parar_evento, salvar_evento, encerrar_callback, logger):
    if not sys.stdin.isatty():
        logger.warning("Entrada do terminal não está disponível.")
        return

    fd = sys.stdin.fileno()
    configuracao_original = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        while not parar_evento.is_set():
            # select com timeout (em vez de os.read bloqueante): assim a
            # thread percebe o parar_evento (Ctrl+C / SIGTERM) e o finally
            # restaura o terminal. Com leitura bloqueante o terminal
            # ficava sem eco após encerrar.
            pronto, _, _ = select.select([fd], [], [], 0.2)
            if not pronto:
                continue

            tecla = os.read(fd, 1).decode(errors="ignore").lower()

            if tecla == "s":
                if salvar_evento.is_set():
                    logger.info("Já existe uma solicitação de gravação pendente.")
                else:
                    logger.info("Tecla S pressionada — solicitando gravação.")
                    salvar_evento.set()

            elif tecla == "q":
                logger.info("Tecla Q pressionada — encerrando.")
                encerrar_callback()
                break

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, configuracao_original)
