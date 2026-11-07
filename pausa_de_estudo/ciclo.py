"""Ciclo de estudo e pausa do app em segundo plano (daemon).

Orientado a eventos: a thread principal dorme em `fila.get(timeout=...)` até o fim do tempo ou
até chegar um evento (comando, janela fechada, tarefa concluída). Não importa tkinter nem
urllib/ssl: janelas e rede rodam em processos filhos (ver janelas.py).
"""
import json
import os
import queue
import threading
import time
from datetime import date

import config
import historico
import inicializacao
import janelas
import notificacoes
import registro
import sistema
import textos
from versao import VERSAO

ROTULOS = {"estudo": "ESTUDANDO · PRÓXIMA PAUSA EM",
           "pausa": "EM PAUSA · VOLTA AO ESTUDO EM",
           "adiada": "PAUSA ADIADA · AVISO EM",
           "ocupado": "TELA CHEIA EM USO · NOVA TENTATIVA EM",
           "tela": "PAUSA EM ANDAMENTO"}
INTERVALO_VERIFICACAO = 24 * 3600
ESPERA_OCUPADO = 60          # segundos entre tentativas quando há tela cheia em uso


def _arquivo_temporario() -> str:
    caminho = os.path.join(sistema.pasta_temp(), "pausa-%s.json" % os.urandom(6).hex())
    open(caminho, "x").close()
    return caminho


def _ler_saida(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass


class Atualizacao:
    """Estado da atualização. A rede acontece em processos filhos; aqui só se lê o resultado."""

    def __init__(self, ciclo):
        self.ciclo = ciclo
        self._lock = threading.Lock()
        self._estado = {"fase": "ocioso", "versao": None, "msg": "", "caminho": None}
        self._info = None
        self._ultima = None
        self._saidas = {}
        self._manual = False

    def estado(self) -> dict:
        with self._lock:
            return dict(self._estado)

    def _definir(self, **campos):
        with self._lock:
            self._estado.update(campos)

    def _ocupado(self) -> bool:
        return self.estado()["fase"] in ("verificando", "baixando")

    def _tarefa(self, nome: str):
        saida = _arquivo_temporario()
        self._saidas[nome] = saida
        try:
            janelas.lancar_vigiado(["--tarefa", nome, "--saida", saida], self.ciclo.fila, "tarefa:" + nome)
        except OSError:
            registro.excecao("Não foi possível iniciar a tarefa %s", nome)
            self._definir(fase="erro", msg="Não foi possível verificar agora.")

    def verificar(self, manual: bool = False):
        if self._ocupado():
            return
        self._ultima, self._manual = time.monotonic(), manual
        self._definir(fase="verificando", msg="Procurando atualizações...")
        self._tarefa("verificar")

    def verificar_se_preciso(self):
        if self._ultima is None or time.monotonic() - self._ultima > INTERVALO_VERIFICACAO:
            self.verificar()

    def instalar(self):
        """Baixa a atualização (ou abre a página, na versão portátil)."""
        e = self.estado()
        if e["fase"] != "disponivel" or not self._info:
            return
        if not sistema.instalado():
            if self._info.get("pagina"):
                sistema.abrir_endereco(self._info["pagina"])
            self._definir(msg="Versão portátil: abri a página de download.")
            return
        self._definir(fase="baixando", msg="Baixando a atualização...")
        self._tarefa("baixar")

    def concluir(self, nome: str):
        """Lê o resultado do processo filho que terminou."""
        res = _ler_saida(self._saidas.pop(nome, ""))
        if not res or not res.get("ok"):
            self._definir(fase="erro", msg=(res or {}).get("erro", "A verificação falhou."))
        elif nome == "verificar":
            self._info = res["info"]
            if res["nova"]:
                self._definir(fase="disponivel", versao=res["info"]["versao"],
                              msg="Nova versão disponível: v%s" % res["info"]["versao"])
                if not self._manual:
                    notificacoes.avisar("Atualização disponível",
                                        "Pausa de Estudo v%s. Abra o painel > Atualizar."
                                        % res["info"]["versao"], som=False)
            else:
                self._definir(fase="atualizado",
                              msg="Você está na versão mais recente (v%s)." % VERSAO)
        else:
            self._definir(fase="pronto", caminho=res["caminho"], msg="Pronto para instalar.")


class Ciclo:
    def __init__(self, fila, ocupado_fn=None):
        self.fila = fila
        self.lock = threading.RLock()
        self.cfg = dict(config.PADRAO)
        self.estado, self.limite, self.duracao = "estudo", time.monotonic(), 1.0
        self.suspenso, self.restante_suspenso = False, 0.0
        self.iniciar_suspenso = True           # só a 1ª espera de estudo nasce suspensa
        self.nunca_iniciado = False             # True enquanto essa 1ª espera não for iniciada
        self.contador, self.longa = 0, False
        self.materia = None                    # None = ainda não lida do config
        self.janelas = {}                      # nome -> processo filho
        self.atualizacao = Atualizacao(self)
        self.ocupado_fn = ocupado_fn or sistema.ocupado_tela_cheia
        self._foco = False                     # pedir ao painel aberto para vir à frente
        self._feitas = None                    # (dia, quantidade) de pausas feitas hoje
        self._meta_avisada = None

    # ------------------------------------------------------------ laço
    def executar(self):
        while True:
            # Config lida só no começo de cada ciclo: mudanças valem a partir do próximo.
            self.cfg = config.carregar(fallback=self.cfg)
            if self.materia is None:
                self.materia = self.cfg["materia_atual"]
            inicializacao.sincronizar(self.cfg["iniciar_com_windows"])
            if self.cfg["verificar_atualizacoes"]:
                self.atualizacao.verificar_se_preciso()
            motivo = self.esperar(self.cfg["minutos_estudo"] * 60,
                                  suspenso_inicial=self.iniciar_suspenso)
            self.iniciar_suspenso = False
            if motivo == "sair":
                return
            with self.lock:
                estudo_s = int(self.duracao - self._restante())
            self.contador += 1
            n = self.cfg["ciclos_pausa_longa"]
            if self.pausa(longa=bool(n) and self.contador % n == 0, forcar=motivo == "agora",
                          estudo_s=estudo_s) == "sair":
                return

    def esperar(self, segundos: float, estado: str = "estudo", suspenso_inicial: bool = False) -> str:
        """Dorme até o fim do tempo. Retorna "tempo", "agora" ou "sair"."""
        with self.lock:
            self.estado, self.duracao = estado, max(1.0, segundos)
            self.limite = time.monotonic() + segundos
            self.suspenso = suspenso_inicial
            self.restante_suspenso = self.duracao if suspenso_inicial else 0.0
            if suspenso_inicial:
                self.nunca_iniciado = True
        while True:
            with self.lock:
                suspenso, restante = self.suspenso, self.limite - time.monotonic()
            if not suspenso and restante <= 0:
                return "tempo"
            try:                                    # suspenso: só acorda com um evento
                evento = self.fila.get(timeout=None if suspenso else restante)
            except queue.Empty:
                return "tempo"
            resultado = self.tratar_evento(evento)
            if resultado in ("sair", "agora"):
                return resultado

    def tratar_evento(self, evento: str):
        """Eventos da fila. Retorna "sair" ou "agora" quando o laço precisa reagir."""
        if evento in ("sair", "agora"):
            return evento
        if evento == "painel":
            self.abrir_janela("painel")
        elif evento in ("resumo", "estatisticas"):
            self.abrir_janela("resumo")
        elif evento == "verificar":
            self.atualizacao.verificar(manual=True)
        elif evento == "atualizar":
            self.atualizacao.instalar()
        elif evento.startswith("tarefa:"):
            self.atualizacao.concluir(evento[7:])
            e = self.atualizacao.estado()
            if e["fase"] == "pronto" and e["caminho"]:
                sistema.executar_instalador(e["caminho"])   # o app sai e o instalador o substitui
                return "sair"
        elif evento.startswith("fim:"):
            self.janelas.pop(evento[4:], None)
        return None                                 # "recalcular" e desconhecidos só acordam o laço

    # -------------------------------------------------- estado e comandos (thread do IPC)
    def _restante(self) -> float:
        if self.suspenso:
            return self.restante_suspenso
        if self.estado == "tela":
            return self.duracao
        return max(0.0, self.limite - time.monotonic())

    def estado_info(self):
        """(rótulo, segundos restantes, duração total)."""
        with self.lock:
            if self.suspenso:
                rotulo = ("AGUARDANDO INÍCIO · CLIQUE EM INICIAR" if self.nunca_iniciado
                          else "CONTAGEM SUSPENSA")
            else:
                rotulo = ROTULOS[self.estado]
            return rotulo, self._restante(), self.duracao

    def alternar_suspensao(self) -> bool:
        with self.lock:
            agora = time.monotonic()
            if self.suspenso:
                self.limite, self.suspenso = agora + self.restante_suspenso, False
                self.nunca_iniciado = False
            else:
                self.restante_suspenso, self.suspenso = max(0.0, self.limite - agora), True
            suspenso = self.suspenso
        self.fila.put("recalcular")
        return suspenso

    def iniciar_contagem(self):
        """Começa a contagem quando ela nasceu suspensa à espera do usuário."""
        with self.lock:
            self.nunca_iniciado = False
        if self.suspenso:
            self.alternar_suspensao()

    def reiniciar_contagem(self):
        with self.lock:
            if self.suspenso:
                self.restante_suspenso = self.duracao
            else:
                self.limite = time.monotonic() + self.duracao
        self.fila.put("recalcular")

    def feitas_hoje(self) -> int:
        hoje = date.today()
        if self._feitas is None or self._feitas[0] != hoje:
            try:
                self._feitas = (hoje, historico.resumo_dia()["feita"])
            except Exception:
                registro.excecao("Falha ao ler as pausas de hoje")
                self._feitas = (hoje, 0)
        return self._feitas[1]

    def tratar(self, cmd: str, dados: dict) -> dict:
        """Chamado pela thread do IPC. Leitura e mudanças simples aqui; o resto vira evento."""
        if cmd == "ping":
            return {"ok": True}
        if cmd == "estado":
            rotulo, restante, total = self.estado_info()
            with self.lock:
                foco, self._foco = self._foco, False
                suspenso, materia = self.suspenso, self.materia
            return {"ok": True, "rotulo": rotulo, "restante": restante, "total": total,
                    "suspenso": suspenso, "nunca_iniciado": self.nunca_iniciado, "foco": foco,
                    "versao": VERSAO, "materia": materia or "",
                    "meta": self.cfg["meta_diaria_pausas"], "feitas": self.feitas_hoje(),
                    "atualizacao": self.atualizacao.estado()}
        if cmd == "suspender":
            return {"ok": True, "suspenso": self.alternar_suspensao()}
        if cmd == "iniciar":
            self.iniciar_contagem()
            return {"ok": True}
        if cmd == "reiniciar":
            self.reiniciar_contagem()
            return {"ok": True}
        if cmd == "materia":
            self.materia = str(dados.get("nome", ""))[:40]
            return {"ok": True}
        if cmd in ("sair", "agora", "painel", "resumo", "estatisticas", "verificar", "atualizar"):
            self.fila.put(cmd)
            return {"ok": True}
        return {"ok": False, "erro": "comando desconhecido"}

    # -------------------------------------------------------------- janelas
    def abrir_janela(self, nome: str, extras: list = None):
        """Abre uma janela filha (uma de cada tipo). Se já está aberta, pede para vir à frente."""
        proc = self.janelas.get(nome)
        if proc is not None and proc.poll() is None:
            self._foco = True
            return proc
        try:
            proc = janelas.lancar_vigiado(["--janela", nome] + (extras or []), self.fila, "fim:" + nome)
        except OSError:
            registro.excecao("Não foi possível abrir a janela %s", nome)
            return None
        self.janelas[nome] = proc
        return proc

    def encerrar_janelas(self):
        for proc in list(self.janelas.values()):
            if proc.poll() is None:
                proc.terminate()
        for proc in list(self.janelas.values()):
            try:
                proc.wait(2)
            except Exception:
                pass

    # -------------------------------------------------------------- pausa
    def pausa(self, longa: bool = False, forcar: bool = False, estudo_s: int = 0):
        """Executa o aviso (com adiamentos). Retorna "sair" se o app foi encerrado."""
        self.longa = longa
        minutos = self.cfg["minutos_pausa_longa" if longa else "minutos_pausa"]
        planejada = int(round(minutos * 60))
        sugestao = textos.SUGESTOES[os.urandom(1)[0] % len(textos.SUGESTOES)]
        tela = self.cfg["modo_aviso"] == "tela_cheia"
        if tela and not forcar and self.cfg["nao_interromper_tela_cheia"]:
            if self.aguardar_livre() == "sair":
                return "sair"
        primeiro = True
        while True:
            if tela:
                acao, real, sair = self.aviso_tela_cheia(planejada, sugestao)
            else:
                acao, real, sair = self.aviso_notificacao(planejada, sugestao)
            self.registrar(planejada, real, acao, estudo_s if primeiro else 0)
            primeiro = False
            if acao == "feita":
                self.contar_feita()
            if sair:
                return "sair"
            if acao == "adiada":
                if self.esperar(self.cfg["adiar_minutos"] * 60, "adiada") == "sair":
                    return "sair"
                continue
            if acao == "feita":
                notificacoes.voltar_a_estudar(self.cfg["som"], usar_toast=not tela)
            return None

    def aguardar_livre(self):
        """Não abre a tela de pausa sobre apresentação/jogo/vídeo em tela cheia."""
        avisou = False
        while self.ocupado_fn():
            if not avisou:
                notificacoes.avisar(textos.TITULO_ADIADA, textos.MSG_ADIADA, som=False)
                avisou = True
            resultado = self.esperar(ESPERA_OCUPADO, "ocupado")
            if resultado == "sair":
                return "sair"
            if resultado == "agora":
                break
        return None

    def aviso_tela_cheia(self, planejada, sugestao):
        """Abre a tela de pausa como processo filho e espera o resultado (sem janela no daemon)."""
        saida = _arquivo_temporario()
        extras = ["--planejada", str(planejada), "--adiar", "%g" % self.cfg["adiar_minutos"],
                  "--cor", self.cfg["cor_destaque"], "--sugestao", sugestao, "--saida", saida]
        if self.longa:
            extras.append("--longa")
        with self.lock:
            self.estado, self.duracao, self.suspenso = "tela", float(planejada), False
        proc = self.abrir_janela("pausa", extras)
        if proc is None:
            return self.aviso_notificacao(planejada, sugestao)
        while True:
            evento = self.fila.get()
            if evento == "fim:pausa":
                break
            if evento == "sair":
                proc.terminate()
                _ler_saida(saida)
                return "pulada", 0, True
            self.tratar_evento(evento)            # "agora" e afins são ignorados: já está em pausa
        resultado = _ler_saida(saida)
        if not resultado or resultado.get("acao") not in ("feita", "adiada", "pulada"):
            registro.erro("A tela de pausa terminou sem resultado; usando notificação")
            return self.aviso_notificacao(planejada, sugestao)
        return resultado["acao"], int(resultado.get("real", 0)), False

    def aviso_notificacao(self, planejada, sugestao):
        """Sem janela: avisa, espera a duração da pausa e assume que foi feita."""
        titulo = textos.TITULO_PAUSA_LONGA if self.longa else textos.TITULO_PAUSA
        notificacoes.avisar(titulo, "Descanse por %g min. %s" % (planejada / 60, sugestao),
                            self.cfg["som"])
        inicio = time.monotonic()
        motivo = self.esperar(planejada, "pausa")
        real = int(min(planejada, time.monotonic() - inicio))
        if motivo == "sair":
            return "pulada", real, True
        return "feita", real, False

    def registrar(self, planejada, real, acao, estudo_s=0):
        try:
            historico.registrar(planejada, real, acao, materia=self.materia or "", estudo_s=estudo_s)
        except Exception:
            registro.excecao("Falha ao gravar no histórico")

    def contar_feita(self):
        """Atualiza o contador do dia e avisa uma vez quando a meta diária é batida."""
        n = self.feitas_hoje() + 1
        self._feitas = (date.today(), n)
        meta = self.cfg["meta_diaria_pausas"]
        if meta and n >= meta and self._meta_avisada != date.today():
            self._meta_avisada = date.today()
            notificacoes.avisar(textos.TITULO_META, textos.MSG_META % n, self.cfg["som"])
