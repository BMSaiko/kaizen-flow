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


if __name__ == "__main__":
    unittest.main()
