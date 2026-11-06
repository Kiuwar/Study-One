"""Comunicação entre o app em segundo plano (daemon) e as janelas/comandos.

Socket local (127.0.0.1) em porta livre. O arquivo %TEMP%\\PausaDeEstudo.porta guarda
"porta token"; cada pedido é uma linha JSON {"cmd": ..., "token": ...} e a resposta é uma linha JSON.
O token impede que outros programas da máquina controlem o app.
"""
import json
import os
import socket

import sistema


def arquivo_porta() -> str:
    return os.path.join(sistema.pasta_temp(), "PausaDeEstudo.porta")


def abrir_servidor():
    """Abre o servidor em porta livre e registra "porta token". Retorna (socket, token)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    token = os.urandom(8).hex()
    with open(arquivo_porta(), "w", encoding="ascii") as f:
        f.write("%d %s" % (s.getsockname()[1], token))
    return s, token


def remover_registro() -> None:
    try:
        os.remove(arquivo_porta())
    except OSError:
        pass


def _ler_linha(conn, limite=65536) -> bytes:
    dados = b""
    while b"\n" not in dados and len(dados) < limite:
        bloco = conn.recv(4096)
        if not bloco:
            break
        dados += bloco
    return dados


def servir(servidor, token: str, tratar) -> None:
    """Thread bloqueada em accept(): 0% de CPU sem pedidos. `tratar(cmd, dados) -> dict`."""
    while True:
        try:
            conn, _ = servidor.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(2)
            try:
                req = json.loads(_ler_linha(conn).decode("utf-8", "ignore"))
                if str(req.get("token", "")) != token:
                    resp = {"ok": False, "erro": "token"}
                else:
                    resp = tratar(str(req.get("cmd", "")), req)
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
            except (OSError, ValueError, AttributeError):
                pass


def pedir(cmd: str, timeout: float = 3, **dados):
    """Envia um comando ao daemon. Retorna o dict de resposta, ou None se não há daemon."""
    try:
        with open(arquivo_porta(), encoding="ascii") as f:
            porta, token = f.read().split()
        with socket.create_connection(("127.0.0.1", int(porta)), timeout=timeout) as c:
            c.settimeout(timeout)
            c.sendall((json.dumps(dict(dados, cmd=cmd, token=token)) + "\n").encode("utf-8"))
            resp = json.loads(_ler_linha(c).decode("utf-8", "ignore"))
        return resp if isinstance(resp, dict) else None
    except (OSError, ValueError):
        return None


def enviar(cmd: str, **dados) -> bool:
    resp = pedir(cmd, **dados)
    return bool(resp and resp.get("ok"))
