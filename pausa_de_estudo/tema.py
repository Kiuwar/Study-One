"""Tema visual futurista: paleta, fontes e desenhos reutilizáveis em tk.Canvas."""

FUNDO = "#04060C"
CARTAO = "#0A111F"
LINHA = "#16233A"
TEXTO = "#E6F1FF"
TEXTO_SUAVE = "#7C8DA8"
VIOLETA = "#8B7CFF"
ROSA = "#FF5C8A"
TRANSPARENTE = "#FF00FF"     # cor-chave de -transparentcolor (cantos arredondados)

DESTAQUES = {
    "ciano": "#00E5FF",
    "violeta": "#A78BFA",
    "verde": "#39FF9C",
    "magenta": "#FF4DD2",
}

FONTE_TITULO = "Segoe UI Light"
FONTE_TEXTO = "Segoe UI"
FONTE_NUMERO = "Bahnschrift"
FONTE_MONO = "Consolas"


def cor_destaque(nome: str) -> str:
    return DESTAQUES.get(nome, DESTAQUES["ciano"])


def misturar(a: str, b: str, t: float) -> str:
    """Mistura duas cores #RRGGBB (t=0 -> a, t=1 -> b). Simula brilho/transparência."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def escala(altura: int, minimo=0.6, maximo=2.0) -> float:
    """Fator de escala da interface em relação a uma tela de 1080 px de altura."""
    return max(minimo, min(maximo, altura / 1080))


def fonte(familia: str, tamanho: float, k: float, estilo: str = ""):
    """Fonte em pixels (tamanho negativo no Tk), independente da escala do Windows."""
    base = (familia, -max(8, int(tamanho * k)))
    return base + (estilo,) if estilo else base


def retangulo_arredondado(canvas, x1, y1, x2, y2, r, **opcoes):
    r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    pontos = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pontos, smooth=True, **opcoes)


def desenhar_grade(canvas, largura, altura, passo, cor=None):
    """Grade sutil de fundo (desenhada uma única vez)."""
    cor = cor or misturar(FUNDO, LINHA, 0.45)
    for x in range(0, largura, passo):
        canvas.create_line(x, 0, x, altura, fill=cor)
    for y in range(0, altura, passo):
        canvas.create_line(0, y, largura, y, fill=cor)


def cartao_com_brilho(canvas, x1, y1, x2, y2, raio, destaque, camadas=5):
    """Cartão escuro com halo neon que esmaece para fora (efeito flutuante)."""
    for i in range(camadas, 0, -1):
        retangulo_arredondado(canvas, x1 - i * 3, y1 - i * 3, x2 + i * 3, y2 + i * 3,
                              raio + i * 3, fill="", outline=misturar(destaque, FUNDO, 0.55 + 0.09 * i),
                              width=1)
    retangulo_arredondado(canvas, x1, y1, x2, y2, raio, fill=CARTAO,
                          outline=misturar(destaque, CARTAO, 0.35), width=2)


def colchetes(canvas, x1, y1, x2, y2, tam, cor, largura=2):
    """Cantos estilo HUD nos quatro vértices."""
    for x, y, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        canvas.create_line(x, y + dy * tam, x, y, x + dx * tam, y, fill=cor, width=largura)


def icone(janela, cor: str) -> None:
    """Ícone da janela (anel de cronômetro neon), desenhado em código."""
    import math
    import tkinter as tk
    n = 64
    img = tk.PhotoImage(width=n, height=n)
    for y in range(n):
        linha = []
        for x in range(n):
            u, v = (x + .5) / n * 2 - 1, (y + .5) / n * 2 - 1
            a = max(0.0, min(1.0, (0.12 - abs(math.hypot(u, v) - 0.55)) / 0.04))
            ang = math.degrees(math.atan2(u, -v)) % 360
            linha.append(misturar(FUNDO, LINHA if 0 < ang < 70 else cor, a))
        img.put("{" + " ".join(linha) + "}", to=(0, y))
    janela.iconphoto(True, img)
    janela._icone = img          # evita coleta pelo GC


def formatar_tempo(segundos: int) -> str:
    segundos = max(0, int(segundos))
    return "%02d:%02d" % divmod(segundos, 60)


class BotaoNeon:
    """Botão em forma de pílula com halo e efeito de hover, desenhado no Canvas."""

    def __init__(self, canvas, cx, cy, largura, altura, texto, comando, cor,
                 preenchido=False, fonte_botao=None):
        self.canvas, self.comando, self.cor, self.preenchido = canvas, comando, cor, preenchido
        self.tag = "btn%d" % id(self)
        x1, y1, x2, y2 = cx - largura // 2, cy - altura // 2, cx + largura // 2, cy + altura // 2
        r = altura // 2
        self._halo = retangulo_arredondado(canvas, x1 - 3, y1 - 3, x2 + 3, y2 + 3, r + 3, fill="",
                                           outline=misturar(cor, FUNDO, 0.7), tags=self.tag)
        self._corpo = retangulo_arredondado(canvas, x1, y1, x2, y2, r, width=2, outline=cor,
                                            fill=cor if preenchido else CARTAO, tags=self.tag)
        self._texto = canvas.create_text(cx, cy, text=texto, tags=self.tag, font=fonte_botao,
                                         fill=FUNDO if preenchido else cor)
        canvas.tag_bind(self.tag, "<Enter>", self._entrar)
        canvas.tag_bind(self.tag, "<Leave>", self._sair)
        canvas.tag_bind(self.tag, "<ButtonRelease-1>", lambda _e: self.comando())

    def _entrar(self, _e):
        self.canvas.configure(cursor="hand2")
        self.canvas.itemconfigure(self._halo, outline=self.cor)
        self.canvas.itemconfigure(
            self._corpo, fill=misturar(self.cor, TEXTO, 0.35) if self.preenchido
            else misturar(self.cor, CARTAO, 0.82))

    def _sair(self, _e):
        self.canvas.configure(cursor="")
        self.canvas.itemconfigure(self._halo, outline=misturar(self.cor, FUNDO, 0.7))
        self.canvas.itemconfigure(self._corpo, fill=self.cor if self.preenchido else CARTAO)

    def destruir(self):
        self.canvas.configure(cursor="")
        self.canvas.delete(self.tag)
