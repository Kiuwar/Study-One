"""Painel de controle: a janela que abre ao dar duplo clique no app.

Mostra a contagem até a próxima pausa e permite pausar agora, abrir o resumo,
mudar as configurações (sem editar JSON) e encerrar o app. Fechar a janela NÃO
encerra o app: ele continua em segundo plano. Criado sob demanda e destruído
ao fechar.
"""
import gc
import math
import tkinter as tk

import config
import sistema
import tema

LARG, ALT = 760, 800


def abrir(estado_fn, cfg, ao_salvar=None, sondar=None):
    """Retorna "agora", "resumo", "sair", "tempo" (a pausa venceu) ou None (fechou)."""
    painel = Painel(estado_fn, cfg, ao_salvar, sondar)
    try:
        return painel.executar()
    finally:
        painel.destruir()


def _mao(canvas, tag):
    canvas.tag_bind(tag, "<Enter>", lambda _e: canvas.configure(cursor="hand2"))
    canvas.tag_bind(tag, "<Leave>", lambda _e: canvas.configure(cursor=""))


class _Segmentos:
    """Escolha de uma opção entre várias (botões lado a lado)."""

    def __init__(self, c, centros, y, largura, altura, opcoes, valor, cor, fonte):
        self.c, self.valor, self.cor, self.itens = c, valor, cor, {}
        for cx, (val, texto) in zip(centros, opcoes):
            tag = "seg%d%s" % (id(self), val)
            corpo = tema.retangulo_arredondado(
                c, cx - largura // 2, y - altura // 2, cx + largura // 2, y + altura // 2,
                altura // 2, width=2, tags=tag)
            txt = c.create_text(cx, y, text=texto, font=fonte, tags=tag)
            c.tag_bind(tag, "<ButtonRelease-1>", lambda _e, v=val: self.definir(v))
            _mao(c, tag)
            self.itens[val] = (corpo, txt)
        self._pintar()

    def definir(self, valor):
        self.valor = valor
        self._pintar()

    def _pintar(self):
        for val, (corpo, txt) in self.itens.items():
            sel = val == self.valor
            self.c.itemconfigure(corpo, fill=self.cor if sel else tema.CARTAO,
                                 outline=self.cor if sel else tema.LINHA)
            self.c.itemconfigure(txt, fill=tema.FUNDO if sel else tema.TEXTO_SUAVE)


class _Amostras:
    """Escolha de cor (círculos)."""

    def __init__(self, c, centros, y, raio, valor):
        self.c, self.valor, self.itens = c, valor, {}
        for cx, (nome, hexa) in zip(centros, tema.DESTAQUES.items()):
            tag = "cor%d%s" % (id(self), nome)
            self.itens[nome] = c.create_oval(cx - raio, y - raio, cx + raio, y + raio,
                                             fill=hexa, tags=tag)
            c.tag_bind(tag, "<ButtonRelease-1>", lambda _e, n=nome: self.definir(n))
            _mao(c, tag)
        self._pintar()

    def definir(self, nome):
        self.valor = nome
        self._pintar()

    def _pintar(self):
        for nome, item in self.itens.items():
            sel = nome == self.valor
            self.c.itemconfigure(item, outline=tema.TEXTO if sel else tema.FUNDO,
                                 width=4 if sel else 2)


class _Interruptor:
    """Liga/desliga."""

    def __init__(self, c, cx, y, largura, valor, cor):
        self.c, self.valor, self.cor, self.h = c, bool(valor), cor, largura // 2
        tag = "int%d" % id(self)
        self.x1, self.x2, self.y = cx - largura // 2, cx + largura // 2, y
        self.trilho = tema.retangulo_arredondado(c, self.x1, y - self.h // 2, self.x2,
                                                 y + self.h // 2, self.h // 2, tags=tag)
        self.botao = c.create_oval(0, 0, 1, 1, outline="", fill=tema.TEXTO, tags=tag)
        c.tag_bind(tag, "<ButtonRelease-1>", lambda _e: self.alternar())
        _mao(c, tag)
        self._pintar()

    def alternar(self):
        self.valor = not self.valor
        self._pintar()

    def _pintar(self):
        r = self.h // 2 - 3
        cx = self.x2 - self.h // 2 if self.valor else self.x1 + self.h // 2
        self.c.coords(self.botao, cx - r, self.y - r, cx + r, self.y + r)
        self.c.itemconfigure(self.trilho, fill=self.cor if self.valor else tema.LINHA,
                             outline=self.cor if self.valor else tema.LINHA)


class Painel:
    def __init__(self, estado_fn, cfg, ao_salvar, sondar=None):
        self.estado_fn, self.cfg, self.ao_salvar, self.sondar = estado_fn, dict(cfg), ao_salvar, sondar
        self.destaque = tema.cor_destaque(cfg.get("cor_destaque"))
        self.root = None
        self._resultado = None
        self._job = None
        self._widgets, self._botoes = [], []
        self.view = "home"

    # --------------------------------------------------------------- ciclo
    def executar(self):
        self.root = root = tk.Tk()
        root.withdraw()
        k = self.k = tema.escala(root.winfo_screenheight(), 0.7, 1.4)
        self.w, self.h = int(LARG * k), int(ALT * k)
        root.title("Pausa de Estudo")
        root.configure(bg=tema.FUNDO)
        root.resizable(False, False)
        root.geometry("%dx%d+%d+%d" % (self.w, self.h, (root.winfo_screenwidth() - self.w) // 2,
                                       max(0, (root.winfo_screenheight() - self.h) // 2 - 20)))
        try:
            tema.icone(root, self.destaque)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(root, width=self.w, height=self.h, bg=tema.FUNDO,
                                highlightthickness=0)
        self.canvas.pack()
        root.protocol("WM_DELETE_WINDOW", lambda: self._fechar(None))
        root.bind("<Escape>", lambda _e: self._fechar(None))
        self._home()
        root.update_idletasks()
        sistema.barra_escura(root)
        root.deiconify()
        root.lift()
        root.focus_force()
        self._job = root.after(1000, self._tick)
        root.mainloop()
        return self._resultado

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

    def _fechar(self, resultado):
        self._resultado = resultado
        self.root.quit()

    def _tick(self):
        # Comandos externos (--sair, --agora...) chegam enquanto a janela está aberta.
        cmd = self.sondar() if self.sondar else None
        if cmd in ("sair", "agora"):
            self._fechar(cmd)
            return
        if cmd == "estatisticas":
            self._fechar("resumo")
            return
        if cmd == "painel":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        rotulo, restante, total = self.estado_fn()
        if restante <= 0:                       # a pausa venceu com o painel aberto
            self._fechar("tempo")
            return
        if self.view == "home":
            self._atualizar_home(rotulo, restante, total)
        self._job = self.root.after(1000, self._tick)

    # ------------------------------------------------------------ desenho
    def _f(self, familia, tamanho, estilo=""):
        return tema.fonte(familia, tamanho, self.k, estilo)

    def _moldura(self, titulo, subtitulo):
        for wdg in self._widgets:
            wdg.destroy()
        self._widgets, self._botoes = [], []
        c, k, d, w, h = self.canvas, self.k, self.destaque, self.w, self.h
        c.delete("all")
        tema.desenhar_grade(c, w, h, int(64 * k))
        m = int(18 * k)
        tema.cartao_com_brilho(c, m, m, w - m, h - m, int(26 * k), d, camadas=3)
        tema.colchetes(c, m + 14 * k, m + 14 * k, w - m - 14 * k, h - m - 14 * k, int(22 * k), d)
        c.create_text(w // 2, 66 * k, text=titulo, fill=d, font=self._f(tema.FONTE_MONO, 17, "bold"))
        c.create_text(w // 2, 104 * k, text=subtitulo, fill=tema.TEXTO_SUAVE,
                      font=self._f(tema.FONTE_TEXTO, 16))

    def _botao(self, cx, y, texto, comando, cor, preenchido=False, largura=290):
        k = self.k
        self._botoes.append(tema.BotaoNeon(
            self.canvas, int(cx), int(y * k), int(largura * k), int(54 * k), texto, comando, cor,
            preenchido, self._f(tema.FONTE_TEXTO, 18, "bold")))

    def _home(self):
        self.view = "home"
        self._moldura("◢  PAUSA DE ESTUDO  ◣", "Painel de controle")
        c, k, d, cx = self.canvas, self.k, self.destaque, self.w // 2
        ry, raio, larg = int(300 * k), int(112 * k), max(4, int(10 * k))
        box = (cx - raio, ry - raio, cx + raio, ry + raio)
        c.create_oval(*box, outline=tema.LINHA, width=larg)
        halo = raio + larg
        c.create_oval(cx - halo, ry - halo, cx + halo, ry + halo,
                      outline=tema.misturar(d, tema.CARTAO, 0.75))
        self._arco = c.create_arc(*box, start=90, extent=-359.9, style="arc", outline=d, width=larg)
        self._tempo = c.create_text(cx, ry, text="--:--", fill=tema.TEXTO,
                                    font=self._f(tema.FONTE_NUMERO, 52))
        self._rotulo = c.create_text(cx, ry + raio + 44 * k, text="", fill=tema.TEXTO_SUAVE,
                                     font=self._f(tema.FONTE_MONO, 14, "bold"))
        esq, dir_ = cx - 160 * k, cx + 160 * k
        self._botao(esq, 575, "Pausar agora", lambda: self._fechar("agora"), d, True)
        self._botao(dir_, 575, "Resumo", lambda: self._fechar("resumo"), d)
        self._botao(esq, 645, "Configurações", self._config, tema.VIOLETA)
        self._botao(dir_, 645, "Encerrar app", lambda: self._fechar("sair"), tema.ROSA)
        c.create_text(cx, 725 * k, text="Fechar esta janela não encerra o app:\nele continua em segundo plano.",
                      fill=tema.TEXTO_SUAVE, justify="center", font=self._f(tema.FONTE_TEXTO, 14))
        self._atualizar_home(*self.estado_fn())

    def _atualizar_home(self, rotulo, restante, total):
        c = self.canvas
        c.itemconfigure(self._tempo, text=tema.formatar_tempo(math.ceil(restante)))
        c.itemconfigure(self._rotulo, text=rotulo)
        c.itemconfigure(self._arco, extent=-359.9 * min(1.0, restante / max(1.0, total)))

    # ------------------------------------------------------- configurações
    def _config(self):
        self.view = "config"
        self._moldura("◢  CONFIGURAÇÕES  ◣", "Valem a partir do próximo ciclo")
        c, k, d, cx, w = self.canvas, self.k, self.destaque, self.w // 2, self.w
        atual = config.carregar(fallback=self.cfg)
        self._campos = {}
        for y, chave, rotulo in ((170, "minutos_estudo", "Tempo de estudo (min)"),
                                 (230, "minutos_pausa", "Tempo de pausa (min)"),
                                 (290, "adiar_minutos", "Adiar por (min)")):
            c.create_text(80 * k, y * k, anchor="w", text=rotulo, fill=tema.TEXTO,
                          font=self._f(tema.FONTE_TEXTO, 19))
            e = tk.Entry(self.root, width=6, justify="center", relief="flat",
                         font=self._f(tema.FONTE_NUMERO, 20), bg=tema.FUNDO, fg=tema.TEXTO,
                         insertbackground=d, highlightthickness=2,
                         highlightbackground=tema.LINHA, highlightcolor=d)
            e.insert(0, "%g" % atual[chave])
            c.create_window(w - 150 * k, y * k, window=e)
            self._widgets.append(e)
            self._campos[chave] = e

        c.create_text(80 * k, 355 * k, anchor="w", text="Tipo de aviso", fill=tema.TEXTO,
                      font=self._f(tema.FONTE_TEXTO, 19))
        self._modo = _Segmentos(
            c, (cx - 150 * k, cx + 150 * k), int(405 * k), int(270 * k), int(48 * k),
            (("tela_cheia", "Tela cheia"), ("notificacao", "Notificação")),
            atual["modo_aviso"], d, self._f(tema.FONTE_TEXTO, 17, "bold"))
        c.create_text(80 * k, 470 * k, anchor="w", text="Cor de destaque", fill=tema.TEXTO,
                      font=self._f(tema.FONTE_TEXTO, 19))
        self._cor = _Amostras(c, [cx + i * 80 * k for i in (-120 / 80, -40 / 80, 40 / 80, 120 / 80)],
                              int(520 * k), int(22 * k), atual["cor_destaque"])
        for y, texto in ((585, "Som nos avisos"), (640, "Iniciar com o Windows")):
            c.create_text(80 * k, y * k, anchor="w", text=texto, fill=tema.TEXTO,
                          font=self._f(tema.FONTE_TEXTO, 19))
        self._som = _Interruptor(c, int(w - 130 * k), int(585 * k), int(64 * k), atual["som"], d)
        self._auto = _Interruptor(c, int(w - 130 * k), int(640 * k), int(64 * k),
                                  atual["iniciar_com_windows"], d)
        self._msg = c.create_text(cx, 695 * k, text="", fill=tema.ROSA,
                                  font=self._f(tema.FONTE_TEXTO, 15))
        self._botao(cx - 160 * k, 745, "Salvar", self._salvar, d, True)
        self._botao(cx + 160 * k, 745, "Voltar", self._home, tema.VIOLETA)

    def _salvar(self):
        novo = {}
        for chave, entrada in self._campos.items():
            try:
                valor = float(entrada.get().strip().replace(",", "."))
            except ValueError:
                valor = 0
            if not 0 < valor <= config.LIMITE_MINUTOS:
                self.canvas.itemconfigure(self._msg, fill=tema.ROSA,
                                          text="Use números maiores que 0 nos minutos.")
                return
            novo[chave] = int(valor) if valor == int(valor) else valor
        novo.update(modo_aviso=self._modo.valor, cor_destaque=self._cor.valor,
                    som=self._som.valor, iniciar_com_windows=self._auto.valor)
        try:
            config.gravar(config.validar(novo))
            if self.ao_salvar:
                self.ao_salvar(novo)
        except OSError:
            self.canvas.itemconfigure(self._msg, fill=tema.ROSA,
                                      text="Não foi possível gravar o config.json.")
            return
        self.canvas.itemconfigure(self._msg, fill=self.destaque,
                                  text="Salvo! Vale a partir do próximo ciclo.")
