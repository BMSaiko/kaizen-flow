import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import review_ciclo as rc


def ficheiros(texto):
    d = Path(tempfile.mkdtemp())
    (d / "a.txt").write_text(texto, encoding="utf-8")
    return d / "estado.json", d / "a.txt"


class CicloTest(unittest.TestCase):
    def run_(self, est, ach, extra=()):
        return rc.main([str(est), "--achados", str(ach), *extra])

    def test_aprovado_so_com_menores(self):
        est, ach = ficheiros("[menor] x.py:1 nome pouco claro\n")
        self.assertEqual(self.run_(est, ach), 0)
        self.assertEqual(json.loads(est.read_text())["veredicto"], "APROVADO")

    def test_reprovado_corrige_e_repete_ate_aprovar(self):
        est, ach = ficheiros("[bloqueante] x.py:3 divide por zero\n")
        self.assertEqual(self.run_(est, ach), 1)
        ach.write_text("[menor] x.py:3 comentário\n", encoding="utf-8")
        self.assertEqual(self.run_(est, ach), 0)
        self.assertEqual(json.loads(est.read_text())["iteracao"], 2)

    def test_limite_escala_ao_bms(self):
        est, ach = ficheiros("[bloqueante] x.py:3 bug\n")
        self.assertEqual(self.run_(est, ach, ["--max", "2"]), 1)
        self.assertEqual(self.run_(est, ach, ["--max", "2"]), 2)
        self.assertEqual(self.run_(est, ach, ["--max", "2"]), 2)

    def test_criar_sps_exige_project(self):
        est, ach = ficheiros("")
        with self.assertRaises(SystemExit):
            self.run_(est, ach, ["--criar-sps"])

    def test_achado_com_verificar(self):
        est, ach = ficheiros("[bloqueante] x.py:3 bug | verificar: pytest x\n")
        rc.main([str(est), "--achados", str(ach)])
        h = json.loads(est.read_text())["historico"][0]
        self.assertEqual(h["achados"][0]["verificar"], "pytest x")

    def test_incremental_so_ficheiros_alterados(self):
        est, ach = ficheiros("[bloqueante] x.py:3 bug\n")
        raiz = est.parent
        (raiz / "x.py").write_text("a", encoding="utf-8")
        (raiz / "y.py").write_text("b", encoding="utf-8")
        base = ["--raiz", str(raiz), "--ficheiros", "x.py", "y.py"]
        rc.main([str(est), "--achados", str(ach), *base])
        e = json.loads(est.read_text())
        self.assertEqual(e["historico"][0]["rever"], ["x.py", "y.py"])
        (raiz / "x.py").write_text("a2", encoding="utf-8")
        rc.main([str(est), "--achados", str(ach), *base])
        e = json.loads(est.read_text())
        self.assertEqual(e["historico"][1]["rever"], ["x.py"])

    def test_resumo_de_iteracoes(self):
        est, ach = ficheiros("[bloqueante] x.py:3 bug\n")
        rc.main([str(est), "--achados", str(ach)])
        txt = rc.resumo(json.loads(est.read_text()))
        self.assertIn("| 1 | 1 | 0 |", txt)

    def test_checklist_por_tipo(self):
        self.assertIn("testes", rc.checklist("codigo").lower())
        with self.assertRaises(KeyError):
            rc.checklist("xyz")


if __name__ == "__main__":
    unittest.main()
