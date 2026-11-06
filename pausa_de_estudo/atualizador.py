"""Atualização do app pelas Releases do GitHub (só biblioteca padrão).

Fluxo: consulta a última release -> compara com a versão instalada -> baixa o
instalador -> confere o SHA-256 -> roda o instalador em modo silencioso e o app
encerra para ser substituído. Nada é executado sem o checksum bater.
"""
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import sistema
from versao import VERSAO

REPO = "Kiuwar/New"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
PREFIXO_DOWNLOAD = "https://github.com/%s/releases/download/" % REPO   # só baixa daqui
NOME_INSTALADOR = "PausaDeEstudo-Setup.exe"
INTERVALO_VERIFICACAO = 24 * 3600


class ErroAtualizacao(Exception):
    """Falha esperada (sem internet, sem checksum...), com texto pronto para o usuário."""


def versao_tupla(texto: str):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", texto or "")
    if not m:
        raise ErroAtualizacao("Número de versão inválido: %r" % (texto,))
    return tuple(int(x) for x in m.groups())


def ha_nova(info: dict, atual: str = VERSAO) -> bool:
    return versao_tupla(info["versao"]) > versao_tupla(atual)


def _abrir(url, timeout):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json, application/octet-stream",
        "User-Agent": "PausaDeEstudo/" + VERSAO})
    return urllib.request.urlopen(req, timeout=timeout)


def consultar(api: str = None, timeout: float = 10) -> dict:
    """Lê a última release publicada."""
    try:
        with _abrir(api or API, timeout) as resp:
            dados = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            raise ErroAtualizacao("Nenhuma versão pública encontrada. Se o repositório for "
                                  "privado, o app não consegue verificar.")
        raise ErroAtualizacao("O servidor de atualizações respondeu %d." % e.code)
    except (OSError, ValueError):          # URLError, timeout, JSON quebrado
        raise ErroAtualizacao("Não foi possível verificar (sem internet?).")
    tag = dados.get("tag_name", "")
    versao_tupla(tag)                      # valida o formato
    arquivos = {a.get("name"): a for a in dados.get("assets", [])}
    instalador = arquivos.get(NOME_INSTALADOR)
    if not instalador:
        raise ErroAtualizacao("A versão %s não tem o instalador anexado." % tag)
    digest = instalador.get("digest") or ""
    soma = arquivos.get(NOME_INSTALADOR + ".sha256")
    return {"versao": tag.lstrip("vV"), "url": instalador["browser_download_url"],
            "sha256": digest[7:] if digest.startswith("sha256:") else None,
            "url_sha": soma["browser_download_url"] if soma else None,
            "pagina": dados.get("html_url"), "notas": (dados.get("body") or "")[:600]}


def _sha_esperado(info: dict, timeout: float) -> str:
    if info.get("sha256"):
        return info["sha256"].strip().lower()
    if info.get("url_sha") and info["url_sha"].startswith(PREFIXO_DOWNLOAD):
        try:
            with _abrir(info["url_sha"], timeout) as resp:
                token = resp.read(512).decode("ascii", "ignore").split()[0].lower()
        except (OSError, IndexError):
            raise ErroAtualizacao("Não foi possível ler o checksum da atualização.")
        if re.fullmatch(r"[0-9a-f]{64}", token):
            return token
    raise ErroAtualizacao("A atualização não traz checksum SHA-256: não vou instalar.")


def baixar(info: dict, timeout: float = 30) -> str:
    """Baixa o instalador, confere o SHA-256 e devolve o caminho. Levanta ErroAtualizacao."""
    if not info["url"].startswith(PREFIXO_DOWNLOAD):
        raise ErroAtualizacao("Endereço de download fora do repositório oficial.")
    esperado = _sha_esperado(info, timeout)
    pasta = tempfile.mkdtemp(prefix="PausaDeEstudo-")
    caminho = os.path.join(pasta, NOME_INSTALADOR)
    soma = hashlib.sha256()
    try:
        with _abrir(info["url"], timeout) as resp, open(caminho, "wb") as f:
            while True:
                bloco = resp.read(64 * 1024)
                if not bloco:
                    break
                soma.update(bloco)
                f.write(bloco)
    except OSError:
        raise ErroAtualizacao("O download foi interrompido.")
    if soma.hexdigest() != esperado:
        os.remove(caminho)
        raise ErroAtualizacao("O arquivo baixado não confere com o checksum (descartado).")
    return caminho


def instalado() -> bool:
    """True se o app veio do instalador (há desinstalador ao lado do .exe)."""
    return os.path.exists(os.path.join(sistema.pasta_app(), "unins000.exe"))


def executar_instalador(caminho: str) -> None:
    subprocess.Popen([caminho, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


class Gerenciador:
    """Estado da atualização, atualizado por threads curtas (a interface só lê)."""

    def __init__(self, ao_encontrar=None):
        self._lock = threading.Lock()
        self._estado = {"fase": "ocioso", "versao": None, "msg": "", "caminho": None}
        self._info = None
        self._ultima = None
        self.ao_encontrar = ao_encontrar

    def estado(self) -> dict:
        with self._lock:
            return dict(self._estado)

    def _definir(self, **campos):
        with self._lock:
            self._estado.update(campos)

    def _ocupado(self) -> bool:
        return self.estado()["fase"] in ("verificando", "baixando")

    def verificar(self, manual: bool = False) -> None:
        if self._ocupado():
            return
        self._ultima = time.monotonic()
        self._definir(fase="verificando", msg="Procurando atualizações...")
        threading.Thread(target=self._verificar, args=(manual,), daemon=True).start()

    def verificar_se_preciso(self) -> None:
        if self._ultima is None or time.monotonic() - self._ultima > INTERVALO_VERIFICACAO:
            self.verificar()

    def _verificar(self, manual):
        try:
            info = consultar()
            self._info = info
            if ha_nova(info):
                self._definir(fase="disponivel", versao=info["versao"],
                              msg="Nova versão disponível: v%s" % info["versao"])
                if not manual and self.ao_encontrar:
                    self.ao_encontrar(info["versao"])
            else:
                self._definir(fase="atualizado", msg="Você está na versão mais recente (v%s)." % VERSAO)
        except ErroAtualizacao as e:
            self._definir(fase="erro", msg=str(e))
        except Exception:
            logging.exception("Falha ao verificar atualização")
            self._definir(fase="erro", msg="Erro inesperado ao verificar.")

    def instalar(self) -> None:
        """Baixa e prepara a instalação (fase final: "pronto"). Sem instalador local, abre a página."""
        if self.estado()["fase"] != "disponivel" or not self._info:
            return
        if not instalado():
            if self._info.get("pagina"):
                webbrowser.open(self._info["pagina"])
            self._definir(msg="Versão portátil: abri a página de download.")
            return
        self._definir(fase="baixando", msg="Baixando a atualização...")
        threading.Thread(target=self._baixar, daemon=True).start()

    def _baixar(self):
        try:
            self._definir(fase="pronto", caminho=baixar(self._info), msg="Pronto para instalar.")
        except ErroAtualizacao as e:
            self._definir(fase="erro", msg=str(e))
        except Exception:
            logging.exception("Falha ao baixar atualização")
            self._definir(fase="erro", msg="Erro inesperado ao baixar.")
