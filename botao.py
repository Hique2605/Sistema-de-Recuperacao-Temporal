from gpiozero import Button
from signal import pause

BOTAO_PIN = 17

botao = Button(BOTAO_PIN, pull_up=False)

def botao_apertado():
    print("Botão apertado!")

botao.when_pressed = botao_apertado

print("Aguardando botão...")

pause()
