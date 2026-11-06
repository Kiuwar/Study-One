"""Registro mínimo de erros em erros.log.

Substitui o módulo `logging` (custa ~2 MB de RAM só por importar), que o app em segundo plano
não precisa. Cada linha: data, nível e mensagem; exceções levam o traceback.
"""
import sys
import time

_caminho = None


def iniciar(caminho: str) -> None:
    global _caminho
    _caminho = caminho


def _escrever(nivel, mensagem, args, exc_info=None):
    try:
        texto = mensagem % args if args else str(mensagem)
    except (TypeError, ValueError):
        texto = str(mensagem)
    linha = "%s %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), nivel, texto)
    if exc_info and exc_info[0] is not None:
        import traceback                      # só quando há erro de fato
        linha += "".join(traceback.format_exception(*exc_info))
    if _caminho:
        try:
            with open(_caminho, "a", encoding="utf-8") as f:
                f.write(linha)
        except OSError:
            pass


def aviso(mensagem, *args):
    _escrever("WARNING", mensagem, args)


def erro(mensagem, *args, exc_info=None):
    _escrever("ERROR", mensagem, args, exc_info)


def excecao(mensagem, *args):
    """Dentro de um `except`: registra a mensagem com o traceback do erro atual."""
    _escrever("ERROR", mensagem, args, sys.exc_info())


def critico(mensagem, *args, exc_info=None):
    _escrever("CRITICAL", mensagem, args, exc_info)
