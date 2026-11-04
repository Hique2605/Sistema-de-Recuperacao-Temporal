"""
Leitura de botão físico via GPIO (Raspberry Pi).

Usa gpiozero, que já cuida de debounce (via `bounce_time`) — não
precisa implementar isso na mão. Não precisa de resistor externo: o
Raspberry Pi tem resistor interno, escolhido por GPIO_PULL_UP no .env.

Ligação física (padrão, GPIO_PULL_UP=false -> pull-down interno):
    GPIO <pino> ---- botão ---- 3,3 V

Ligação alternativa (GPIO_PULL_UP=true -> pull-up interno):
    GPIO <pino> ---- botão ---- GND

ATENÇÃO: o modo do código e a ligação do botão precisam combinar; se
estiverem trocados o botão não responde (ou parece sempre apertado).

Se a lib não estiver instalada (ex: rodando em notebook/dev sem Pi),
o sistema apenas loga um aviso e continua funcionando normalmente
via teclado — não quebra o programa.
"""


from . import config


def iniciar_botoes(pino_salvar, pino_encerrar, salvar_evento, encerrar_callback, logger):
    from gpiozero import Button  # import tardio: só é necessário se houver pino configurado

    def ao_pressionar_salvar():
        if salvar_evento.is_set():
            logger.info("Já existe uma solicitação de gravação pendente.")
        else:
            logger.info("Botão físico de salvar pressionado (GPIO %s).", pino_salvar)
            salvar_evento.set()

    botao_salvar = Button(pino_salvar, bounce_time=0.2, pull_up=config.GPIO_PULL_UP)
    botao_salvar.when_pressed = ao_pressionar_salvar

    botao_encerrar = None

    # Opcional: só é criado se GPIO_ENCERRAR_PIN estiver no .env.
    if pino_encerrar is not None:
        def ao_pressionar_encerrar():
            logger.info("Botão físico de encerrar pressionado (GPIO %s).", pino_encerrar)
            encerrar_callback()

        # hold_time exige segurar um pouco o botão antes de disparar,
        # pra evitar encerrar o sistema com um toque acidental.
        botao_encerrar = Button(pino_encerrar, bounce_time=0.2, pull_up=config.GPIO_PULL_UP, hold_time=1.5)
        botao_encerrar.when_held = ao_pressionar_encerrar

    # Mantém referência viva (gpiozero depende do objeto Button não
    # ser coletado pelo garbage collector enquanto escuta eventos).
    return botao_salvar, botao_encerrar
