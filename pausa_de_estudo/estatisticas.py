"""Tela de resumo do histórico: total do dia e dos últimos 7 dias.

Janela flutuante sem borda (cantos arredondados via -transparentcolor, que é do
Windows). Aberta sob demanda e destruída ao fechar. Esc ou ✕ fecham.
"""
import gc
import tkinter as tk
from datetime import date

import config
import historico
import sistema
import tema

DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _horas(segundos: int) -> str:
    minutos = round(segundos / 60)
    return "%d h %02d min" % divmod(minutos, 60) if minutos >= 60 else "%d min" % minutos


def abrir(cor: str = "ciano", sondar=None) -> None:
    """`sondar()` devolve True quando um comando externo pede para fechar a janela."""
    tela = JanelaEstatisticas(tema.cor_destaque(cor), sondar)
    try:
        tela.executar()
    finally:
        tela.destruir()


class JanelaEstatisticas:
    def __init__(self, destaque, sondar=None):
        self.destaque = destaque
        self.sondar = sondar
        self.root = None
        self._job = None
        self.sequencia, self.materias, self.meta = 0, [], 0

    def destruir(self):
        if self.root is not None:
            try:
                if self._job:
                    self.root.after_cancel(self._job)
                self.root.destroy()
            except tk.TclError:
                pass
            self.root = None
        gc.collect()

    def executar(self):
        sistema.proteger_tk()
        try:
            dias = historico.resumo_dias(7)
            self.sequencia = historico.sequencia_dias()
            self.materias = historico.resumo_materias(7)
            self.meta = config.carregar()["meta_diaria_pausas"]
            erro = None
        except Exception as e:      # banco bloqueado/corrompido: mostra a tela vazia + aviso
            dias, self.sequencia, erro = [], 0, "Não foi possível ler o histórico (%s)" % e
        self.root = root = tk.Tk()
        root.withdraw()
        k = tema.escala(root.winfo_screenheight(), 0.8, 1.6)
        self.k = k
        w, h = int(720 * k), int(880 * k)
        root.overrideredirect(True)
        root.configure(bg=tema.TRANSPARENTE)
        try:
            root.attributes("-transparentcolor", tema.TRANSPARENTE)
        except tk.TclError:
            root.configure(bg=tema.FUNDO)       # fora do Windows: sem cantos transparentes
        root.attributes("-topmost", True)
        root.geometry("%dx%d+%d+%d" % (w, h, (root.winfo_screenwidth() - w) // 2,
                                       (root.winfo_screenheight() - h) // 2))
        self.canvas = c = tk.Canvas(root, width=w, height=h, bg=root["bg"], highlightthickness=0)
        c.pack()
        self._desenhar(w, h, dias, erro)
        root.bind("<Escape>", lambda _e: root.quit())
        root.deiconify()
        root.update()
        root.focus_force()
        sistema.trazer_para_frente(root)
        root.after(200, root.focus_force)         # garante o foco (o Esc depende dele)
        if self.sondar:
            self._vigiar()
        root.mainloop()

    def _vigiar(self):
        if self.sondar():
            self.root.quit()
            return
        self._job = self.root.after(1000, self._vigiar)

    # ---------------------------------------------------------- desenho
    def _desenhar(self, w, h, dias, erro):
        c, k, d = self.canvas, self.k, self.destaque
        m = int(16 * k)
        x1, y1, x2, y2 = m, m, w - m, h - m
        tema.cartao_com_brilho(c, x1, y1, x2, y2, int(26 * k), d, camadas=4)
        tema.colchetes(c, x1 + 14 * k, y1 + 14 * k, x2 - 14 * k, y2 - 14 * k, int(22 * k), d)

        # barra de título arrastável
        c.create_rectangle(x1 + 20 * k, y1 + 14 * k, x2 - 90 * k, y1 + 80 * k, outline="",
                           fill=tema.CARTAO, tags="arrastar")   # área clicável (precisa de fill)
        c.create_text(x1 + 40 * k, y1 + 46 * k, anchor="w", text="◢  RESUMO DAS PAUSAS", fill=d,
                      font=tema.fonte(tema.FONTE_MONO, 17, k, "bold"), tags="arrastar")
        c.tag_bind("arrastar", "<ButtonPress-1>", self._arrastar_inicio)
        c.tag_bind("arrastar", "<B1-Motion>", self._arrastar_mover)
        tema.BotaoNeon(c, int(x2 - 52 * k), int(y1 + 46 * k), int(40 * k), int(40 * k), "✕",
                       self.root.quit, tema.ROSA,
                       fonte_botao=tema.fonte(tema.FONTE_TEXTO, 16, k, "bold"))

        hoje = date.today()
        hoje_r = dias[-1] if dias else {"feita": 0, "adiada": 0, "pulada": 0,
                                        "total": 0, "segundos_descanso": 0}
        c.create_text(x1 + 40 * k, y1 + 100 * k, anchor="w",
                      text="Hoje  ·  %s %s" % (DIAS_SEMANA[hoje.weekday()], hoje.strftime("%d/%m/%Y")),
                      fill=tema.TEXTO_SUAVE, font=tema.fonte(tema.FONTE_TEXTO, 16, k))

        c.create_text(x2 - 40 * k, y1 + 100 * k, anchor="e",
                      text="SEQUÊNCIA  %d dia%s" % (self.sequencia, "" if self.sequencia == 1 else "s"),
                      fill=d if self.sequencia else tema.TEXTO_SUAVE,
                      font=tema.fonte(tema.FONTE_MONO, 14, k, "bold"))

        # três cartões de métricas do dia
        largura = (x2 - x1 - 80 * k - 2 * 16 * k) / 3
        for i, (rotulo, chave, cor) in enumerate(
                (("FEITAS", "feita", d), ("ADIADAS", "adiada", tema.VIOLETA),
                 ("PULADAS", "pulada", tema.ROSA))):
            tx1 = x1 + 40 * k + i * (largura + 16 * k)
            ty1, ty2 = y1 + 128 * k, y1 + 258 * k
            tema.retangulo_arredondado(c, int(tx1), int(ty1), int(tx1 + largura), int(ty2),
                                       int(18 * k), fill=tema.FUNDO,
                                       outline=tema.misturar(cor, tema.FUNDO, 0.5), width=1)
            c.create_text(tx1 + largura / 2, ty1 + 52 * k, text=str(hoje_r[chave]), fill=cor,
                          font=tema.fonte(tema.FONTE_NUMERO, 54, k))
            c.create_text(tx1 + largura / 2, ty2 - 26 * k, text=rotulo, fill=tema.TEXTO_SUAVE,
                          font=tema.fonte(tema.FONTE_MONO, 13, k, "bold"))
        c.create_text(x1 + 40 * k, y1 + 284 * k, anchor="w",
                      text="Descanso efetivo hoje: %d min   ·   %d aviso(s)"
                           % (round(hoje_r["segundos_descanso"] / 60), hoje_r["total"]),
                      fill=tema.TEXTO, font=tema.fonte(tema.FONTE_TEXTO, 17, k))

        # meta diária
        feitas = hoje_r["feita"]
        if self.meta:
            c.create_text(x1 + 40 * k, y1 + 330 * k, anchor="w", text="META DE HOJE", fill=d,
                          font=tema.fonte(tema.FONTE_MONO, 14, k, "bold"))
            c.create_text(x2 - 40 * k, y1 + 330 * k, anchor="e", fill=d if feitas >= self.meta else tema.TEXTO,
                          text="%d / %d pausas" % (feitas, self.meta),
                          font=tema.fonte(tema.FONTE_TEXTO, 15, k))
            bx1, bx2, by = x1 + 40 * k, x2 - 40 * k, y1 + 352 * k
            tema.retangulo_arredondado(c, int(bx1), int(by), int(bx2), int(by + 14 * k), int(7 * k),
                                       fill=tema.LINHA, outline="")
            if feitas:
                tema.retangulo_arredondado(c, int(bx1), int(by), int(bx1 + (bx2 - bx1) * min(1, feitas / self.meta)),
                                           int(by + 14 * k), int(7 * k), fill=d, outline="")
        else:
            c.create_text(x1 + 40 * k, y1 + 336 * k, anchor="w", fill=tema.TEXTO_SUAVE,
                          text="Meta diária desligada (defina em Configurações)",
                          font=tema.fonte(tema.FONTE_TEXTO, 14, k))

        # gráfico dos últimos 7 dias (barras empilhadas por ação)
        c.create_text(x1 + 40 * k, y1 + 396 * k, anchor="w", text="ÚLTIMOS 7 DIAS",
                      fill=d, font=tema.fonte(tema.FONTE_MONO, 14, k, "bold"))
        base, topo = y1 + 580 * k, y1 + 440 * k
        c.create_line(x1 + 40 * k, base, x2 - 40 * k, base, fill=tema.LINHA)
        maximo = max([dia["total"] for dia in dias] + [1])
        faixa = (x2 - x1 - 80 * k) / 7
        for i, dia in enumerate(dias):
            bx = x1 + 40 * k + i * faixa
            bw = faixa * 0.52
            bx1 = bx + (faixa - bw) / 2
            y = base
            for chave, cor in (("feita", d), ("adiada", tema.VIOLETA), ("pulada", tema.ROSA)):
                if dia[chave]:
                    altura = (base - topo) * dia[chave] / maximo
                    c.create_rectangle(bx1, y - altura, bx1 + bw, y, fill=cor, outline="")
                    y -= altura
            if dia["total"]:
                c.create_text(bx1 + bw / 2, y - 12 * k, text=str(dia["total"]), fill=tema.TEXTO,
                              font=tema.fonte(tema.FONTE_NUMERO, 15, k))
            nome = "hoje" if dia["data"] == hoje else DIAS_SEMANA[dia["data"].weekday()]
            c.create_text(bx1 + bw / 2, base + 20 * k, text=nome,
                          fill=d if dia["data"] == hoje else tema.TEXTO_SUAVE,
                          font=tema.fonte(tema.FONTE_MONO, 13, k))

        c.create_text(x1 + 40 * k, y1 + 654 * k, anchor="w", text="POR MATÉRIA (7 DIAS)", fill=d,
                      font=tema.fonte(tema.FONTE_MONO, 14, k, "bold"))
        if not self.materias:
            c.create_text(x1 + 40 * k, y1 + 690 * k, anchor="w", fill=tema.TEXTO_SUAVE,
                          text="Nenhum estudo registrado ainda. Escolha a matéria no painel.",
                          font=tema.fonte(tema.FONTE_TEXTO, 14, k))
        for i, (nome, pausas, estudo) in enumerate(self.materias[:3]):
            y = y1 + (690 + 30 * i) * k
            c.create_text(x1 + 40 * k, y, anchor="w", text=nome, fill=tema.TEXTO,
                          font=tema.fonte(tema.FONTE_TEXTO, 16, k))
            c.create_text(x2 - 40 * k, y, anchor="e", fill=tema.TEXTO_SUAVE,
                          text="%s  ·  %d pausa%s" % (_horas(estudo), pausas, "" if pausas == 1 else "s"),
                          font=tema.fonte(tema.FONTE_TEXTO, 15, k))

        tot = historico.somar(dias)
        c.create_text(x1 + 40 * k, y2 - 84 * k, anchor="w",
                      text="7 dias: %d avisos  ·  %d feitas  ·  %d adiadas  ·  %d puladas  ·  %d min de descanso"
                           % (tot["total"], tot["feita"], tot["adiada"], tot["pulada"],
                              round(tot["segundos_descanso"] / 60)),
                      fill=tema.TEXTO_SUAVE, font=tema.fonte(tema.FONTE_TEXTO, 14, k))
        self._rodape = c.create_text(x1 + 40 * k, y2 - 34 * k, anchor="w",
                                     text=erro or "Arraste pelo topo  ·  Esc ou ✕ para fechar",
                                     fill=tema.ROSA if erro else tema.TEXTO_SUAVE,
                                     font=tema.fonte(tema.FONTE_MONO, 12, k))
        tema.BotaoNeon(c, int(x2 - 150 * k), int(y2 - 38 * k), int(190 * k), int(40 * k),
                       "Exportar CSV", self._exportar, d,
                       fonte_botao=tema.fonte(tema.FONTE_TEXTO, 14, k, "bold"))

    def _exportar(self):
        import os
        import subprocess
        destino = os.path.join(sistema.pasta_app(), "historico.csv")
        try:
            n = historico.exportar_csv(destino)
            self.canvas.itemconfigure(self._rodape, fill=self.destaque,
                                      text="%d registro(s) exportados para historico.csv" % n)
            if sistema.e_windows():
                subprocess.Popen(["explorer", "/select,", destino])
        except Exception as e:
            self.canvas.itemconfigure(self._rodape, fill=tema.ROSA,
                                      text="Falha ao exportar: %s" % e)

    # ---------------------------------------------------------- arrastar
    def _arrastar_inicio(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _arrastar_mover(self, e):
        self.root.geometry("+%d+%d" % (e.x_root - self._dx, e.y_root - self._dy))
