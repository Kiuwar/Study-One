"""Leitura e gravação do config.json (criado com valores padrão se faltar)."""
import json
import logging
import os

import sistema

PADRAO = {
    "minutos_estudo": 50,
    "minutos_pausa": 10,
    "modo_aviso": "tela_cheia",       # "tela_cheia" ou "notificacao"
    "adiar_minutos": 5,
    "som": True,
    "iniciar_com_windows": False,
    "cor_destaque": "ciano",          # ciano, violeta, verde ou magenta
}
MODOS = ("tela_cheia", "notificacao")
CORES = ("ciano", "violeta", "verde", "magenta")
LIMITE_MINUTOS = 24 * 60


def caminho_padrao() -> str:
    return os.path.join(sistema.pasta_app(), "config.json")


def _numero_valido(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= LIMITE_MINUTOS


def validar(dados: dict) -> dict:
    """Mescla `dados` com o padrão; campo inválido volta ao valor padrão."""
    cfg = dict(PADRAO)
    for chave, padrao in PADRAO.items():
        if chave not in dados:
            continue
        valor = dados[chave]
        if chave in ("minutos_estudo", "minutos_pausa", "adiar_minutos"):
            ok = _numero_valido(valor)
        elif chave == "modo_aviso":
            ok = valor in MODOS
        elif chave == "cor_destaque":
            ok = valor in CORES
        else:  # booleanos
            ok = isinstance(valor, bool)
        if ok:
            cfg[chave] = valor
        else:
            logging.warning("config.json: valor inválido em %r (%r); usando %r",
                            chave, valor, padrao)
    return cfg


def gravar(cfg: dict, caminho: str = None) -> None:
    caminho = caminho or caminho_padrao()
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, caminho)  # gravação atômica


def carregar(caminho: str = None, fallback: dict = None) -> dict:
    """Lê o config.json. Cria o arquivo se não existir.

    Se o JSON estiver quebrado, devolve `fallback` (última config válida)
    ou o padrão, sem sobrescrever o arquivo do usuário.
    """
    caminho = caminho or caminho_padrao()
    if not os.path.exists(caminho):
        try:
            gravar(dict(PADRAO), caminho)
        except OSError:
            logging.exception("Não foi possível criar %s", caminho)
        return dict(PADRAO)
    try:
        with open(caminho, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            raise ValueError("o JSON precisa ser um objeto { ... }")
    except (OSError, ValueError) as erro:
        logging.warning("config.json ilegível (%s); mantendo a configuração anterior", erro)
        return dict(fallback or PADRAO)
    return validar(dados)
