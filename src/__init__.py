"""
Pacote do sistema de gravação contínua com câmera IP.

Módulos:
    config            -- configurações centrais (lidas do .env)
    logger_config      -- configuração de logging (console + arquivo)
    camera            -- captura RTSP em thread dedicada (uma por câmera)
    buffer            -- buffer circular thread-safe (um por câmera)
    recorder          -- gravação de um vídeo por câmera + CSV de eventos
    metrics           -- monitoramento de CPU/RAM/FPS + CSV
    keyboard_control  -- leitura de teclado (S / Q)
    main              -- ponto de entrada / orquestração
"""

__version__ = "1.2.0"
