"""Atalho na pasta Inicializar do Windows (início automático)."""
import logging
import os
import sys

import sistema

NOME_ATALHO = "Pausa de Estudo.lnk"


def caminho_atalho() -> str:
    base = os.environ.get("APPDATA", "")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", NOME_ATALHO)


def existe() -> bool:
    return os.path.exists(caminho_atalho())


def _alvo_e_argumentos():
    if getattr(sys, "frozen", False):          # .exe do PyInstaller
        return sys.executable, ""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable   # pythonw = sem console
    return exe, '"%s"' % os.path.join(sistema.pasta_app(), "main.py")


def criar() -> bool:
    alvo, args = _alvo_e_argumentos()
    q = sistema.aspas_ps
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
        "$s.TargetPath = '%s'; $s.Arguments = '%s'; $s.WorkingDirectory = '%s'; "
        "$s.WindowStyle = 7; $s.Description = '%s'; $s.Save()"
        % (q(caminho_atalho()), q(alvo), q(args), q(sistema.pasta_app()), q(sistema.NOME_APP)))
    return sistema.executar_powershell(script)


def remover() -> bool:
    try:
        os.remove(caminho_atalho())
        return True
    except FileNotFoundError:
        return True
    except OSError:
        logging.exception("Não foi possível remover o atalho de inicialização")
        return False


def sincronizar(ativo: bool) -> None:
    """Deixa o atalho de acordo com o config.json (cria ou remove só se preciso)."""
    if not sistema.e_windows():
        return
    if ativo and not existe():
        if not criar():
            logging.warning("Falha ao criar o atalho de inicialização")
    elif not ativo and existe():
        remover()
