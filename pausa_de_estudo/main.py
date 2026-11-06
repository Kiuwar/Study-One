"""Pausa de Estudo — ponto de entrada.

Uso:
    python main.py                  inicia o app e abre o painel de controle
    python main.py --silencioso     inicia sem abrir o painel (usado no início com o Windows)
    python main.py --painel         abre o painel (inicia o app se não estiver rodando)
    python main.py --estatisticas   abre o resumo do histórico
    python main.py --agora          dispara a pausa imediatamente
    python main.py --sair           encerra o app em execução

O app em segundo plano (daemon) é leve: não carrega tkinter nem rede. Painel, tela de pausa e resumo
abrem como processos separados (`--janela`) e a verificação de atualização também (`--tarefa`);
eles terminam ao fechar e devolvem a memória. Detalhes do laço em ciclo.py.
"""
import os
import queue
import sys
import threading
import time

import ipc
import registro
import sistema


def _argumentos(argv):
    import argparse
    p = argparse.ArgumentParser(description="Lembrete de pausas para estudar.")
    p.add_argument("--painel", action="store_true", help="abre o painel de controle")
    p.add_argument("--silencioso", action="store_true", help="inicia sem abrir o painel")
    p.add_argument("--estatisticas", action="store_true", help="abre o resumo do histórico")
    p.add_argument("--agora", action="store_true", help="dispara a pausa imediatamente")
    p.add_argument("--sair", action="store_true", help="encerra o app em execução")
    # uso interno: processos filhos
    p.add_argument("--janela", choices=("painel", "pausa", "resumo"), help=argparse.SUPPRESS)
    p.add_argument("--tarefa", choices=("verificar", "baixar"), help=argparse.SUPPRESS)
    p.add_argument("--saida", help=argparse.SUPPRESS)
    p.add_argument("--planejada", type=int, default=600, help=argparse.SUPPRESS)
    p.add_argument("--adiar", type=float, default=5, help=argparse.SUPPRESS)
    p.add_argument("--cor", help=argparse.SUPPRESS)
    p.add_argument("--sugestao", default="", help=argparse.SUPPRESS)
    p.add_argument("--longa", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


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
    args = _argumentos(argv)

    registro.iniciar(os.path.join(sistema.pasta_app(), "erros.log"))   # só erros; sem `logging`
    sistema.instalar_diagnostico(os.path.join(sistema.pasta_app(), "erros.log"))

    if args.janela or args.tarefa:              # processo filho: nunca vira o app principal
        import janelas
        return janelas.executar(args)

    cmd = ("sair" if args.sair else "resumo" if args.estatisticas
           else "agora" if args.agora else "painel" if args.painel else None)
    alvo = cmd or ("ping" if args.silencioso else "painel")
    if alvo != "ping":
        sistema.permitir_foco()                 # o usuário acabou de abrir o app: libera o foco da janela
    if ipc.enviar(alvo):                        # já existe uma instância: só repassa o comando
        return 0
    if not sistema.obter_mutex():               # outra instância está iniciando agora
        for _ in range(10):
            time.sleep(0.3)
            if ipc.enviar(alvo):
                break
        return 0
    if args.sair:                               # nada rodando para encerrar
        return 0

    from ciclo import Ciclo
    sistema.definir_dpi()
    servidor, token = ipc.abrir_servidor()
    fila = queue.Queue()
    ciclo = Ciclo(fila)
    threading.Thread(target=ipc.servir, args=(servidor, token, ciclo.tratar), daemon=True).start()
    if cmd:
        fila.put(cmd)
    elif not args.silencioso:
        fila.put("painel")                      # duplo clique: mostra o painel
    try:
        ciclo.executar()
    finally:
        ciclo.encerrar_janelas()
        servidor.close()
        ipc.remover_registro()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        registro.excecao("Erro fatal")
        _mostrar_erro(sistema.pasta_app())
        sys.exit(1)
