"""Pausa de Estudo — ponto de entrada e laço do ciclo.

Uso:
    python main.py                  inicia o app e abre o painel de controle
    python main.py --silencioso     inicia sem abrir o painel (usado no início com o Windows)
    python main.py --painel         abre o painel (inicia o app se não estiver rodando)
    python main.py --estatisticas   abre a tela de resumo (inicia o app se não estiver rodando)
    python main.py --agora          dispara a pausa imediatamente
    python main.py --sair           encerra o app em execução

A espera usa queue.get(timeout=...): a thread dorme até o fim do tempo ou até
chegar um comando — sem loop ocupado e sem consultar o relógio repetidamente.
"""
import argparse
import logging
import os
import queue
import random
import socket
import sys
import tempfile
import threading
import time

import config
import historico
import inicializacao
import notificacoes
import sistema
import textos

COMANDOS = {"sair", "estatisticas", "agora", "painel", "ping"}


# ------------------------------------------------------------ instância única
def arquivo_porta() -> str:
    return os.path.join(tempfile.gettempdir(), "PausaDeEstudo.porta")


def abrir_servidor():
    """Abre um servidor local em porta livre (escolhida pelo sistema) e a registra."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(4)
    with open(arquivo_porta(), "w", encoding="ascii") as f:
        f.write(str(s.getsockname()[1]))
    return s


def enviar_comando(cmd: str) -> bool:
    """Envia um comando à instância em execução. False se não há nenhuma."""
    try:
        with open(arquivo_porta(), encoding="ascii") as f:
            porta = int(f.read().strip())
        with socket.create_connection(("127.0.0.1", porta), timeout=3) as c:
            c.sendall(cmd.encode("ascii"))
            return c.recv(8) == b"ok"
    except (OSError, ValueError):
        return False


def escutar(servidor, fila):
    """Thread bloqueada em accept(): consome 0% de CPU enquanto ninguém conecta."""
    while True:
        try:
            conn, _ = servidor.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(2)
            try:
                cmd = conn.recv(32).decode("ascii", "ignore").strip()
                if cmd in COMANDOS:
                    if cmd != "ping":
                        fila.put(cmd)
                    conn.sendall(b"ok")
            except OSError:
                pass


# ------------------------------------------------------------------- ciclo
class Ciclo:
    def __init__(self, fila):
        self.fila = fila
        self.cfg = dict(config.PADRAO)
        self.estado, self.limite, self.duracao = "estudo", time.monotonic(), 1.0

    def executar(self):
        while True:
            # Config lida só no começo de cada ciclo: mudanças valem a partir do próximo.
            self.cfg = config.carregar(fallback=self.cfg)
            inicializacao.sincronizar(self.cfg["iniciar_com_windows"])
            if self.esperar(self.cfg["minutos_estudo"] * 60) == "sair":
                return
            if self.pausa() == "sair":
                return

    def esperar(self, segundos: float, estado: str = "estudo") -> str:
        """Dorme até o fim do tempo. Retorna "tempo", "agora" ou "sair"."""
        self.estado, self.duracao = estado, max(1.0, segundos)
        self.limite = time.monotonic() + segundos
        while True:
            restante = self.limite - time.monotonic()
            if restante <= 0:
                return "tempo"
            try:
                cmd = self.fila.get(timeout=restante)
            except queue.Empty:
                return "tempo"
            if cmd in ("sair", "agora"):
                return cmd
            if cmd == "estatisticas":
                self.abrir_estatisticas()
            elif cmd == "painel":
                acao = self.abrir_painel()
                if acao in ("sair", "agora"):
                    return acao
                if acao == "resumo":
                    self.abrir_estatisticas()

    def estado_info(self):
        """(rótulo, segundos restantes, duração total) para o painel."""
        rotulos = {"estudo": "ESTUDANDO · PRÓXIMA PAUSA EM",
                   "pausa": "EM PAUSA · VOLTA AO ESTUDO EM",
                   "adiada": "PAUSA ADIADA · AVISO EM"}
        return rotulos[self.estado], max(0.0, self.limite - time.monotonic()), self.duracao

    def aplicar_config(self, novo: dict):
        inicializacao.sincronizar(novo["iniciar_com_windows"])

    def abrir_painel(self):
        try:
            import painel
            return painel.abrir(self.estado_info, self.cfg, self.aplicar_config)
        except Exception:
            logging.exception("Falha ao abrir o painel")
            return None

    def abrir_estatisticas(self):
        try:
            import estatisticas
            estatisticas.abrir(self.cfg["cor_destaque"])
        except Exception:
            logging.exception("Falha ao abrir as estatísticas")

    # -------------------------------------------------------------- pausa
    def pausa(self):
        """Executa o aviso (com adiamentos). Retorna "sair" se o app foi encerrado."""
        planejada = int(round(self.cfg["minutos_pausa"] * 60))
        sugestao = random.choice(textos.SUGESTOES)
        while True:
            if self.cfg["modo_aviso"] == "tela_cheia":
                acao, real, sair = self.aviso_tela_cheia(planejada, sugestao)
            else:
                acao, real, sair = self.aviso_notificacao(planejada, sugestao)
            self.registrar(planejada, real, acao)
            if sair:
                return "sair"
            if acao == "adiada":
                if self.esperar(self.cfg["adiar_minutos"] * 60, "adiada") == "sair":
                    return "sair"
                continue
            if acao == "feita":
                notificacoes.voltar_a_estudar(
                    self.cfg["som"], usar_toast=self.cfg["modo_aviso"] == "notificacao")
            return None

    def aviso_tela_cheia(self, planejada, sugestao):
        try:
            import overlay
            if self.cfg["som"]:
                notificacoes.som_curto()
            acao, real = overlay.mostrar(planejada, self.cfg["adiar_minutos"],
                                         self.cfg["cor_destaque"], sugestao)
            return acao, real, False
        except Exception:
            logging.exception("Falha na tela cheia; usando notificação")
            return self.aviso_notificacao(planejada, sugestao)

    def aviso_notificacao(self, planejada, sugestao):
        """Sem janela: avisa, espera a duração da pausa e assume que foi feita."""
        notificacoes.avisar(textos.TITULO_PAUSA,
                            "Descanse por %g min. %s" % (planejada / 60, sugestao), self.cfg["som"])
        inicio = time.monotonic()
        motivo = self.esperar(planejada, "pausa")
        real = int(min(planejada, time.monotonic() - inicio))
        if motivo == "sair":
            return "pulada", real, True
        return "feita", real, False

    @staticmethod
    def registrar(planejada, real, acao):
        try:
            historico.registrar(planejada, real, acao)
        except Exception:
            logging.exception("Falha ao gravar no histórico")


# -------------------------------------------------------------------- main
def _mostrar_erro(pasta: str) -> None:
    """Sem console (pythonw/.exe) um erro de inicialização seria invisível: avisa na tela."""
    try:
        import tkinter
        from tkinter import messagebox
        r = tkinter.Tk()
        r.withdraw()
        messagebox.showerror(sistema.NOME_APP, "O app não conseguiu iniciar.\n\n"
                             "Detalhes em:\n" + os.path.join(pasta, "erros.log"))
        r.destroy()
    except Exception:
        pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lembrete de pausas para estudar.")
    p.add_argument("--painel", action="store_true", help="abre o painel de controle")
    p.add_argument("--silencioso", action="store_true", help="inicia sem abrir o painel")
    p.add_argument("--estatisticas", action="store_true", help="abre o resumo do histórico")
    p.add_argument("--agora", action="store_true", help="dispara a pausa imediatamente")
    p.add_argument("--sair", action="store_true", help="encerra o app em execução")
    args = p.parse_args(argv)

    # Log só de erros, em arquivo criado sob demanda (pythonw não tem console).
    logging.basicConfig(level=logging.WARNING, handlers=[logging.FileHandler(
        os.path.join(sistema.pasta_app(), "erros.log"), encoding="utf-8", delay=True)],
        format="%(asctime)s %(levelname)s %(message)s")

    cmd = ("sair" if args.sair else "estatisticas" if args.estatisticas
           else "agora" if args.agora else "painel" if args.painel else None)
    alvo = cmd or ("ping" if args.silencioso else "painel")
    if enviar_comando(alvo):                   # já existe uma instância: só repassa o comando
        return 0
    if not sistema.obter_mutex():              # outra instância está iniciando agora
        for _ in range(10):
            time.sleep(0.3)
            if enviar_comando(alvo):
                break
        return 0
    if args.sair:                              # nada rodando para encerrar
        return 0

    sistema.definir_dpi()
    servidor = abrir_servidor()
    fila = queue.Queue()
    threading.Thread(target=escutar, args=(servidor, fila), daemon=True).start()
    if cmd:
        fila.put(cmd)
    elif not args.silencioso:
        fila.put("painel")                     # duplo clique: mostra o painel
    try:
        Ciclo(fila).executar()
    finally:
        servidor.close()
        try:
            os.remove(arquivo_porta())
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logging.exception("Erro fatal")
        _mostrar_erro(sistema.pasta_app())
        sys.exit(1)
