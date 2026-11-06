"""Tela cheia da pausa: criada só no aviso e destruída ao fechar.

Cobre todos os monitores. O monitor principal mostra o cartão com contagem
regressiva e os botões; os demais recebem apenas um painel escuro.
Esc fecha a tela a qualquer momento.
"""
import gc
import math
import time
import tkinter as tk

import sistema
import tema

ALFA = 0.94   # leve transparência: efeito de vidro sobre a área de trabalho


def mostrar(planejada_s: int, adiar_min, cor: str, sugestao: str, longa: bool = False):
    """Exibe a tela e devolve (acao, duracao_real_s): acao em feita/adiada/pulada."""
    tela = TelaPausa(planejada_s, adiar_min, tema.cor_destaque(cor), sugestao, longa)
    try:
        return tela.executar()
    finally:
        tela.destruir()


class TelaPausa:
    def __init__(self, planejada_s, adiar_min, destaque, sugestao, longa=False):
        self.longa = longa
        self.planejada = max(1, int(planejada_s))
        self.adiar_min = adiar_min
        self.destaque = destaque
        self.sugestao = sugestao
        self.root = None
        self._resultado = None
        self._fase = "espera"          # "espera" -> "contagem"
        self._inicio = self._fim = 0.0
        self._job = None
        self._botoes = []

    # ---------------------------------------------------------------- ciclo
    def executar(self):
        self.root = tk.Tk()
        self.root.withdraw()
        monitores = sistema.listar_monitores() or [
            (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())]
        principal, *outros = monitores
        self._montar_principal(principal)
        self._secundarias = [self._montar_secundaria(m) for m in outros]
        self.root.bind_all("<Escape>", lambda _e: self._encerrar("pulada"))
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.after(300, self.root.focus_force)   # garante o foco para o Esc
        self.root.mainloop()
        return self._resultado or ("pulada", 0)

    def destruir(self):
        """Fecha tudo: não sobra janela nem job agendado."""
        if self.root is not None:
            try:
                if self._job:
                    self.root.after_cancel(self._job)
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None
        gc.collect()

    def _encerrar(self, acao):
        if self._resultado is not None:
            return
        if acao == "feita":
            real = self.planejada
        elif self._fase == "contagem":
            real = int(min(self.planejada, time.monotonic() - self._inicio))
        else:
            real = 0
        self._resultado = (acao, real)
        self.root.quit()

    # ------------------------------------------------------------- janelas
    @staticmethod
    def _preparar(janela, monitor):
        x, y, w, h = monitor
        janela.overrideredirect(True)
        janela.configure(bg=tema.FUNDO)
        janela.geometry("%dx%d+%d+%d" % (w, h, x, y))
        janela.attributes("-topmost", True)
        try:
            janela.attributes("-alpha", ALFA)
        except tk.TclError:
            pass

    def _montar_secundaria(self, monitor):
        _x, _y, w, h = monitor
        k = tema.escala(h)
        top = tk.Toplevel(self.root)
        self._preparar(top, monitor)
        c = tk.Canvas(top, width=w, height=h, bg=tema.FUNDO, highlightthickness=0)
        c.pack()
        tema.desenhar_grade(c, w, h, int(64 * k))
        c.create_text(w // 2, h // 2 - 20 * k, text="HORA DA PAUSA", fill=self.destaque,
                      font=tema.fonte(tema.FONTE_MONO, 26, k, "bold"))
        c.create_text(w // 2, h // 2 + 30 * k, text="Esc fecha esta tela", fill=tema.TEXTO_SUAVE,
                      font=tema.fonte(tema.FONTE_MONO, 15, k))
        return top

    def _montar_principal(self, monitor):
        _x, _y, w, h = monitor
        k = tema.escala(h)
        self.k = k
        self._preparar(self.root, monitor)
        c = self.canvas = tk.Canvas(self.root, width=w, height=h, bg=tema.FUNDO,
                                    highlightthickness=0)
        c.pack()
        tema.desenhar_grade(c, w, h, int(64 * k))

        cw, ch = min(w - 40, int(900 * k)), min(h - 40, int(700 * k))
        cx, cy = w // 2, h // 2
        x1, y1, x2, y2 = cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2
        tema.cartao_com_brilho(c, x1, y1, x2, y2, int(28 * k), self.destaque)
        tema.colchetes(c, x1 + 18 * k, y1 + 18 * k, x2 - 18 * k, y2 - 18 * k, int(26 * k),
                       self.destaque)

        c.create_text(cx, y1 + 52 * k, text="◢  PAUSA LONGA  ◣" if self.longa else "◢  PAUSA PROGRAMADA  ◣", fill=self.destaque,
                      font=tema.fonte(tema.FONTE_MONO, 16, k, "bold"))
        c.create_text(cx, y1 + 112 * k, text="Você merece uma pausa longa" if self.longa else "Hora de descansar", fill=tema.TEXTO,
                      font=tema.fonte(tema.FONTE_TITULO, 54, k))
        c.create_text(cx, y1 + 162 * k, text="Afaste os olhos da tela e cuide de você.",
                      fill=tema.TEXTO_SUAVE, font=tema.fonte(tema.FONTE_TEXTO, 18, k))

        # Anel de progresso
        ry, raio, larg = y1 + 340 * k, int(105 * k), max(4, int(10 * k))
        self._box = (cx - raio, ry - raio, cx + raio, ry + raio)
        c.create_oval(*self._box, outline=tema.LINHA, width=larg)
        halo = raio + larg
        c.create_oval(cx - halo, ry - halo, cx + halo, ry + halo,
                      outline=tema.misturar(self.destaque, tema.CARTAO, 0.75))
        self._arco = c.create_arc(*self._box, start=90, extent=-359.9, style="arc",
                                  outline=self.destaque, width=larg)
        self._tempo = c.create_text(cx, ry - 8 * k, text=tema.formatar_tempo(self.planejada),
                                    fill=tema.TEXTO, font=tema.fonte(tema.FONTE_NUMERO, 48, k))
        self._rotulo = c.create_text(cx, ry + 40 * k, text="DURAÇÃO DA PAUSA",
                                     fill=tema.TEXTO_SUAVE,
                                     font=tema.fonte(tema.FONTE_MONO, 12, k))

        c.create_text(cx, y1 + 482 * k, text="›  " + self.sugestao, fill=self.destaque,
                      font=tema.fonte(tema.FONTE_TEXTO, 21, k))
        c.create_text(cx, y2 - 30 * k, text="ESC  ·  fechar a qualquer momento",
                      fill=tema.TEXTO_SUAVE, font=tema.fonte(tema.FONTE_MONO, 13, k))

        self._cx, self._by = cx, int(y1 + 572 * k)
        self._criar_botoes_espera()

    # -------------------------------------------------------------- botões
    def _botao(self, dx, texto, comando, cor, preenchido=False, largura=220):
        b = tema.BotaoNeon(self.canvas, self._cx + int(dx * self.k), self._by,
                           int(largura * self.k), int(56 * self.k), texto, comando, cor,
                           preenchido, tema.fonte(tema.FONTE_TEXTO, 19, self.k, "bold"))
        self._botoes.append(b)

    def _limpar_botoes(self):
        for b in self._botoes:
            b.destruir()
        self._botoes = []

    def _criar_botoes_espera(self):
        minutos = ("%g" % self.adiar_min)
        self._botao(-255, "Adiar %s min" % minutos, lambda: self._encerrar("adiada"), tema.VIOLETA)
        self._botao(0, "Iniciar pausa", self._iniciar, self.destaque, True, 250)
        self._botao(255, "Pular", lambda: self._encerrar("pulada"), tema.ROSA)

    # ------------------------------------------------------------ contagem
    def _iniciar(self):
        if self._fase != "espera":
            return
        self._fase = "contagem"
        self._limpar_botoes()
        self._botao(0, "Pular", lambda: self._encerrar("pulada"), tema.ROSA)
        self.canvas.itemconfigure(self._rotulo, text="RESTANTE")
        self._inicio = time.monotonic()
        self._fim = self._inicio + self.planejada
        self._tick()

    def _tick(self):
        restante = self._fim - time.monotonic()
        segundos = max(0, round(restante))
        self.canvas.itemconfigure(self._tempo, text=tema.formatar_tempo(segundos))
        self.canvas.itemconfigure(self._arco, extent=-359.9 * max(0.0, restante) / self.planejada)
        if segundos <= 0:
            self._encerrar("feita")
            return
        # próximo tick exatamente quando o contador mudar de segundo (sem consultar o relógio à toa)
        atraso = max(20, int((restante - (segundos - 1)) * 1000))
        self._job = self.root.after(atraso, self._tick)
