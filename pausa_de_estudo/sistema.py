"""Utilidades de sistema (pasta do app, PowerShell, DPI e monitores).

Só usa a biblioteca padrão. Funções específicas do Windows retornam um
valor neutro em outros sistemas, para o código poder ser testado no Linux.
"""
import base64
import os
import subprocess
import sys

NOME_APP = "Pausa de Estudo"


def e_windows() -> bool:
    return sys.platform == "win32"


def pasta_app() -> str:
    """Pasta onde ficam config.json e historico.db (ao lado do app/.exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def executar_powershell(script: str, timeout: int = 20) -> bool:
    """Roda um script PowerShell oculto. Retorna True se terminou sem erro."""
    if not e_windows():
        return False
    codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        resultado = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-EncodedCommand", codificado],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return resultado.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def aspas_ps(texto: str) -> str:
    """Escapa texto para uso dentro de string PowerShell entre aspas simples."""
    return texto.replace("'", "''")


def definir_dpi() -> None:
    """Evita tela borrada/medidas erradas em monitores com escala > 100%."""
    if not e_windows():
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def listar_monitores():
    """Lista [(x, y, largura, altura)] de todos os monitores; o principal vem primeiro.

    Retorna [] fora do Windows ou em caso de falha (o chamador usa a tela padrão).
    """
    if not e_windows():
        return []
    import ctypes
    from ctypes import wintypes

    monitores = []
    proc = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

    def _cb(_hmon, _hdc, rect, _lparam):
        r = rect.contents
        monitores.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return 1

    try:
        enum = ctypes.windll.user32.EnumDisplayMonitors
        enum.argtypes = [ctypes.c_void_p, ctypes.c_void_p, proc, ctypes.c_void_p]
        enum.restype = ctypes.c_int
        enum(None, None, proc(_cb), None)
    except (AttributeError, OSError):
        return []
    # O monitor principal sempre está na origem (0, 0).
    monitores.sort(key=lambda m: (m[0], m[1]) != (0, 0))
    return monitores


_mutex = None   # mantém o mutex vivo enquanto o processo existir


def obter_mutex(nome: str = "Local\\PausaDeEstudo.Instancia") -> bool:
    """True se esta é a primeira instância (mutex nomeado do Windows, atômico).

    Fora do Windows sempre devolve True (a checagem é feita pela porta local).
    """
    global _mutex
    if not e_windows():
        return True
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    _mutex = k32.CreateMutexW(None, False, nome)
    return ctypes.get_last_error() != 183      # 183 = ERROR_ALREADY_EXISTS


def barra_escura(janela) -> None:
    """Barra de título escura (Windows 10 1903+ e 11). Melhor esforço."""
    if not e_windows():
        return
    import ctypes
    try:
        hwnd = ctypes.windll.user32.GetParent(janela.winfo_id())
        for atributo in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, atributo, ctypes.byref(ctypes.c_int(1)), 4)
    except (AttributeError, OSError):
        pass


_log_falha = None   # mantém aberto o arquivo do faulthandler


def instalar_diagnostico(caminho_log: str) -> None:
    """Registra em erros.log também falhas fatais (travamento do Python/Tk) e erros em threads.

    Sem console (pythonw/.exe) esses erros sumiriam sem deixar rastro.
    """
    import faulthandler
    import logging
    import threading
    global _log_falha
    try:
        _log_falha = open(caminho_log, "a", encoding="utf-8")
        faulthandler.enable(file=_log_falha, all_threads=True)
    except OSError:
        pass
    sys.excepthook = lambda t, v, tb: logging.critical("Erro não tratado", exc_info=(t, v, tb))
    threading.excepthook = lambda a: logging.error(
        "Erro em thread", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def proteger_tk() -> None:
    """Erros dentro de callbacks do Tk vão para o erros.log (sem console eles se perdiam)."""
    import logging
    import tkinter
    tkinter.Tk.report_callback_exception = lambda self, exc, val, tb: logging.error(
        "Erro em callback do Tk", exc_info=(exc, val, tb))
