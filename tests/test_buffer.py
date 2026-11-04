"""
Teste unitário do buffer circular.

Rodar com:
    python -m pytest tests/
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.buffer import FrameBuffer


def test_buffer_respeita_tamanho_maximo():
    buffer = FrameBuffer(max_frames=3)

    for i in range(5):
        buffer.append(i)

    assert len(buffer) == 3
    assert buffer.snapshot() == [2, 3, 4]


def test_buffer_vazio_inicialmente():
    buffer = FrameBuffer(max_frames=10)
    assert len(buffer) == 0
    assert buffer.snapshot() == []


def test_snapshot_retorna_copia():
    buffer = FrameBuffer(max_frames=5)
    buffer.append("a")

    copia = buffer.snapshot()
    copia.append("b")

    assert buffer.snapshot() == ["a"]
