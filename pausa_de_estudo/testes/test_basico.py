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
import main


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


class TesteCiclo(unittest.TestCase):
    def test_esperar_respeita_tempo_e_comandos(self):
        f = queue.Queue()
        c = main.Ciclo(f)
        t = time.monotonic()
        self.assertEqual(c.esperar(0.2), "tempo")
        self.assertGreaterEqual(time.monotonic() - t, 0.19)
        f.put("sair")
        self.assertEqual(c.esperar(5), "sair")
        f.put("agora")
        self.assertEqual(c.esperar(5), "agora")

    def test_adiar_registra_e_reagenda(self):
        gravados, ciclo = [], main.Ciclo(queue.Queue())
        ciclo.cfg.update(modo_aviso="tela_cheia", adiar_minutos=0.001, minutos_pausa=1)
        respostas = iter([("adiada", 0, False), ("feita", 60, False)])
        ciclo.aviso_tela_cheia = lambda p, s: next(respostas)
        ciclo.registrar = lambda p, r, a: gravados.append((p, r, a))
        main.notificacoes.voltar_a_estudar = lambda *a, **k: None
        self.assertIsNone(ciclo.pausa())
        self.assertEqual([g[2] for g in gravados], ["adiada", "feita"])


class TesteInstancia(unittest.TestCase):
    def test_comando_chega_na_instancia_em_execucao(self):
        import threading
        main.arquivo_porta = lambda: os.path.join(tempfile.gettempdir(), "teste_pausa.porta")
        self.assertFalse(main.enviar_comando("painel"))            # nada rodando
        srv, fila = main.abrir_servidor(), queue.Queue()
        threading.Thread(target=main.escutar, args=(srv, fila), daemon=True).start()
        self.assertTrue(main.enviar_comando("painel"))
        self.assertEqual(fila.get(timeout=2), "painel")
        self.assertTrue(main.enviar_comando("ping"))               # ping não gera comando
        self.assertTrue(fila.empty())
        srv.close()

    def test_sondar_nao_bloqueia_e_repassa_sair(self):
        f = queue.Queue()
        c = main.Ciclo(f)
        self.assertIsNone(c.sondar())
        f.put("sair")
        self.assertTrue(c.sondar_para_fechar())
        self.assertEqual(f.get_nowait(), "sair")       # devolvido ao laço principal

    def test_estado_info_para_o_painel(self):
        c = main.Ciclo(queue.Queue())
        c.esperar(0.05, "pausa")
        rotulo, restante, total = c.estado_info()
        self.assertIn("EM PAUSA", rotulo)
        self.assertEqual(restante, 0.0)


class TesteNovidades(unittest.TestCase):
    def test_config_novas_chaves(self):
        cfg = config.validar({"ciclos_pausa_longa": 4, "minutos_pausa_longa": 15,
                              "verificar_atualizacoes": False})
        self.assertEqual((cfg["ciclos_pausa_longa"], cfg["minutos_pausa_longa"],
                          cfg["verificar_atualizacoes"]), (4, 15, False))
        ruim = config.validar({"ciclos_pausa_longa": -1, "minutos_pausa_longa": 0})
        self.assertEqual((ruim["ciclos_pausa_longa"], ruim["minutos_pausa_longa"]), (0, 20))

    def test_pausa_longa_usa_a_duracao_longa(self):
        c = main.Ciclo(queue.Queue())
        c.cfg.update(modo_aviso="tela_cheia", minutos_pausa=10, minutos_pausa_longa=20)
        vistos = []
        c.aviso_tela_cheia = lambda p, s: (vistos.append((p, c.longa)), ("pulada", 0, False))[1]
        c.registrar = lambda *a: None
        c.pausa(longa=True)
        c.pausa(longa=False)
        self.assertEqual(vistos, [(1200, True), (600, False)])

    def test_suspender_congela_a_contagem(self):
        import threading
        f = queue.Queue()
        c = main.Ciclo(f)
        c.abrir_painel = lambda: (c.alternar_suspensao(), None)[1]   # painel simulado
        resultado = []
        t0 = time.monotonic()
        th = threading.Thread(target=lambda: resultado.append(c.esperar(0.6)))
        th.start()
        time.sleep(0.15)
        f.put("painel")                 # suspende com ~0,45 s restantes
        time.sleep(0.8)                 # passa do prazo original
        self.assertTrue(th.is_alive())  # continua esperando: a contagem está suspensa
        self.assertIn("SUSPENSA", c.estado_info()[0])
        f.put("painel")                 # retoma
        th.join(3)
        self.assertEqual(resultado, ["tempo"])
        self.assertGreaterEqual(time.monotonic() - t0, 0.15 + 0.8 + 0.35)

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


class TesteCorrecoes(unittest.TestCase):
    def test_reiniciar_contagem_volta_ao_inicio(self):
        c = main.Ciclo(queue.Queue())
        c.esperar(0.05)                              # define duração e limite
        c.duracao = 100.0
        c.limite = time.monotonic() + 10
        c.reiniciar_contagem()
        self.assertGreater(c.estado_info()[1], 99)
        c.alternar_suspensao()                       # suspenso: reinicia o valor congelado
        c.restante_suspenso = 5
        c.reiniciar_contagem()
        self.assertEqual(c.estado_info()[1], 100.0)

    def test_painel_volta_depois_da_pausa_iniciada_por_ele(self):
        f = queue.Queue()
        c = main.Ciclo(f)
        c.cfg.update(modo_aviso="tela_cheia")
        c.abrir_painel = lambda: "agora"             # usuário clicou em "Pausar agora"
        f.put("painel")
        self.assertEqual(c.esperar(5), "agora")
        self.assertTrue(c.reabrir_painel)
        c.aviso_tela_cheia = lambda p, s: ("feita", p, False)
        c.registrar = lambda *a: None
        main.notificacoes.voltar_a_estudar = lambda *a, **k: None
        c.pausa()
        self.assertEqual(f.get_nowait(), "painel")   # painel reaberto, sem o app "sumir"
        self.assertFalse(c.reabrir_painel)

    def test_painel_nao_volta_se_o_app_foi_encerrado(self):
        f = queue.Queue()
        c = main.Ciclo(f)
        c.reabrir_painel = True
        c.aviso_tela_cheia = lambda p, s: ("pulada", 0, True)
        c.registrar = lambda *a: None
        self.assertEqual(c.pausa(), "sair")
        self.assertTrue(f.empty())

    def test_tela_cheia_fecha_com_sair_e_guarda_painel(self):
        f = queue.Queue()
        c = main.Ciclo(f)
        f.put("painel")
        f.put("agora")
        self.assertFalse(c.sondar_overlay())         # painel guardado
        self.assertFalse(c.sondar_overlay())         # "agora" ignorado
        self.assertEqual(c._pendentes, {"painel"})
        f.put("sair")
        self.assertTrue(c.sondar_overlay())
        self.assertEqual(f.get_nowait(), "sair")

    def test_exportar_csv(self):
        with tempfile.TemporaryDirectory() as d:
            db, csv_ = os.path.join(d, "h.db"), os.path.join(d, "h.csv")
            historico.registrar(600, 600, "feita", datetime(2026, 11, 6, 10), db)
            historico.registrar(600, 0, "adiada", datetime(2026, 11, 6, 11), db)
            self.assertEqual(historico.exportar_csv(csv_, db), 2)
            with open(csv_, encoding="utf-8-sig") as f:
                linhas = f.read().splitlines()
            self.assertEqual(linhas[0], "data_hora;duracao_planejada_s;duracao_real_s;acao")
            self.assertEqual(linhas[1], "2026-11-06 10:00:00;600;600;feita")


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
        self._prefixo = atualizador.PREFIXO_DOWNLOAD
        atualizador.PREFIXO_DOWNLOAD = "http://127.0.0.1:%d/dl/" % self.srv.server_port

    def tearDown(self):
        atualizador.PREFIXO_DOWNLOAD = self._prefixo
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

    def test_sem_servidor_vira_erro_amigavel(self):
        self.srv.shutdown()
        self.srv.server_close()
        with self.assertRaises(atualizador.ErroAtualizacao):
            atualizador.consultar(self.api, timeout=2)
        self.srv.server_close()
        self.srv = type("X", (), {"shutdown": lambda s: None, "server_close": lambda s: None})()


if __name__ == "__main__":
    unittest.main()
