"""Notificações nativas do Windows e som curto (sem dependências extras).

O toast é exibido por um PowerShell oculto que roda e termina na hora do aviso;
nenhuma janela do app é aberta.
"""
import registro

import sistema
import textos


def escape(texto: str) -> str:
    """Escapa texto para XML (substitui html.escape, que custa RAM de import)."""
    return (texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))

# Identificador do Windows PowerShell 5.1: permite exibir toasts sem registrar um app.
_AUMID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


def som_curto() -> None:
    if not sistema.e_windows():
        return
    try:
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        registro.excecao("Falha ao tocar o som")


def toast(titulo: str, mensagem: str) -> bool:
    xml = ("<toast><visual><binding template=\"ToastGeneric\"><text>%s</text><text>%s</text>"
           "</binding></visual></toast>" % (escape(titulo), escape(mensagem)))
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType = WindowsRuntime] | Out-Null; "
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml('%s'); "
        "$t = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show($t)"
        % (sistema.aspas_ps(xml), _AUMID))
    return sistema.executar_powershell(script)


def avisar(titulo: str, mensagem: str, som: bool = True) -> None:
    """Mostra o toast; se falhar, ao menos toca o som para o aviso não passar em branco."""
    ok = toast(titulo, mensagem)
    if not ok:
        registro.aviso("Toast não exibido (PowerShell indisponível ou erro)")
    if som or not ok:
        som_curto()


def voltar_a_estudar(som: bool = True, usar_toast: bool = True) -> None:
    if usar_toast:
        avisar(textos.TITULO_VOLTAR, textos.MSG_VOLTAR, som)
    elif som:
        som_curto()
