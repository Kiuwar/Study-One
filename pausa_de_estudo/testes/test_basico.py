"""Testes da lógica sem interface:  python -m unittest discover -s testes"""
import json
import os
import queue
import sys
import tempfile
import time
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import historico
import atualizador
import ciclo
import ipc
import sistema
import versao


class TesteConfig(unittest.TestCase):
    def test_cria_arquivo_com_padrao(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "config.json")
            cfg = config.carregar(caminho)
            self.assertEqual(cfg["minutos_estudo"], 50)
            self.assertEqual(cfg["minutos_pausa"], 10)
            self.assertTrue(os.path.exists(caminho))

    def test_mudanca_vale_na_proxima_leitura(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "config.json")
            config.carregar(caminho)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"minutos_estudo": 25}, f)
            self.assertEqual(config.carregar(caminho)["minutos_estudo"], 25)

    def test_invalido_volta_ao_padrao_e_json_quebrado_mantem_anterior(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "config.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump({"minutos_estudo": -3, "modo_aviso": "xyz"}, f)
            cfg = config.carregar(caminho)
            self.assertEqual((cfg["minutos_estudo"], cfg["modo_aviso"]), (50, "tela_cheia"))
            with open(caminho, "w", encoding="utf-8") as f:
                f.write("{ quebrado")
            anterior = dict(cfg, minutos_estudo=30)
            self.assertEqual(config.carregar(caminho, fallback=anterior)["minutos_estudo"], 30)
            with open(caminho, encoding="utf-8") as f:
                self.assertEqual(f.read(), "{ quebrado")        # arquivo do usuário intacto


class TesteHistorico(unittest.TestCase):
    def test_registro_resumo_e_persistencia(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "h.db")
            hoje = date(2026, 11, 6)
            historico.registrar(600, 600, "feita", datetime(2026, 11, 6, 10, 0), db)
            historico.registrar(600, 0, "adiada", datetime(2026, 11, 6, 11, 0), db)
            historico.registrar(600, 120, "pulada", datetime(2026, 11, 1, 9, 0), db)
            historico.registrar(600, 600, "feita", datetime(2026, 10, 1, 9, 0), db)   # fora dos 7 dias
            dia = historico.resumo_dia(hoje, db)
            self.assertEqual((dia["feita"], dia["adiada"], dia["total"]), (1, 1, 2))
            semana = historico.resumo_dias(7, hoje, db)
            self.assertEqual(len(semana), 7)
            tot = historico.somar(semana)
            self.assertEqual((tot["total"], tot["pulada"], tot["segundos_descanso"]), (3, 1, 720))
            self.assertEqual(historico.resumo_dia(hoje, db)["total"], 2)   # nova conexão = reinício
            with self.assertRaises(ValueError):
                historico.registrar(1, 1, "outra", caminho=db)


def _json_em(caminho, dados):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f)


class TesteCiclo(unittest.TestCase):
    def setUp(self):
        self.f = queue.Queue()
        self.c = ciclo.Ciclo(self.f, ocupado_fn=lambda: False)
        self.c.registrar = lambda *a, **k: None          # sem tocar no banco real
        self._voltar = ciclo.notificacoes.voltar_a_estudar
        self._avisar = ciclo.notificacoes.avisar
        ciclo.notificacoes.voltar_a_estudar = lambda *a, **k: None
        self.avisos = []
        ciclo.notificacoes.avisar = lambda t, m, som=True: self.avisos.append(t)

    def tearDown(self):
        ciclo.notificacoes.voltar_a_estudar = self._voltar
        ciclo.notificacoes.avisar = self._avisar

    def test_esperar_respeita_tempo_e_comandos(self):
        t = time.monotonic()
        self.assertEqual(self.c.esperar(0.2), "tempo")
        self.assertGreaterEqual(time.monotonic() - t, 0.19)
        self.f.put("sair")
        self.assertEqual(self.c.esperar(5), "sair")
        self.f.put("agora")
        self.assertEqual(self.c.esperar(5), "agora")

    def test_adiar_registra_e_reagenda(self):
        gravados = []
        self.c.cfg.update(modo_aviso="tela_cheia", adiar_minutos=0.001, minutos_pausa=1,
                          nao_interromper_tela_cheia=False)
        respostas = iter([("adiada", 0, False), ("feita", 60, False)])
        self.c.aviso_tela_cheia = lambda p, s: next(respostas)
        self.c.registrar = lambda p, r, a, estudo_s=0: gravados.append((a, estudo_s))
        self.c._feitas = (date.today(), 0)
        self.assertIsNone(self.c.pausa(estudo_s=300))
        self.assertEqual(gravados, [("adiada", 300), ("feita", 0)])   # estudo contado uma vez só

    def test_pausa_longa_usa_a_duracao_longa(self):
        self.c.cfg.update(modo_aviso="tela_cheia", minutos_pausa=10, minutos_pausa_longa=20,
                          nao_interromper_tela_cheia=False)
        vistos = []
        self.c.aviso_tela_cheia = lambda p, s: (vistos.append((p, self.c.longa)), ("pulada", 0, False))[1]
        self.c.pausa(longa=True)
        self.c.pausa(longa=False)
        self.assertEqual(vistos, [(1200, True), (600, False)])

    def test_estado_e_comandos_pelo_ipc_logico(self):
        self.c.esperar(0.05, "pausa")
        r = self.c.tratar("estado", {})
        self.assertTrue(r["ok"])
        self.assertIn("EM PAUSA", r["rotulo"])
        for chave in ("restante", "total", "suspenso", "nunca_iniciado", "foco", "versao", "materia",
                      "meta", "feitas", "atualizacao"):
            self.assertIn(chave, r)
        self.assertTrue(self.c.tratar("materia", {"nome": "Penal"})["ok"])
        self.assertEqual(self.c.tratar("estado", {})["materia"], "Penal")
        self.assertFalse(self.c.tratar("inexistente", {})["ok"])
        self.c.tratar("painel", {})
        self.assertEqual(self.f.get_nowait(), "painel")

    def test_suspender_congela_e_retomar_continua(self):
        import threading
        resultado, t0 = [], time.monotonic()
        th = threading.Thread(target=lambda: resultado.append(self.c.esperar(0.6)))
        th.start()
        time.sleep(0.15)
        self.assertTrue(self.c.tratar("suspender", {})["suspenso"])    # ~0,45 s restantes
        time.sleep(0.8)                                                # passa do prazo original
        self.assertTrue(th.is_alive())                                 # contagem suspensa
        self.assertIn("SUSPENSA", self.c.estado_info()[0])
        self.assertFalse(self.c.tratar("suspender", {})["suspenso"])   # retoma: acorda o laço
        th.join(3)
        self.assertEqual(resultado, ["tempo"])
        self.assertGreaterEqual(time.monotonic() - t0, 0.15 + 0.8 + 0.35)

    def test_esperar_com_suspenso_inicial_espera_o_usuario(self):
        import threading
        resultado = []
        th = threading.Thread(target=lambda: resultado.append(self.c.esperar(0.2, suspenso_inicial=True)))
        th.start()
        time.sleep(0.4)                                     # passa do prazo nominal
        self.assertTrue(th.is_alive())                       # nasceu suspensa: não contou sozinha
        self.assertEqual(self.c.estado_info()[1], self.c.duracao)    # nada decorrido
        self.assertIn("AGUARDANDO INÍCIO", self.c.estado_info()[0])
        self.c.iniciar_contagem()
        th.join(3)
        self.assertEqual(resultado, ["tempo"])
        self.assertFalse(self.c.nunca_iniciado)

    def test_iniciar_contagem_pelo_tratar(self):
        import threading
        resultado = []
        th = threading.Thread(target=lambda: resultado.append(self.c.esperar(0.2, suspenso_inicial=True)))
        th.start()
        time.sleep(0.1)
        self.assertTrue(self.c.tratar("iniciar", {})["ok"])
        th.join(3)
        self.assertEqual(resultado, ["tempo"])
        self.assertFalse(self.c.tratar("estado", {})["nunca_iniciado"])

    def test_reiniciar_contagem_volta_ao_inicio(self):
        self.c.esperar(0.05)
        self.c.duracao, self.c.limite = 100.0, time.monotonic() + 10
        self.c.tratar("reiniciar", {})
        self.assertGreater(self.c.estado_info()[1], 99)
        self.c.alternar_suspensao()
        self.c.restante_suspenso = 5
        self.c.reiniciar_contagem()
        self.assertEqual(self.c.estado_info()[1], 100.0)

    def test_nao_interrompe_tela_cheia_e_tenta_de_novo(self):
        ocupado = iter([True, True, False])
        self.c.ocupado_fn = lambda: next(ocupado)
        ciclo.ESPERA_OCUPADO = 0.05
        self.c.cfg.update(modo_aviso="tela_cheia", nao_interromper_tela_cheia=True)
        chamadas = []
        self.c.aviso_tela_cheia = lambda p, s: (chamadas.append(time.monotonic()), ("pulada", 0, False))[1]
        self.assertIsNone(self.c.pausa())
        self.assertEqual(len(chamadas), 1)                  # só abre depois de liberar
        self.assertEqual(self.avisos.count("Pausa adiada"), 1)   # avisou uma única vez

    def test_pausar_agora_ignora_a_checagem_de_tela_cheia(self):
        self.c.ocupado_fn = lambda: True
        self.c.cfg.update(modo_aviso="tela_cheia", nao_interromper_tela_cheia=True)
        self.c.aviso_tela_cheia = lambda p, s: ("pulada", 0, False)
        self.assertIsNone(self.c.pausa(forcar=True))        # não trava esperando

    def test_meta_diaria_avisa_uma_vez(self):
        self.c.cfg.update(meta_diaria_pausas=2)
        self.c._feitas = (date.today(), 0)
        self.c.contar_feita()
        self.assertNotIn("Meta do dia atingida", self.avisos)
        self.c.contar_feita()
        self.c.contar_feita()
        self.assertEqual(self.avisos.count("Meta do dia atingida"), 1)

    def test_tela_cheia_como_processo_filho(self):
        class Proc:
            terminou = False

            def poll(self):
                return None

            def terminate(self):
                self.terminou = True

        def abrir(nome, extras=None):
            saida = extras[extras.index("--saida") + 1]
            _json_em(saida, {"acao": "adiada", "real": 0})
            self.f.put("fim:pausa")
            return Proc()
        self.c.abrir_janela = abrir
        self.assertEqual(self.c.aviso_tela_cheia(60, "x"), ("adiada", 0, False))

    def test_sair_durante_a_tela_cheia_encerra_o_filho(self):
        proc = type("P", (), {"terminou": False, "poll": lambda s: None,
                              "terminate": lambda s: setattr(s, "terminou", True)})()
        self.c.abrir_janela = lambda nome, extras=None: proc
        self.f.put("sair")
        self.assertEqual(self.c.aviso_tela_cheia(60, "x"), ("pulada", 0, True))
        self.assertTrue(proc.terminou)

    def test_filho_sem_resultado_cai_para_notificacao(self):
        proc = type("P", (), {"poll": lambda s: None})()
        self.c.abrir_janela = lambda nome, extras=None: (self.f.put("fim:pausa"), proc)[1]
        self.c.aviso_notificacao = lambda p, s: ("feita", p, False)
        self.assertEqual(self.c.aviso_tela_cheia(60, "x"), ("feita", 60, False))

    def test_resultado_da_atualizacao_vem_do_processo_filho(self):
        a = self.c.atualizacao
        with tempfile.TemporaryDirectory() as d:
            for res, fase in (({"ok": True, "nova": True, "info": {"versao": "9.9.9", "pagina": "x"}}, "disponivel"),
                              ({"ok": True, "nova": False, "info": {"versao": "1.0.0"}}, "atualizado"),
                              ({"ok": False, "erro": "sem internet"}, "erro")):
                caminho = os.path.join(d, "r.json")
                _json_em(caminho, res)
                a._saidas["verificar"], a._manual = caminho, False
                a.concluir("verificar")
                self.assertEqual(a.estado()["fase"], fase)
        self.assertIn("Atualização disponível", self.avisos)


class TesteIPC(unittest.TestCase):
    def setUp(self):
        import threading
        self._antes = ipc.arquivo_porta
        ipc.arquivo_porta = lambda: os.path.join(tempfile.gettempdir(), "teste_pausa.porta")
        self.f = queue.Queue()
        self.c = ciclo.Ciclo(self.f)
        self.srv, self.token = ipc.abrir_servidor()
        threading.Thread(target=ipc.servir, args=(self.srv, self.token, self.c.tratar), daemon=True).start()

    def tearDown(self):
        self.srv.close()
        ipc.remover_registro()
        ipc.arquivo_porta = self._antes

    def test_sem_servidor_nao_ha_resposta(self):
        ipc.remover_registro()
        self.assertIsNone(ipc.pedir("ping"))
        self.assertFalse(ipc.enviar("painel"))

    def test_comandos_e_estado(self):
        self.assertTrue(ipc.enviar("ping"))
        self.assertTrue(ipc.enviar("painel"))
        self.assertEqual(self.f.get(timeout=2), "painel")
        self.assertEqual(ipc.pedir("estado")["versao"], versao.VERSAO)

    def test_token_errado_e_recusado(self):
        import socket
        porta = int(open(ipc.arquivo_porta()).read().split()[0])
        with socket.create_connection(("127.0.0.1", porta), timeout=2) as c:
            c.sendall(b'{"cmd": "sair", "token": "errado"}\n')
            resposta = json.loads(c.recv(1024))
        self.assertFalse(resposta["ok"])
        self.assertTrue(self.f.empty())


class TesteNovidades(unittest.TestCase):
    def test_config_novas_chaves(self):
        cfg = config.validar({"ciclos_pausa_longa": 4, "minutos_pausa_longa": 15, "meta_diaria_pausas": 6,
                              "verificar_atualizacoes": False, "materias": ["Civil", "Penal"],
                              "materia_atual": "Civil", "nao_interromper_tela_cheia": False})
        self.assertEqual((cfg["ciclos_pausa_longa"], cfg["minutos_pausa_longa"], cfg["meta_diaria_pausas"],
                          cfg["verificar_atualizacoes"], cfg["materias"], cfg["nao_interromper_tela_cheia"]),
                         (4, 15, 6, False, ["Civil", "Penal"], False))
        ruim = config.validar({"ciclos_pausa_longa": -1, "minutos_pausa_longa": 0, "meta_diaria_pausas": 99,
                               "materias": ["", 3], "materia_atual": 5})
        self.assertEqual((ruim["ciclos_pausa_longa"], ruim["minutos_pausa_longa"], ruim["meta_diaria_pausas"],
                          ruim["materias"], ruim["materia_atual"]), (0, 20, 0, [], ""))

    def test_sequencia_de_dias(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "h.db")
            hoje = date(2026, 11, 6)
            for dia in (6, 5, 4, 2):                         # lacuna no dia 3
                historico.registrar(600, 600, "feita", datetime(2026, 11, dia, 10), db)
            historico.registrar(600, 0, "pulada", datetime(2026, 11, 3, 10), db)   # não conta
            self.assertEqual(historico.sequencia_dias(hoje, db), 3)
            self.assertEqual(historico.sequencia_dias(date(2026, 11, 7), db), 3)   # ontem conta
            self.assertEqual(historico.sequencia_dias(date(2026, 11, 9), db), 0)

    def test_migracao_do_banco_antigo_e_materias(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "velho.db")
            conn = sqlite3.connect(db)                       # formato da v1.2 (sem materia/estudo_s)
            conn.execute("CREATE TABLE avisos (id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT NOT NULL, "
                         "duracao_planejada_s INTEGER NOT NULL, duracao_real_s INTEGER NOT NULL, "
                         "acao TEXT NOT NULL CHECK (acao IN ('feita', 'adiada', 'pulada')))")
            conn.execute("INSERT INTO avisos VALUES (1, '2026-11-06 09:00:00', 600, 600, 'feita')")
            conn.commit()
            conn.close()
            historico.registrar(600, 600, "feita", datetime(2026, 11, 6, 10), db, materia="Civil", estudo_s=3000)
            historico.registrar(600, 0, "adiada", datetime(2026, 11, 6, 11), db, materia="Civil")
            historico.registrar(600, 600, "feita", datetime(2026, 11, 5, 10), db, materia="Penal", estudo_s=1800)
            self.assertEqual(historico.resumo_dia(date(2026, 11, 6), db)["feita"], 2)   # dado antigo preservado
            self.assertEqual(historico.resumo_materias(7, date(2026, 11, 6), db),
                             [("Civil", 1, 3000), ("Penal", 1, 1800), ("Sem matéria", 1, 0)])
            historico.registrar(1, 1, "pulada", caminho=db)   # chamada antiga (sem matéria) continua válida

    def test_exportar_csv(self):
        with tempfile.TemporaryDirectory() as d:
            db, csv_ = os.path.join(d, "h.db"), os.path.join(d, "h.csv")
            historico.registrar(600, 600, "feita", datetime(2026, 11, 6, 10), db, materia="Civil", estudo_s=3000)
            historico.registrar(600, 0, "adiada", datetime(2026, 11, 6, 11), db)
            self.assertEqual(historico.exportar_csv(csv_, db), 2)
            with open(csv_, encoding="utf-8-sig") as f:
                linhas = f.read().splitlines()
            self.assertEqual(linhas[0], "data_hora;duracao_planejada_s;duracao_real_s;acao;materia;estudo_s")
            self.assertEqual(linhas[1], "2026-11-06 10:00:00;600;600;feita;Civil;3000")

    def test_ocupado_tela_cheia_fora_do_windows(self):
        self.assertFalse(sistema.ocupado_tela_cheia())


class TesteAtualizador(unittest.TestCase):
    CONTEUDO = b"MZ-instalador-falso" * 1000

    def setUp(self):
        import hashlib
        import http.server
        import threading
        teste = self
        self.sha = hashlib.sha256(self.CONTEUDO).hexdigest()
        self.modo = {"sha": "ok", "versao": "v9.0.0", "digest": True}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                base = "http://127.0.0.1:%d/dl/" % self.server.server_port
                if self.path == "/api":
                    ativos = [{"name": atualizador.NOME_INSTALADOR,
                               "browser_download_url": base + atualizador.NOME_INSTALADOR}]
                    if teste.modo["digest"]:
                        ativos[0]["digest"] = "sha256:" + teste.sha
                    else:
                        ativos.append({"name": atualizador.NOME_INSTALADOR + ".sha256",
                                       "browser_download_url": base + "soma.sha256"})
                    corpo = json.dumps({"tag_name": teste.modo["versao"], "assets": ativos,
                                        "html_url": "http://x/y", "body": "notas"}).encode()
                elif self.path == "/dl/" + atualizador.NOME_INSTALADOR:
                    corpo = teste.CONTEUDO
                elif self.path == "/dl/soma.sha256":
                    corpo = (teste.sha + "  PausaDeEstudo-Setup.exe\n").encode()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.api = "http://127.0.0.1:%d/api" % self.srv.server_port
        self._prefixos = atualizador.PREFIXOS_DOWNLOAD
        atualizador.PREFIXOS_DOWNLOAD = ("http://127.0.0.1:%d/dl/" % self.srv.server_port,)

    def tearDown(self):
        atualizador.PREFIXOS_DOWNLOAD = self._prefixos
        self.srv.shutdown()
        self.srv.server_close()

    def test_versoes(self):
        self.assertTrue(atualizador.ha_nova({"versao": "1.10.0"}, "1.9.9"))
        self.assertFalse(atualizador.ha_nova({"versao": "1.1.0"}, "1.1.0"))
        self.assertFalse(atualizador.ha_nova({"versao": "1.0.9"}, "1.1.0"))

    def test_consulta_download_e_checksum(self):
        info = atualizador.consultar(self.api)
        self.assertEqual(info["versao"], "9.0.0")
        self.assertTrue(atualizador.ha_nova(info))
        caminho = atualizador.baixar(info)
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), self.CONTEUDO)

    def test_checksum_pelo_arquivo_sha256(self):
        self.modo["digest"] = False
        caminho = atualizador.baixar(atualizador.consultar(self.api))
        self.assertTrue(os.path.exists(caminho))

    def test_recusa_checksum_errado_url_estranha_e_sem_checksum(self):
        info = atualizador.consultar(self.api)
        with self.assertRaises(atualizador.ErroAtualizacao):
            atualizador.baixar(dict(info, sha256="0" * 64))
        with self.assertRaises(atualizador.ErroAtualizacao):
            atualizador.baixar(dict(info, url="http://evil.example/Setup.exe"))
        with self.assertRaises(atualizador.ErroAtualizacao):
            atualizador.baixar(dict(info, sha256=None, url_sha=None))

    def test_aceita_o_nome_novo_e_o_antigo_do_repositorio(self):
        for repo, ok in (("Kiuwar/Study-One", True), ("Kiuwar/New", True), ("Outro/New", False),
                         ("Kiuwar/Study-One.evil", False)):
            url = "https://github.com/%s/releases/download/v1/PausaDeEstudo-Setup.exe" % repo
            self.assertEqual(url.startswith(self._prefixos), ok, repo)

    def test_sem_servidor_vira_erro_amigavel(self):
        self.srv.shutdown()
        self.srv.server_close()
        with self.assertRaises(atualizador.ErroAtualizacao):
            atualizador.consultar(self.api, timeout=2)
        self.srv.server_close()
        self.srv = type("X", (), {"shutdown": lambda s: None, "server_close": lambda s: None})()


if __name__ == "__main__":
    unittest.main()
