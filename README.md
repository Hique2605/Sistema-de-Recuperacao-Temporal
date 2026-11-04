# Sistema de Recuperação Temporal de Vídeo com Buffer Circular

**Guia de instalação, configuração, execução e manutenção — Raspberry Pi 4 Model B**

## 1. Visão geral

Este projeto implementa um sistema embarcado de captura contínua de vídeo de câmeras IP por RTSP. Os quadros recentes são mantidos em **buffers circulares independentes por câmera**. Ao pressionar a tecla `S` ou um botão físico conectado ao Raspberry Pi, o programa salva em MP4 o trecho **anterior ao acionamento**, sem precisar manter uma gravação permanente de todos os vídeos no disco.

O sistema oferece captura em threads, reconexão RTSP, compressão JPEG em memória, gravação MP4 em segundo plano, métricas em CSV, logs, retenção automática de arquivos e envio opcional por SMTP. É possível configurar uma câmera ou várias câmeras (até nove entradas previstas no código).

> **Importante:** `FPS` é a taxa-alvo de amostragem do software, não uma garantia de FPS efetivo. O tempo de vídeo recuperado depende da taxa real, da disponibilidade dos quadros e da capacidade do buffer. Os arquivos são salvos localmente mesmo que o envio por e-mail falhe.

## 2. Tecnologias utilizadas

| Tecnologia / biblioteca | Aplicação |
|---|---|
| Raspberry Pi 4 Model B | Plataforma de execução embarcada |
| Raspberry Pi OS Lite 64-bit / Linux | Sistema operacional headless |
| Python 3 | Implementação principal (versão utilizada no protótipo: 3.13) |
| OpenCV (`opencv-python`) | Recepção/decodificação RTSP, JPEG e escrita MP4 |
| FFmpeg | Infraestrutura multimídia e diagnóstico de streams |
| `psutil` | Coleta de CPU e memória |
| `python-dotenv` | Carregamento das configurações do `.env` |
| `gpiozero` | Acionamento por botão físico GPIO |
| `RPi.GPIO` / `lgpio` | Backends possíveis do GPIO, conforme versão do sistema |
| `pytest` | Testes automatizados |
| `threading`, `collections.deque`, `time` | Concorrência, buffer circular e temporização |
| `csv`, `logging`, `smtplib`, `email`, `ssl` | Métricas, logs e envio SMTP |
| `systemd` | Inicialização automática e supervisão do serviço |

As bibliotecas da última linha e `threading`, `collections`, `time` fazem parte da biblioteca padrão do Python. **Não precisam ser instaladas separadamente.** O projeto já possui `requirements.txt` e `requirements-rpi.txt`.

## 3. Materiais e pré-requisitos

- Raspberry Pi 4 Model B, fonte adequada (recomendado 5 V / 3 A), cartão microSD (64 GB no protótipo) e rede local.
- Raspberry Pi OS Lite 64-bit instalado, usuário Linux criado e acesso por terminal ou SSH.
- Uma ou duas câmeras IP com RTSP habilitado; o protótipo utilizou câmeras Intelbras. Outras câmeras são possíveis se o caminho RTSP for compatível.
- IP, usuário e senha de cada câmera, com conectividade de rede e acesso à porta RTSP (normalmente TCP 554).
- **Opcional:** botoeira de contato normalmente aberto e fios para GPIO 17 (BCM) e 3,3 V.
- **Opcional:** conta de e-mail com SMTP e senha de aplicativo, se o provedor exigir.

**Atenção elétrica:** use **somente 3,3 V** no GPIO; nunca conecte 5 V diretamente aos pinos GPIO. Desligue a alimentação antes de montar o circuito.

## 4. Preparar o Raspberry Pi

Instale o Raspberry Pi OS Lite 64-bit com o Raspberry Pi Imager, configure usuário, rede e SSH. Conecte por terminal ou, de outro computador:

```bash
ssh SEU_USUARIO@IP_DO_RASPBERRY
```

Atualize o sistema e instale os pacotes:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip python3-dev \
  ffmpeg libglib2.0-0 libgl1 git unzip libcamera-tools
```

Para uso do GPIO em Raspberry Pi OS recente, instale também:

```bash
sudo apt install -y python3-gpiozero python3-lgpio
```

Confira:

```bash
python3 --version
ffmpeg -version
hostname -I
```

> O pacote `libcamera-tools` é auxiliar e não é necessário para câmeras IP RTSP. Em instalações Lite, algumas dependências de vídeo podem variar; `ffmpeg`, `libglib2.0-0` e `libgl1` são suficientes como ponto de partida para o OpenCV usado neste repositório.

## 5. Colocar o projeto no Raspberry Pi

### Opção A — transferir o ZIP

No computador, copie o ZIP para o Raspberry Pi:

```bash
scp "ARQUIVO_DO_PROJETO.zip" SEU_USUARIO@IP_DO_RASPBERRY:~/
```

No Raspberry Pi:

```bash
cd ~
unzip "ARQUIVO_DO_PROJETO.zip"
cd Sistema-de-Recuperacao-Temporal-de-Video-com-Buffer-Circular-feat-camerasprod
```

Substitua `ARQUIVO_DO_PROJETO.zip` pelo nome real do arquivo. O ZIP fornecido contém a pasta `Sistema-de-Recuperacao-Temporal-de-Video-com-Buffer-Circular-feat-camerasprod/`.

### Opção B — clonar o repositório

```bash
git clone URL_DO_SEU_REPOSITORIO.git camerasprod
cd camerasprod
```

O endereço do repositório deve ser preenchido pelo responsável pelo projeto.

**Todos os comandos seguintes devem ser executados na raiz do projeto**, onde estão `requirements.txt` e `src/`.

## 6. Criar o ambiente virtual e instalar bibliotecas

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

O uso de `--system-site-packages` permite aproveitar `python3-lgpio` e `python3-gpiozero` instalados pelo APT. Para GPIO, instale o `gpiozero` caso não esteja disponível:

```bash
python -c "import gpiozero; print('gpiozero OK')"
```

O arquivo `requirements-rpi.txt` também declara `RPi.GPIO` para ARM. **Em Raspberry Pi OS recente, prefira `lgpio` via APT**; não é obrigatório instalar `RPi.GPIO` quando `gpiozero` já opera corretamente com `lgpio`. Em sistemas antigos compatíveis, pode-se usar `python -m pip install -r requirements-rpi.txt`, mas o backend `RPi.GPIO` pode não funcionar em todos os modelos/versões.

Confira os imports principais:

```bash
python -c "import cv2, psutil, dotenv; print('Dependências principais OK:', cv2.__version__)"
python -c "import gpiozero, lgpio; print('GPIO OK')"
```

Se a segunda linha falhar, confira a instalação dos pacotes APT e a criação do venv com `--system-site-packages`. Sem botão físico, essa linha não é necessária.

## 7. Configurar o arquivo `.env`

```bash
cp .env.example .env
nano .env
```

Exemplo para **uma câmera**, botão GPIO 17 e gravação de 30 segundos:

```dotenv
CAMERA_IP=192.168.3.254
CAMERA_USUARIO=admin
CAMERA_SENHA=SUBSTITUA_PELA_SENHA_REAL
CAMERA_RTSP_PATH=/cam/realmonitor?channel=1&subtype=1

BUFFER_SECONDS=30
FPS=20
FRAME_WIDTH=1280
FRAME_HEIGHT=720
BUFFER_JPEG_QUALIDADE=80
CAPTURE_BUFFERSIZE=1
TIMEOUT_PRIMEIRO_FRAME_S=10
RECONEXAO_APOS_FALHAS=100

INTERVALO_AMOSTRAGEM_METRICAS=1.0
PASTA_VIDEOS=gravacoes
PASTA_METRICAS=metricas
PASTA_LOGS=logs
RETENCAO_DIAS=2

GPIO_SALVAR_PIN=17
GPIO_ENCERRAR_PIN=
GPIO_PULL_UP=false

EMAIL_ATIVADO=false
EMAIL_TAMANHO_MAX_MB=18
```

**Esses IPs e credenciais são exemplos.** Substitua pelos dados reais. O caminho `/cam/realmonitor?...` é típico de Intelbras/Dahua, mas pode variar por fabricante. `subtype=0` costuma indicar o stream principal e `subtype=1`, o secundário; configure a câmera para transmitir a resolução/FPS pretendidos.

Para **duas câmeras**, acrescente ao mesmo `.env`:

```dotenv
CAMERA2_IP=192.168.3.253
CAMERA2_USUARIO=admin
CAMERA2_SENHA=SUBSTITUA_PELA_SENHA_REAL
CAMERA2_RTSP_PATH=/cam/realmonitor?channel=1&subtype=1
```

A câmera 2 pode herdar usuário e senha da câmera 1 se os campos não forem definidos. Para desativar a câmera 2, remova ou comente `CAMERA2_IP`. O software suporta entradas `CAMERA2_` até `CAMERA9_`, conforme disponibilidade de hardware e desempenho.

**Como dimensionar o buffer:** `BUFFER_SECONDS × FPS` determina o máximo de quadros por câmera. Por exemplo, 30 × 20 = 600 quadros. Se a câmera entregar menos quadros novos que o alvo, a duração/qualidade temporal do vídeo pode ser afetada. `BUFFER_JPEG_QUALIDADE=80` reduz o uso de RAM; `0` desliga a compressão e pode consumir vários GB.

## 8. Verificar a conexão das câmeras

Teste se a câmera responde:

```bash
ping -c 4 192.168.3.254
```

Teste a porta RTSP (substitua o IP):

```bash
timeout 3 bash -c 'echo > /dev/tcp/192.168.3.254/554' && echo 'Porta RTSP acessível'
```

Teste o stream com FFmpeg, ajustando usuário, senha e caminho:

```bash
ffprobe -rtsp_transport tcp \
  'rtsp://admin:SENHA@192.168.3.254:554/cam/realmonitor?channel=1&subtype=1'
```

Se a senha contiver caracteres especiais, evite inseri-la diretamente na URL sem codificação. O programa principal faz a codificação da senha automaticamente. A câmera e o Raspberry Pi precisam estar em redes roteáveis entre si; se não estiverem, ajuste a rede antes de iniciar o software.

## 9. Executar manualmente

Na raiz do projeto:

```bash
source venv/bin/activate
python -m src.main
```

Aguarde a conexão RTSP e o preenchimento do buffer. Com o terminal interativo aberto:

| Controle | Ação |
|---|---|
| `S` | Salvar o trecho anterior de todas as câmeras conectadas |
| `Q` | Encerrar a aplicação |
| `Ctrl+C` | Solicitar encerramento seguro |
| Botão GPIO | Executar a mesma ação da tecla `S` |

O salvamento do MP4 acontece em segundo plano. Uma nova solicitação enquanto a gravação anterior ainda estiver em andamento pode ser ignorada. Em execução via `systemd`, as teclas `S`/`Q` não ficam disponíveis; use o botão físico e os comandos de serviço.

### Teste sem câmera física

O repositório inclui `demo.py` com câmera simulada:

```bash
python demo.py
```

Essa demonstração gera um evento automático e arquivos de saída. Também é possível executar os testes:

```bash
python -m pytest tests/ -v
```

**Nota:** `demo.py` utiliza uma interface própria de simulação; caso ocorra erro de assinatura de função por divergência entre os módulos, a demonstração precisará ser ajustada. Isso não impede o uso do comando principal `python -m src.main`.

## 10. Montar e testar o botão físico

Com o Raspberry Pi desligado, conecte uma extremidade do botão ao **GPIO 17 (BCM, pino físico 11)** e a outra ao **3,3 V (pino físico 1)**. No `.env`:

```dotenv
GPIO_SALVAR_PIN=17
GPIO_PULL_UP=false
```

Esse modo usa o resistor pull-down interno. Para ligar o botão entre GPIO e GND, configure `GPIO_PULL_UP=true` e adapte a fiação. Não conecte tensão de 5 V aos GPIOs.

Verifique os pinos disponíveis:

```bash
pinout
```

Teste isolado (encerre com `Ctrl+C`):

```bash
source venv/bin/activate
python botao.py
```

O teste deve mostrar `Botão apertado!` a cada acionamento. Depois execute `python -m src.main` e pressione o botão para salvar os vídeos. O arquivo `botao.py` utiliza GPIO 17 fixo, independentemente do `.env`.

Se houver erro de GPIO no sistema recente, confira:

```bash
sudo apt install -y python3-lgpio python3-gpiozero
python -c "import lgpio, gpiozero; print('GPIO disponível')"
```

Pode-se testar o backend explicitamente com `GPIOZERO_PIN_FACTORY=lgpio python botao.py`. Não use `sudo pip install` no Python global.

## 11. Configurar envio opcional por e-mail

O envio é opcional: com `EMAIL_ATIVADO=false`, o sistema salva os MP4 normalmente. Para SMTP Gmail, configure no `.env`:

```dotenv
EMAIL_ATIVADO=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USUARIO=seuemail@gmail.com
SMTP_SENHA=SENHA_DE_APLICATIVO
EMAIL_REMETENTE=seuemail@gmail.com
EMAIL_DESTINATARIO=destinatario@gmail.com
EMAIL_TAMANHO_MAX_MB=18
```

No Gmail, pode ser necessário ativar a verificação em duas etapas e gerar uma **senha de aplicativo**, quando essa opção estiver disponível para a conta. Não use a senha normal da conta e nunca divulgue o `.env`.

O código agrupa vídeos conforme o tamanho total dos anexos: uma câmera normalmente resulta em um vídeo por e-mail; com duas câmeras, elas podem seguir juntas **se couberem no limite**, ou em e-mails separados. Se um arquivo for maior que o limite, o e-mail poderá apenas informar o caminho do vídeo no disco. Falhas SMTP não removem o vídeo local.

## 12. Iniciar automaticamente com `systemd`

Primeiro confirme que a execução manual funciona. Em seguida, na raiz do projeto, obtenha o caminho absoluto:

```bash
pwd
whoami
```

Neste exemplo, vamos considerar `/home/hique/camerasprod` e usuário `hique`. **Substitua ambos pelos valores do seu Raspberry Pi.** Se o projeto foi extraído com o nome longo, use esse caminho real ou renomeie a pasta:

```bash
cd ~
mv Sistema-de-Recuperacao-Temporal-de-Video-com-Buffer-Circular-feat-camerasprod camerasprod
cd ~/camerasprod
chmod +x esperar_cameras.sh
```

Crie o serviço:

```bash
sudo nano /etc/systemd/system/cameras.service
```

Conteúdo:

```ini
[Unit]
Description=Sistema de Recuperacao Temporal de Video
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=hique
WorkingDirectory=/home/hique/camerasprod
Environment=PYTHONUNBUFFERED=1
Environment=GPIOZERO_PIN_FACTORY=lgpio
ExecStartPre=/home/hique/camerasprod/esperar_cameras.sh 90
ExecStart=/home/hique/camerasprod/venv/bin/python -u -m src.main
Restart=always
RestartSec=5
TimeoutStopSec=650

[Install]
WantedBy=multi-user.target
```

O script `esperar_cameras.sh` testa a porta TCP 554 das câmeras antes da inicialização. Ele **não impede** a execução se alguma câmera estiver indisponível após o tempo-limite; a aplicação tentará conectar e pode iniciar com apenas as câmeras acessíveis. `TimeoutStopSec=650` dá tempo para a finalização de uma gravação pendente.

Ative e execute:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cameras.service
sudo systemctl start cameras.service
sudo systemctl status cameras.service
```

Comandos úteis:

```bash
sudo systemctl restart cameras.service  # Reiniciar
sudo systemctl stop cameras.service     # Parar
sudo systemctl start cameras.service    # Iniciar
sudo systemctl disable cameras.service  # Desativar no boot
journalctl -u cameras.service -f        # Acompanhar logs
journalctl -u cameras.service -n 100 --no-pager
```

Para testar a inicialização automática:

```bash
sudo reboot
```

Após reconectar via SSH:

```bash
systemctl status cameras.service
```

> Se o usuário não tiver permissão para acessar o GPIO, confira os grupos e permissões do dispositivo. Não rode o serviço como root sem necessidade. Ajuste o `Environment=GPIOZERO_PIN_FACTORY=lgpio` caso utilize outro backend compatível.

## 13. Estrutura do projeto

```text
projeto/
├── .env.example             # Modelo das variáveis de ambiente
├── requirements.txt         # Dependências gerais
├── requirements-rpi.txt     # Dependências opcionais de GPIO
├── esperar_cameras.sh       # Aguarda disponibilidade da porta RTSP
├── botao.py                 # Teste isolado do botão físico
├── demo.py                  # Demonstração com câmera simulada
├── src/
│   ├── main.py              # Orquestração e captura/amostragem
│   ├── config.py            # Configurações e câmeras
│   ├── camera.py            # Captura RTSP
│   ├── camera_fake.py       # Câmera simulada
│   ├── buffer.py            # Buffer circular
│   ├── recorder.py          # Escrita de MP4 e eventos
│   ├── metrics.py           # Coleta de métricas
│   ├── gpio_control.py      # Acionamento GPIO
│   ├── keyboard_control.py  # Comandos S e Q
│   ├── email_sender.py      # Envio SMTP
│   ├── limpeza.py           # Retenção dos vídeos
│   └── logger_config.py     # Logs
├── tests/                   # Testes automatizados
├── gravacoes/               # Arquivos MP4
├── metricas/                # Arquivos CSV
└── logs/                    # Logs de execução
```

As pastas de saída são criadas automaticamente se não existirem.

## 14. Saídas e métricas

| Caminho | Conteúdo |
|---|---|
| `gravacoes/video_YYYYMMDD_HHMMSS_cam1.mp4` | Vídeo da câmera 1 |
| `gravacoes/video_YYYYMMDD_HHMMSS_cam2.mp4` | Vídeo da câmera 2 |
| `metricas/sistema_*.csv` | CPU, RAM, FPS real, preenchimento dos buffers |
| `metricas/eventos_*.csv` | Evento, câmera, nome do vídeo, quadros, duração, latência, quadros repetidos/perdidos estimados e FPS de gravação |
| `logs/execucao_*.log` | Mensagens e erros do sistema |

A coleta de métricas ocorre periodicamente, conforme `INTERVALO_AMOSTRAGEM_METRICAS`; **não depende de apertar o botão**. O CSV de eventos recebe registros quando vídeos são gravados. A latência de gravação representa o tempo gasto para produzir o arquivo, e não a latência de transmissão RTSP.

Confira os arquivos:

```bash
ls -lh gravacoes/
ls -lh metricas/
ls -lh logs/
tail -n 10 metricas/sistema_*.csv
```

Para visualizar o espaço disponível:

```bash
df -h
du -sh gravacoes metricas logs
```

A retenção `RETENCAO_DIAS` remove vídeos antigos com base na idade dos arquivos, durante o fluxo de salvamento. **Não é um agendador independente de limpeza**: sem novos salvamentos, não há garantia de que a limpeza seja executada.

## 15. Atualizar, copiar e manter o sistema

Copiar uma pasta do Raspberry Pi para o computador (executar no computador):

```bash
scp -r SEU_USUARIO@IP_DO_RASPBERRY:~/camerasprod ./camerasprod
```

Atualizar o código de um clone Git:

```bash
cd ~/camerasprod
sudo systemctl stop cameras.service
git pull
source venv/bin/activate
python -m pip install -r requirements.txt
sudo systemctl start cameras.service
```

Atenção: um ZIP extraído não é necessariamente um repositório Git, portanto `git pull` só funciona em clones. Faça backup do `.env`, dos vídeos e das métricas antes de atualizar ou substituir arquivos.

**Limpeza manual (irreversível):** antes de apagar, confira a pasta com `pwd` e `ls`. Para remover somente MP4 da pasta de gravações:

```bash
find gravacoes -maxdepth 1 -type f -name 'video_*.mp4' -delete
```

Não execute esse comando se desejar preservar os vídeos do experimento.

## 16. Problemas comuns

| Problema | Verificações |
|---|---|
| Nenhuma câmera conecta | IP, rota de rede, porta 554, credenciais e caminho RTSP; testar com `ffprobe` |
| Câmera conectada, mas sem quadros | Codec/stream, substream, resolução, bitrate, `TIMEOUT_PRIMEIRO_FRAME_S` |
| FPS real abaixo do alvo | CPU, qualidade/rede RTSP, FPS de origem, número de câmeras; reduzir FPS/resolução e usar substream |
| Uso excessivo de RAM | Manter `BUFFER_JPEG_QUALIDADE` maior que zero; reduzir resolução/FPS |
| Botão não responde | GPIO 17 BCM, fiação 3,3 V, `GPIO_PULL_UP`, `gpiozero` e backend `lgpio` |
| `ModuleNotFoundError` | Ativar `venv` e reinstalar dependências |
| E-mail não chega | `EMAIL_ATIVADO`, SMTP, porta, senha de aplicativo, tamanho dos anexos e logs |
| Serviço não inicia | `systemctl status`, `journalctl`, `WorkingDirectory`, usuário e caminhos absolutos |
| MP4 não aparece imediatamente | Gravação ocorre em segundo plano; aguardar conclusão no log |
| Vídeo tem menos que 30 s | Aguardar buffer preencher; verificar FPS real, quedas RTSP e quadros disponíveis |

## 17. Checklist de reprodução

- [ ] Raspberry Pi OS instalado e SSH funcionando.
- [ ] Câmeras IP ligadas e acessíveis por RTSP.
- [ ] Pacotes APT e ambiente virtual configurados.
- [ ] Dependências Python instaladas.
- [ ] `.env` preenchido com IP, usuário e senha corretos.
- [ ] `python -m src.main` inicia e recebe quadros.
- [ ] Tecla `S` produz MP4 na pasta `gravacoes/`.
- [ ] Arquivos CSV aparecem em `metricas/`.
- [ ] Botão físico testado, se utilizado.
- [ ] SMTP testado, se utilizado.
- [ ] `cameras.service` ativado e validado após reinicialização, se desejado.

## 18. Observações de segurança e reprodutibilidade

- **Não envie senhas reais no ZIP.** O arquivo `.env` contém credenciais; envie apenas `.env.example` e instrua cada pessoa a criar seu próprio `.env`.
- O `.gitignore` fornecido ignora `venv/` e `logs/`, mas **não inclui `.env`, `gravacoes/` nem `metricas/`**. Antes de publicar o repositório, acrescente essas entradas ao `.gitignore` se os arquivos forem privados. Arquivos já versionados precisam ser retirados do índice separadamente.
- O ZIP analisado contém gravações e métricas de experimentos. Confira se esses dados podem ser compartilhados antes de encaminhar.
- Não exponha a porta RTSP ou o SSH diretamente à internet sem medidas de segurança apropriadas.
- Os valores de FPS e consumo de recursos variam conforme a câmera, o codec, a rede e a configuração do Raspberry Pi. O guia descreve a instalação e a operação do código fornecido, não garante desempenho idêntico em outros equipamentos.

---

**Execução rápida, depois de configurar o `.env`:**

```bash
cd ~/camerasprod
source venv/bin/activate
python -m src.main
```

Pressione **S** para salvar o trecho anterior, ou use o botão físico configurado no GPIO 17.
