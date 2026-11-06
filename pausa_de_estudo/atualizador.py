"""Rede da atualização pelas Releases do GitHub (só biblioteca padrão).

Roda SEMPRE num processo filho curto (`main.py --tarefa verificar|baixar`, ver janelas.py): assim o
app em segundo plano nunca carrega urllib/ssl. Consulta a última release, compara com a versão
instalada e baixa o instalador conferindo o SHA-256. Nada é entregue sem o checksum bater.
"""
import hashlib
import json
import os
import re
import tempfile

from versao import VERSAO

# O repositório foi renomeado (Kiuwar/New -> Kiuwar/Study-One). O GitHub redireciona o nome antigo,
# mas os links de download vêm com o nome novo: aceitamos os dois, e só eles.
REPOS = ("Kiuwar/Study-One", "Kiuwar/New")
API = "https://api.github.com/repos/%s/releases/latest" % REPOS[0]
PREFIXOS_DOWNLOAD = tuple("https://github.com/%s/releases/download/" % r for r in REPOS)
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
    import urllib.request
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json, application/octet-stream",
        "User-Agent": "PausaDeEstudo/" + VERSAO})
    return urllib.request.urlopen(req, timeout=timeout)


def consultar(api: str = None, timeout: float = 10) -> dict:
    """Lê a última release publicada."""
    import urllib.error
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
    if info.get("url_sha") and info["url_sha"].startswith(PREFIXOS_DOWNLOAD):
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
    if not info["url"].startswith(PREFIXOS_DOWNLOAD):
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
