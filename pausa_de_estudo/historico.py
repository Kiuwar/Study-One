"""Histórico dos avisos em SQLite.

A conexão é aberta só para gravar/ler e fechada logo depois; nada fica em memória.
"""
from contextlib import closing
from datetime import date, datetime, timedelta

import sistema

ACOES = ("feita", "adiada", "pulada")

_SQL = """
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT NOT NULL,                 -- 'AAAA-MM-DD HH:MM:SS' (hora local)
    duracao_planejada_s INTEGER NOT NULL,
    duracao_real_s INTEGER NOT NULL,
    acao TEXT NOT NULL CHECK (acao IN ('feita', 'adiada', 'pulada')),
    materia TEXT NOT NULL DEFAULT '',        -- matéria ativa quando a pausa começou
    estudo_s INTEGER NOT NULL DEFAULT 0      -- segundos de estudo antes desta pausa
);
CREATE INDEX IF NOT EXISTS idx_avisos_data ON avisos (data_hora);
"""


def caminho_padrao() -> str:
    import os
    return os.path.join(sistema.pasta_app(), "historico.db")


def _conectar(caminho: str = None):
    import sqlite3          # sob demanda: o app em segundo plano só carrega isto ao gravar/ler
    conn = sqlite3.connect(caminho or caminho_padrao(), timeout=5)
    conn.executescript(_SQL)
    colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(avisos)")}
    for nome, definicao in (("materia", "TEXT NOT NULL DEFAULT ''"),
                            ("estudo_s", "INTEGER NOT NULL DEFAULT 0")):
        if nome not in colunas:                       # banco criado por versões anteriores
            conn.execute("ALTER TABLE avisos ADD COLUMN %s %s" % (nome, definicao))
    conn.commit()
    return conn


def registrar(planejada_s, real_s, acao, quando: datetime = None, caminho: str = None,
              materia: str = "", estudo_s: int = 0) -> None:
    if acao not in ACOES:
        raise ValueError(f"ação inválida: {acao!r}")
    quando = quando or datetime.now()
    with closing(_conectar(caminho)) as conn, conn:
        conn.execute(
            "INSERT INTO avisos (data_hora, duracao_planejada_s, duracao_real_s, acao, materia, estudo_s) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (quando.strftime("%Y-%m-%d %H:%M:%S"), int(planejada_s), int(real_s), acao,
             materia or "", int(estudo_s)))


def resumo_dias(n: int = 7, hoje: date = None, caminho: str = None) -> list:
    """Resumo dos últimos `n` dias (inclui hoje), do mais antigo ao mais recente."""
    hoje = hoje or date.today()
    dias = [hoje - timedelta(days=i) for i in range(n - 1, -1, -1)]
    saida = {d.isoformat(): {"data": d, "feita": 0, "adiada": 0, "pulada": 0,
                             "total": 0, "segundos_descanso": 0} for d in dias}
    with closing(_conectar(caminho)) as conn:
        linhas = conn.execute(
            "SELECT substr(data_hora, 1, 10), acao, COUNT(*), COALESCE(SUM(duracao_real_s), 0) "
            "FROM avisos WHERE data_hora >= ? AND data_hora < ? GROUP BY 1, 2",
            (dias[0].isoformat() + " 00:00:00",
             (hoje + timedelta(days=1)).isoformat() + " 00:00:00")).fetchall()
    for dia, acao, qtd, seg in linhas:
        item = saida.get(dia)
        if item and acao in ACOES:
            item[acao] += qtd
            item["total"] += qtd
            item["segundos_descanso"] += seg
    return [saida[d.isoformat()] for d in dias]


def resumo_dia(hoje: date = None, caminho: str = None) -> dict:
    return resumo_dias(1, hoje, caminho)[0]


def somar(dias: list) -> dict:
    total = {"feita": 0, "adiada": 0, "pulada": 0, "total": 0, "segundos_descanso": 0}
    for d in dias:
        for chave in total:
            total[chave] += d[chave]
    return total


def sequencia_dias(hoje: date = None, caminho: str = None) -> int:
    """Dias seguidos (até hoje, ou até ontem se hoje ainda não teve pausa) com ao menos 1 pausa feita."""
    hoje = hoje or date.today()
    with closing(_conectar(caminho)) as conn:
        linhas = conn.execute(
            "SELECT DISTINCT substr(data_hora, 1, 10) FROM avisos WHERE acao = 'feita' "
            "ORDER BY 1 DESC LIMIT 400").fetchall()
    dias = {date.fromisoformat(r[0]) for r in linhas}
    dia = hoje if hoje in dias else hoje - timedelta(days=1)
    n = 0
    while dia in dias:
        n += 1
        dia -= timedelta(days=1)
    return n


def exportar_csv(destino: str, caminho: str = None) -> int:
    """Grava todo o histórico em CSV (separador ';' e UTF-8 com BOM: abre certo no Excel pt-BR)."""
    import csv
    with closing(_conectar(caminho)) as conn:
        linhas = conn.execute("SELECT data_hora, duracao_planejada_s, duracao_real_s, acao, materia, "
                              "estudo_s FROM avisos ORDER BY id").fetchall()
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["data_hora", "duracao_planejada_s", "duracao_real_s", "acao", "materia", "estudo_s"])
        w.writerows(linhas)
    return len(linhas)


def resumo_materias(n: int = 7, hoje: date = None, caminho: str = None) -> list:
    """Estudo por matéria nos últimos `n` dias: [(materia, pausas_feitas, estudo_s)], maior estudo primeiro."""
    hoje = hoje or date.today()
    inicio = (hoje - timedelta(days=n - 1)).isoformat() + " 00:00:00"
    fim = (hoje + timedelta(days=1)).isoformat() + " 00:00:00"
    with closing(_conectar(caminho)) as conn:
        linhas = conn.execute(
            "SELECT materia, SUM(acao = 'feita'), SUM(estudo_s) FROM avisos "
            "WHERE data_hora >= ? AND data_hora < ? GROUP BY materia ORDER BY 3 DESC, 1",
            (inicio, fim)).fetchall()
    return [(m or "Sem matéria", int(f or 0), int(e or 0)) for m, f, e in linhas if (e or f)]
