"""Processos filhos do app: janelas (painel, pausa, resumo) e tarefas de rede.

O app em segundo plano (daemon) fica sem tkinter e sem urllib/ssl; cada janela ou tarefa roda
num processo próprio que termina ao fechar, devolvendo a memória ao sistema.
"""
import json
import registro
import threading

import sistema


def lancar_vigiado(argumentos: list, fila, evento: str):
    """Dispara um filho e coloca `evento` na fila quando ele terminar."""
    proc = sistema.lancar_filho(argumentos)
    threading.Thread(target=lambda: (proc.wait(), fila.put(evento)), daemon=True).start()
    return proc


def _gravar_saida(caminho, dados: dict) -> None:
    if caminho:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f)


def _daemon_sumiu():
    """Função para as janelas: True depois de 3 falhas seguidas ao falar com o app (janela órfã)."""
    import ipc
    falhas = [0]

    def verificar() -> bool:
        falhas[0] = falhas[0] + 1 if ipc.pedir("ping", timeout=1.5) is None else 0
        return falhas[0] >= 3
    return verificar


def _tarefa(args) -> int:
    import atualizador
    try:
        info = atualizador.consultar()
        if args.tarefa == "verificar":
            resultado = {"ok": True, "nova": atualizador.ha_nova(info), "info": info}
        elif not atualizador.ha_nova(info):
            resultado = {"ok": False, "erro": "O app já está na versão mais recente."}
        else:
            resultado = {"ok": True, "caminho": atualizador.baixar(info), "info": info}
    except atualizador.ErroAtualizacao as e:
        resultado = {"ok": False, "erro": str(e)}
    except Exception:
        registro.excecao("Falha na tarefa %s", args.tarefa)
        resultado = {"ok": False, "erro": "Erro inesperado na atualização."}
    _gravar_saida(args.saida, resultado)
    return 0


def executar(args) -> int:
    """Ponto de entrada dos processos filhos (`--janela` ou `--tarefa`)."""
    if args.tarefa:
        return _tarefa(args)
    import config
    cfg = config.carregar()
    if args.janela == "painel":
        import painel
        painel.abrir()
    elif args.janela == "resumo":
        import estatisticas
        estatisticas.abrir(cfg["cor_destaque"], _daemon_sumiu())
    elif args.janela == "pausa":
        import overlay
        acao, real = overlay.mostrar(args.planejada, args.adiar, args.cor or cfg["cor_destaque"],
                                     args.sugestao, args.longa, _daemon_sumiu())
        _gravar_saida(args.saida, {"acao": acao, "real": real})
    else:
        return 2
    return 0
