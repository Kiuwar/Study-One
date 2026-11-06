"""Leitura e gravação do config.json (criado com valores padrão se faltar)."""
import json
import registro
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
    "verificar_atualizacoes": True,   # consulta o GitHub ao iniciar e a cada 24 h
    "ciclos_pausa_longa": 0,          # a cada N ciclos a pausa é longa (0 = desligado)
    "minutos_pausa_longa": 20,
    "nao_interromper_tela_cheia": True,   # adia a pausa se houver apresentação/jogo em tela cheia
    "meta_diaria_pausas": 0,              # 0 = sem meta
    "materias": [],                       # ex.: ["Direito Civil", "Penal"]
    "materia_atual": "",
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
        if chave in ("minutos_estudo", "minutos_pausa", "adiar_minutos", "minutos_pausa_longa"):
            ok = _numero_valido(valor)
        elif chave in ("ciclos_pausa_longa", "meta_diaria_pausas"):
            ok = isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= (
                24 if chave == "ciclos_pausa_longa" else 50)
        elif chave == "materias":
            ok = (isinstance(valor, list) and len(valor) <= 12 and
                  all(isinstance(m, str) and m.strip() and len(m) <= 40 for m in valor))
        elif chave == "materia_atual":
            ok = isinstance(valor, str) and len(valor) <= 40
        elif chave == "modo_aviso":
            ok = valor in MODOS
        elif chave == "cor_destaque":
            ok = valor in CORES
        else:  # booleanos
            ok = isinstance(valor, bool)
        if ok:
            cfg[chave] = valor
        else:
            registro.aviso("config.json: valor inválido em %r (%r); usando %r",
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
            registro.excecao("Não foi possível criar %s", caminho)
        return dict(PADRAO)
    try:
        with open(caminho, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            raise ValueError("o JSON precisa ser um objeto { ... }")
    except (OSError, ValueError) as erro:
        registro.aviso("config.json ilegível (%s); mantendo a configuração anterior", erro)
        return dict(fallback or PADRAO)
    return validar(dados)
