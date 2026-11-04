"""
Envio automático dos vídeos gravados por e-mail (SMTP).

PLANEJAMENTO PELO TAMANHO (antes de enviar)
-------------------------------------------
Os tamanhos dos .mp4 são lidos do disco e o envio é planejado assim:

  * tudo cabe em EMAIL_TAMANHO_MAX_MB  -> UM e-mail com todos os vídeos;
  * não cabe tudo junto                -> vários e-mails, cada um com o que
                                          couber (no limite, um vídeo por
                                          e-mail, ex.: 2 câmeras = 2 e-mails);
  * um vídeo sozinho já passa do limite -> não é anexado; o e-mail só avisa
                                          onde ele ficou salvo no disco.

EMAIL_TAMANHO_MAX_MB vale POR E-MAIL (soma dos anexos dele). Anexos viajam
em base64 (+33%), então 18 MB viram ~24 MB, abaixo dos 25 MB do Gmail.

TENTATIVAS
----------
Cada e-mail é tentado até 3 vezes (espera de 5 s e 15 s entre elas) em
caso de queda de conexão/timeout. Login recusado ou recusa definitiva do
servidor (5xx) não são repetidos, pois não adianta.

Qualquer erro aqui é só logado como warning — não derruba a gravação
nem o sistema. Os vídeos já estão salvos em disco antes desta função
ser chamada; o e-mail é só um "extra".
"""

import os
import smtplib
import ssl
import time
from email.message import EmailMessage

from . import config

TENTATIVAS = 3
ESPERAS_ENTRE_TENTATIVAS = (5, 15)  # segundos, antes da 2ª e da 3ª tentativa

# Limite real de uma mensagem no Gmail (já contando o base64).
LIMITE_MENSAGEM_MB = 25.0


def _timeout_s():
    # Tempo máximo para enviar os dados de UM e-mail (conexão lenta + anexo
    # grande estouravam os 60 s antigos). Configurável: EMAIL_TIMEOUT_S.
    return getattr(config, "EMAIL_TIMEOUT_S", 180)


def planejar_emails(caminhos_arquivos, logger, limite_mb=None):
    """
    Lê o tamanho de cada vídeo e agrupa em e-mails.

    Retorna (grupos, sem_anexo):
      grupos:    lista de listas [(caminho, nome, tamanho_mb), ...]; cada
                 lista vira um e-mail, e a soma dela respeita o limite.
      sem_anexo: [(caminho, nome, tamanho_mb)] — vídeos grandes demais
                 para anexar mesmo sozinhos.
    """
    limite = config.EMAIL_TAMANHO_MAX_MB if limite_mb is None else limite_mb
    itens = []

    for caminho in caminhos_arquivos:
        nome = os.path.basename(caminho)
        try:
            tamanho_mb = os.path.getsize(caminho) / (1024 * 1024)
        except OSError as erro:
            logger.warning("Não foi possível ler o arquivo %s para enviar por e-mail: %s", nome, erro)
            continue
        itens.append((caminho, nome, tamanho_mb))

    logger.info(
        "E-mail: tamanhos dos vídeos -> %s | limite por e-mail: %sMB",
        ", ".join(f"{n} {mb:.1f}MB" for _, n, mb in itens) or "(nenhum)",
        limite,
    )

    grupos, sem_anexo = [], []
    atual, total_atual = [], 0.0

    for item in itens:
        mb = item[2]

        if mb > limite:
            sem_anexo.append(item)
            logger.warning("Vídeo %s tem %.1fMB e passa do limite de %sMB sozinho — vai sem anexo.", item[1], mb, limite)
            continue

        if atual and total_atual + mb > limite:
            grupos.append(atual)
            atual, total_atual = [], 0.0

        atual.append(item)
        total_atual += mb

    if atual:
        grupos.append(atual)

    return grupos, sem_anexo


def montar_mensagem(anexar, sem_anexo, timestamp_evento, indice, total, logger):
    """
    Monta UM EmailMessage (sem enviar). Separado do envio para poder ser
    testado sem servidor SMTP.

    anexar:    [(caminho, nome, mb)] que vão em anexo neste e-mail
    sem_anexo: [(caminho, nome, mb)] só citados no texto
    indice/total: posição deste e-mail ("2/3"), só para o assunto.
    """
    if not anexar and not sem_anexo:
        return None

    qtd = len(anexar) + len(sem_anexo)
    parte = f" [{indice}/{total}]" if total > 1 else ""

    msg = EmailMessage()
    msg["Subject"] = f"Sistema de Gravação - {qtd} vídeo(s) salvo(s) ({timestamp_evento}){parte}"
    msg["From"] = config.EMAIL_REMETENTE
    msg["To"] = config.EMAIL_DESTINATARIO

    linhas = [f"Vídeos gravados em {timestamp_evento}." + (f" E-mail {indice} de {total}." if total > 1 else ""), ""]

    for _, nome, mb in anexar:
        linhas.append(f"- {nome} ({mb:.1f} MB) — em anexo")

    for caminho, nome, mb in sem_anexo:
        linhas.append(f"- {nome} ({mb:.1f} MB) — NÃO anexado (maior que {config.EMAIL_TAMANHO_MAX_MB}MB). Salvo em: {caminho}")

    msg.set_content("\n".join(linhas))

    for caminho, nome, _ in anexar:
        try:
            with open(caminho, "rb") as f:
                msg.add_attachment(f.read(), maintype="video", subtype="mp4", filename=nome)
        except OSError as erro:
            logger.warning("Não foi possível anexar %s ao e-mail: %s", nome, erro)

    return msg


def _enviar(msg):
    # Contexto padrão: valida o certificado do servidor.
    contexto = ssl.create_default_context()
    timeout = _timeout_s()

    if config.SMTP_PORT == 465:  # SSL direto
        servidor = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=timeout, context=contexto)
    else:  # 587: STARTTLS
        servidor = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=timeout)

    with servidor:
        if config.SMTP_PORT != 465:
            servidor.starttls(context=contexto)
        servidor.login(config.SMTP_USUARIO, config.SMTP_SENHA)
        servidor.send_message(msg)


def _enviar_com_tentativas(msg, rotulo, logger):
    """Tenta enviar até TENTATIVAS vezes. Retorna True se enviou."""
    tamanho_mb = len(bytes(msg)) / (1024 * 1024)

    if tamanho_mb > LIMITE_MENSAGEM_MB:
        logger.warning("E-mail %s tem %.1fMB (já com base64) e passa dos %.0fMB do Gmail — não enviado.",
                       rotulo, tamanho_mb, LIMITE_MENSAGEM_MB)
        return False

    for tentativa in range(1, TENTATIVAS + 1):
        logger.info("Enviando e-mail %s (%.1fMB) — tentativa %s/%s...", rotulo, tamanho_mb, tentativa, TENTATIVAS)

        try:
            _enviar(msg)
            logger.info("E-mail %s enviado para %s.", rotulo, config.EMAIL_DESTINATARIO)
            return True
        except smtplib.SMTPAuthenticationError as erro:
            logger.warning("E-mail %s não enviado: login recusado (use a SENHA DE APP do Gmail). %s", rotulo, erro)
            return False
        except smtplib.SMTPResponseException as erro:
            if erro.smtp_code >= 500:  # recusa definitiva (ex.: anexo grande demais)
                logger.warning("E-mail %s recusado pelo servidor (%s): %s", rotulo, erro.smtp_code, erro.smtp_error)
                return False
            falha = erro
        except (smtplib.SMTPException, OSError) as erro:  # queda de conexão, timeout, DNS...
            falha = erro

        if tentativa == TENTATIVAS:
            logger.warning("Falha ao enviar e-mail %s após %s tentativas: %s", rotulo, TENTATIVAS, falha)
            return False

        espera = ESPERAS_ENTRE_TENTATIVAS[tentativa - 1]
        logger.warning("Falha no e-mail %s (tentativa %s/%s): %s — nova tentativa em %ss.",
                       rotulo, tentativa, TENTATIVAS, falha, espera)
        time.sleep(espera)

    return False


def enviar_email_videos(caminhos_arquivos, timestamp_evento, logger):
    if not config.EMAIL_ATIVADO:
        return

    grupos, sem_anexo = planejar_emails(caminhos_arquivos, logger)

    if not grupos and not sem_anexo:
        return

    # Vídeos grandes demais para anexar são citados no texto do 1º e-mail
    # (ou num e-mail só de aviso, se não houver nenhum anexável).
    if not grupos:
        envios = [([], sem_anexo)]
    else:
        envios = [(g, sem_anexo if i == 0 else []) for i, g in enumerate(grupos)]

    if len(envios) > 1:
        logger.info("Os vídeos não cabem num e-mail só: serão enviados %s e-mails separados.", len(envios))

    ok = 0
    for i, (anexar, avisos) in enumerate(envios, start=1):
        msg = montar_mensagem(anexar, avisos, timestamp_evento, i, len(envios), logger)
        if msg is None:
            continue
        if _enviar_com_tentativas(msg, f"{i}/{len(envios)}", logger):
            ok += 1

    if ok < len(envios):
        logger.warning("Evento %s: %s de %s e-mail(s) enviado(s). Os vídeos continuam salvos em %s/.",
                       timestamp_evento, ok, len(envios), config.PASTA_VIDEOS)
