"""Painel de controle: janela que abre ao dar duplo clique no app.

É um processo próprio (`main.py --janela painel`): conversa com o app em segundo plano pelo IPC
(ipc.py) e termina ao fechar, devolvendo a memória. Fechar a janela NÃO encerra o app. Se o app em
segundo plano desaparecer, o painel fecha sozinho (nada de janela órfã).
"""
import gc
import math
import tkinter as tk

import config
import ipc
import sistema
import tema
from versao import VERSAO

LARG, ALT = 760, 960


def abrir():
    painel = Painel()
    try:
        painel.executar()
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
    def __init__(self):
        self.cfg = config.carregar()
        self.destaque = tema.cor_destaque(self.cfg.get("cor_destaque"))
        self.e = None                       # último estado recebido do app em segundo plano
        self.root = None
        self._job = None
        self._falhas = 0
        self._widgets, self._botoes = [], []
        self.view = "home"
        self._assinatura = None

    # --------------------------------------------------------------- ciclo
    def executar(self):
        self.e = ipc.pedir("estado")
        if not self.e or not self.e.get("ok"):
            return                          # não há app em segundo plano: nada a mostrar
        sistema.proteger_tk()
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
        root.protocol("WM_DELETE_WINDOW", self._fechar)
        root.bind("<Escape>", lambda _e: self._fechar())
        self._home()
        root.update_idletasks()
        sistema.barra_escura(root)
        root.deiconify()
        root.lift()
        root.focus_force()
        sistema.trazer_para_frente(root)
        self._job = root.after(1000, self._tick)
        root.mainloop()

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

    def _fechar(self):
        self.root.quit()

    def _tick(self):
        e = ipc.pedir("estado", timeout=1.5)
        if not e or not e.get("ok"):
            self._falhas += 1
            if self._falhas >= 3:           # o app em segundo plano foi encerrado
                self._fechar()
                return
        else:
            self._falhas, self.e = 0, e
            if e.get("foco"):               # outro duplo clique no app: traz a janela à frente
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                sistema.trazer_para_frente(self.root)
            if self.view == "home":
                if self._assinatura_atual() != self._assinatura:
                    self._home()            # algo mudou (atualização, matéria, suspensão...)
                else:
                    self._atualizar_home()
        fase = (self.e or {}).get("atualizacao", {}).get("fase")
        self._job = self.root.after(300 if fase in ("verificando", "baixando") else 1000, self._tick)

    def _assinatura_atual(self):
        e = self.e
        a = e["atualizacao"]
        return (a["fase"], a["versao"], a["msg"], e["suspenso"], e.get("nunca_iniciado"),
                e["materia"], e["feitas"], e["meta"], e["rotulo"].split(" · ")[0])

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

    def _ir(self, funcao):
        """Executa depois do clique terminar (redesenhar a tela dentro do próprio clique é frágil)."""
        return lambda: self.root.after_idle(funcao)

    def _botao(self, cx, y, texto, comando, cor, preenchido=False, largura=290, altura=54):
        k = self.k
        self._botoes.append(tema.BotaoNeon(
            self.canvas, int(cx), int(y * k), int(largura * k), int(altura * k), texto, comando, cor,
            preenchido, self._f(tema.FONTE_TEXTO, 18 if altura > 50 else 16, "bold")))

    def _pedir(self, cmd, **dados):
        """Comando ao app em segundo plano, com atualização imediata da tela."""
        ipc.pedir(cmd, **dados)
        self._atualizar_estado()

    def _atualizar_estado(self):
        e = ipc.pedir("estado", timeout=1.5)
        if e and e.get("ok"):
            self.e = e
            if self.view == "home":
                self._home()

    def _home(self):
        self.view = "home"
        self._assinatura = self._assinatura_atual()
        self._moldura("◢  PAUSA DE ESTUDO  ◣", "Painel de controle")
        c, k, d, cx, e = self.canvas, self.k, self.destaque, self.w // 2, self.e
        ry, raio, larg = int(265 * k), int(102 * k), max(4, int(10 * k))
        box = (cx - raio, ry - raio, cx + raio, ry + raio)
        c.create_oval(*box, outline=tema.LINHA, width=larg)
        halo = raio + larg
        c.create_oval(cx - halo, ry - halo, cx + halo, ry + halo,
                      outline=tema.misturar(d, tema.CARTAO, 0.75))
        self._arco = c.create_arc(*box, start=90, extent=-359.9, style="arc", outline=d, width=larg)
        self._tempo = c.create_text(cx, ry, text="--:--", fill=tema.TEXTO,
                                    font=self._f(tema.FONTE_NUMERO, 50))
        self._rotulo = c.create_text(cx, ry + raio + 38 * k, text="", fill=tema.TEXTO_SUAVE,
                                     font=self._f(tema.FONTE_MONO, 14, "bold"))
        # matéria atual (clique troca) e meta do dia
        materias = self.cfg["materias"]
        if materias:
            self._botao(cx, 452, "Matéria: %s" % (e["materia"] or "(nenhuma)"),
                        self._ir(self._proxima_materia), d, largura=470, altura=42)
        else:
            self._botao(cx, 452, "Cadastrar matérias", self._ir(self._config), d, largura=470, altura=42)
        meta = e["meta"]
        c.create_text(cx, 494 * k, fill=d if meta and e["feitas"] >= meta else tema.TEXTO_SUAVE,
                      text=("Hoje: %d de %d pausas" % (e["feitas"], meta)) if meta
                      else "Hoje: %d pausa(s) feita(s)" % e["feitas"],
                      font=self._f(tema.FONTE_TEXTO, 15))
        esq, dir_ = cx - 160 * k, cx + 160 * k
        self._botao(esq, 550, "Pausar agora", lambda: self._abrir("agora"), d, True)
        self._botao(dir_, 550, "Reiniciar contagem", self._ir(lambda: self._pedir("reiniciar")),
                    tema.VIOLETA)
        if e["suspenso"] and e.get("nunca_iniciado"):
            texto_susp, cmd_susp, destacar = "Iniciar contagem", "iniciar", True
        elif e["suspenso"]:
            texto_susp, cmd_susp, destacar = "Retomar contagem", "suspender", False
        else:
            texto_susp, cmd_susp, destacar = "Suspender contagem", "suspender", False
        self._botao(esq, 617, texto_susp, self._ir(lambda: self._pedir(cmd_susp)),
                    tema.VIOLETA, preenchido=destacar)
        self._botao(dir_, 617, "Resumo", lambda: self._abrir("resumo"), d)
        self._botao(esq, 684, "Configurações", self._ir(self._config), d)
        self._botao_atualizacao(dir_, 684)
        self._botao(cx, 751, "Encerrar app", self._encerrar_app, tema.ROSA)
        a = e["atualizacao"]
        c.create_text(cx, 812 * k, text=a["msg"], justify="center",
                      fill=tema.ROSA if a["fase"] == "erro" else self.destaque,
                      font=self._f(tema.FONTE_TEXTO, 14), width=int(640 * k))
        c.create_text(cx, 870 * k, justify="center", fill=tema.TEXTO_SUAVE,
                      text="v%s  ·  Fechar esta janela não encerra o app:\nele continua em segundo plano." % VERSAO,
                      font=self._f(tema.FONTE_TEXTO, 13))
        self._atualizar_home()

    def _abrir(self, comando):
        """Pede ao app para abrir outra janela; libera o foco porque o clique foi daqui."""
        sistema.permitir_foco()
        ipc.pedir(comando)

    def _encerrar_app(self):
        ipc.pedir("sair")
        self._fechar()

    def _botao_atualizacao(self, cx, y):
        a = self.e["atualizacao"]
        fase = a["fase"]
        if fase == "disponivel":
            self._botao(cx, y, "Atualizar para v%s" % a["versao"], lambda: ipc.pedir("atualizar"),
                        tema.DESTAQUES["verde"], True)
        elif fase in ("verificando", "baixando", "pronto"):
            self._botao(cx, y, "Instalando..." if fase == "pronto" else "Aguarde...",
                        lambda: None, tema.TEXTO_SUAVE)
        else:
            self._botao(cx, y, "Tentar de novo" if fase == "erro" else "Verificar atualização",
                        lambda: ipc.pedir("verificar"), tema.DESTAQUES["verde"])

    def _proxima_materia(self):
        opcoes = list(self.cfg["materias"]) + [""]          # "" = sem matéria
        atual = self.e["materia"]
        nova = opcoes[(opcoes.index(atual) + 1) % len(opcoes)] if atual in opcoes else opcoes[0]
        try:
            cfg = config.carregar()
            cfg["materia_atual"] = nova
            config.gravar(cfg)
        except OSError:
            pass
        self._pedir("materia", nome=nova)

    def _atualizar_home(self):
        e, c = self.e, self.canvas
        c.itemconfigure(self._tempo, text=tema.formatar_tempo(math.ceil(e["restante"])))
        c.itemconfigure(self._rotulo, text=e["rotulo"],
                        fill=tema.VIOLETA if e["suspenso"] else tema.TEXTO_SUAVE)
        c.itemconfigure(self._arco, extent=-359.9 * min(1.0, e["restante"] / max(1.0, e["total"])))

    # ------------------------------------------------------- configurações
    def _entrada(self, largura, valor):
        e = tk.Entry(self.root, width=largura, justify="center", relief="flat",
                     font=self._f(tema.FONTE_NUMERO, 18), bg=tema.FUNDO, fg=tema.TEXTO,
                     insertbackground=self.destaque, highlightthickness=2,
                     highlightbackground=tema.LINHA, highlightcolor=self.destaque)
        e.insert(0, valor)
        self._widgets.append(e)
        return e

    def _config(self):
        self.view = "config"
        self._moldura("◢  CONFIGURAÇÕES  ◣", "Valem a partir do próximo ciclo")
        c, k, d, cx, w = self.canvas, self.k, self.destaque, self.w // 2, self.w
        atual = self._atual = config.carregar(fallback=self.cfg)
        rot = self._f(tema.FONTE_TEXTO, 17)
        self._campos = {}
        for y, chave, texto in ((150, "minutos_estudo", "Tempo de estudo (min)"),
                                (203, "minutos_pausa", "Tempo de pausa (min)"),
                                (256, "adiar_minutos", "Adiar por (min)"),
                                (309, "meta_diaria_pausas", "Meta diária de pausas (0 = sem meta)")):
            c.create_text(80 * k, y * k, anchor="w", text=texto, fill=tema.TEXTO, font=rot)
            e = self._entrada(6, "%g" % atual[chave])
            c.create_window(w - 150 * k, y * k, window=e)
            self._campos[chave] = e
        c.create_text(80 * k, 362 * k, anchor="w", text="Matérias (separe por vírgula)",
                      fill=tema.TEXTO, font=rot)
        self._materias = self._entrada(46, ", ".join(atual["materias"]))
        c.create_window(cx, 402 * k, window=self._materias)
        c.create_text(80 * k, 455 * k, anchor="w", text="Tipo de aviso", fill=tema.TEXTO, font=rot)
        self._modo = _Segmentos(
            c, (cx - 150 * k, cx + 150 * k), int(499 * k), int(270 * k), int(44 * k),
            (("tela_cheia", "Tela cheia"), ("notificacao", "Notificação")),
            atual["modo_aviso"], d, self._f(tema.FONTE_TEXTO, 16, "bold"))
        c.create_text(80 * k, 556 * k, anchor="w", text="Cor de destaque", fill=tema.TEXTO, font=rot)
        self._cor = _Amostras(c, [cx + i * k for i in (-120, -40, 40, 120)],
                              int(600 * k), int(21 * k), atual["cor_destaque"])
        self._chaves = {}
        for y, texto, chave in ((660, "Som nos avisos", "som"),
                                (707, "Iniciar com o Windows", "iniciar_com_windows"),
                                (754, "Verificar atualizações sozinho", "verificar_atualizacoes"),
                                (801, "Não interromper tela cheia/apresentação", "nao_interromper_tela_cheia")):
            c.create_text(80 * k, y * k, anchor="w", text=texto, fill=tema.TEXTO, font=rot)
            self._chaves[chave] = _Interruptor(c, int(w - 130 * k), int(y * k), int(64 * k),
                                               atual[chave], d)
        self._msg = c.create_text(cx, 846 * k, text="", fill=tema.ROSA,
                                  font=self._f(tema.FONTE_TEXTO, 15))
        self._botao(cx - 160 * k, 897, "Salvar", self._salvar, d, True)
        self._botao(cx + 160 * k, 897, "Voltar", self._ir(self._home), tema.VIOLETA)

    def _erro(self, texto):
        self.canvas.itemconfigure(self._msg, fill=tema.ROSA, text=texto)

    def _salvar(self):
        novo = dict(self._atual)        # preserva chaves sem campo na tela (ex.: pausa longa)
        for chave, entrada in self._campos.items():
            try:
                valor = float(entrada.get().strip().replace(",", "."))
            except ValueError:
                valor = -1
            minimo_zero = chave == "meta_diaria_pausas"
            if not (0 <= valor if minimo_zero else 0 < valor) or valor > config.LIMITE_MINUTOS:
                return self._erro("Confira os números (minutos maiores que 0).")
            if chave == "meta_diaria_pausas":
                if valor != int(valor) or valor > 50:
                    return self._erro("A meta diária deve ser um número inteiro até 50.")
                valor = int(valor)
            novo[chave] = int(valor) if valor == int(valor) else valor
        materias = []
        for nome in self._materias.get().split(","):
            nome = nome.strip()
            if nome and nome not in materias:
                materias.append(nome)
        if len(materias) > 12 or any(len(m) > 40 for m in materias):
            return self._erro("Use até 12 matérias, com até 40 letras cada.")
        novo["materias"] = materias
        if novo["materia_atual"] not in materias:
            novo["materia_atual"] = ""
        novo.update(modo_aviso=self._modo.valor, cor_destaque=self._cor.valor)
        novo.update({chave: ch.valor for chave, ch in self._chaves.items()})
        try:
            config.gravar(config.validar(novo))
            import inicializacao
            inicializacao.sincronizar(novo["iniciar_com_windows"])
        except OSError:
            return self._erro("Não foi possível gravar o config.json.")
        self.cfg = config.validar(novo)
        self._atual = self.cfg
        ipc.pedir("materia", nome=self.cfg["materia_atual"])
        self.canvas.itemconfigure(self._msg, fill=self.destaque,
                                  text="Salvo! Vale a partir do próximo ciclo.")
