"""Gera icone.ico (anel de cronômetro neon) só com a biblioteca padrão.

Uso:  python gerar_icone.py          (já vem gerado; rode só para mudar o desenho)
"""
import math
import struct
import zlib

import tema


def _rgb(hexa):
    return [int(hexa[i:i + 2], 16) for i in (1, 3, 5)]


def renderizar(n):
    fundo, neon, apagado = _rgb(tema.CARTAO), _rgb(tema.DESTAQUES["ciano"]), _rgb(tema.LINHA)
    linhas = []
    for y in range(n):
        linha = bytearray([0])
        for x in range(n):
            u, v = (x + .5) / n * 2 - 1, (y + .5) / n * 2 - 1
            # quadrado arredondado (distância assinada)
            qx, qy = abs(u) - 0.68, abs(v) - 0.68
            dist = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - 0.3
            alfa = max(0.0, min(1.0, 0.5 - dist * n / 2))
            r = math.hypot(u, v)
            anel = max(0.0, min(1.0, (0.11 - abs(r - 0.5)) * n / 2))
            brilho = math.exp(-((r - 0.5) / 0.2) ** 2) * 0.3
            ang = math.degrees(math.atan2(u, -v)) % 360
            cor_anel = apagado if 0 < ang < 70 else neon
            pix = [fundo[i] * (1 - anel) + cor_anel[i] * anel for i in range(3)]
            pix = [pix[i] * (1 - brilho) + cor_anel[i] * brilho for i in range(3)]
            linha += bytes([min(255, int(c)) for c in pix] + [int(alfa * 255)])
        linhas.append(bytes(linha))
    return b"".join(linhas)


def png(n):
    def bloco(tipo, dados):
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(renderizar(n), 9)) + bloco(b"IEND", b""))


def gerar(caminho="icone.ico", tamanhos=(256, 64, 48, 32, 16)):
    imagens = [png(n) for n in tamanhos]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    deslocamento = 6 + 16 * len(imagens)
    entradas = b""
    for n, dados in zip(tamanhos, imagens):
        entradas += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(dados), deslocamento)
        deslocamento += len(dados)
    with open(caminho, "wb") as f:
        f.write(cabecalho + entradas + b"".join(imagens))


if __name__ == "__main__":
    gerar()
