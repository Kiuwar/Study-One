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

    def test_estado_info_para_o_painel(self):
        c = main.Ciclo(queue.Queue())
        c.esperar(0.05, "pausa")
        rotulo, restante, total = c.estado_info()
        self.assertIn("EM PAUSA", rotulo)
        self.assertEqual(restante, 0.0)


if __name__ == "__main__":
    unittest.main()
