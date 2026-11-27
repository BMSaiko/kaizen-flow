import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import auditar


def repo(ficheiros, extra_base=None):
    """Repo git temporário com um commit base e `ficheiros` ({caminho: texto}) por commitar."""
    d = Path(tempfile.mkdtemp())
    run = lambda *a: subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (d / "base.py").write_text("x = 1\n", encoding="utf-8")
    for k, v in (extra_base or {}).items():
        (d / k).parent.mkdir(parents=True, exist_ok=True)
        (d / k).write_text(v, encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "base")
    for k, v in ficheiros.items():
        (d / k).parent.mkdir(parents=True, exist_ok=True)
        (d / k).write_text(v, encoding="utf-8")
    return d


def tipos(d, modo="normal", **kw):
    _ctx, conf, _sus = auditar.auditar(d, modo=modo, **kw)
    return sorted((a["tipo"], a["onde"].split(":")[0]) for a in conf)


class PlantadosTest(unittest.TestCase):
    """Fixture com erros plantados: todos encontrados, nenhum inventado."""

    def setUp(self):
        self.d = repo({
            "app.py": "import subprocess\nsubprocess.run(cmd, shell=True)\n",
            "leak.py": 'api_key = "abcd1234efgh"\n',
            "quebrado.py": "def f(:\n    pass\n",
            "conf.json": "{ invalido",
            "conflito.txt": "a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> x\n",
            "nota.md": "# Nota\nver [[nao-existe-mesmo]] e [[outra]]\n",
            "outra.md": "# Outra\n",
        })

    def test_encontra_todos_os_plantados(self):
        t = tipos(self.d)
        self.assertIn(("seguranca", "app.py"), t)
        self.assertIn(("seguranca", "leak.py"), t)
        self.assertIn(("bug", "quebrado.py"), t)
        self.assertIn(("bug", "conf.json"), t)
        self.assertIn(("bug", "conflito.txt"), t)
        self.assertIn(("docs", "nota.md"), t)

    def test_nao_inventa(self):
        t = tipos(self.d)
        self.assertEqual(len(t), 6, t)
        self.assertNotIn("outra.md", [x[1] for x in t])

    def test_rc_e_relatorio(self):
        self.assertEqual(auditar.main(["--repo", str(self.d), "--no-baseline"]), 1)

    def test_codigo_limpo_rc0(self):
        d = repo({"ok.py": "print('ola')\n"})
        self.assertEqual(auditar.main(["--repo", str(d), "--no-baseline"]), 0)
        self.assertEqual(tipos(d), [])

    def test_ficheiro_env_nunca_lido(self):
        d = repo({".env": "SEGREDO_NAO_LER=abc\n"})
        _c, conf, _s = auditar.auditar(d)
        self.assertEqual(conf[0]["tipo"], "seguranca")
        self.assertNotIn("SEGREDO_NAO_LER", json.dumps(conf))

    def test_testes_ignorados(self):
        d = repo({"test_x.py": "os.system('x')\n"})
        self.assertEqual(tipos(d), [])

    def test_supressao_com_motivo(self):
        d = repo({"a.py": "subprocess.run(c, shell=True)  # auditar: ok comando fixo\n"})
        self.assertEqual(tipos(d), [])
        d2 = repo({"a.py": "subprocess.run(c, shell=True)  # auditar: ok\n"})
        self.assertEqual(tipos(d2), [("seguranca", "a.py")])


class SuspeitasTest(unittest.TestCase):
    def test_todo_vai_para_suspeitas(self):
        d = repo({"a.py": "x = 2  # TODO rever\n"})
        _c, conf, sus = auditar.auditar(d)
        self.assertEqual(conf, [])
        self.assertEqual(len(sus), 1)
        self.assertEqual(auditar.main(["--repo", str(d), "--no-baseline"]), 0)


class ModosTest(unittest.TestCase):
    def test_rapido_so_linhas_adicionadas(self):
        d = repo({}, extra_base={"velho.py": "eval(x)\n"})
        (d / "velho.py").write_text("eval(x)\ny = 1\n", encoding="utf-8")
        self.assertEqual(tipos(d, "rapido"), [])
        self.assertEqual(tipos(d, "normal"), [("seguranca", "velho.py")])

    def test_total_ve_ficheiros_nao_alterados(self):
        d = repo({}, extra_base={"velho.py": "eval(x)\n"})
        subprocess.run(["git", "-C", str(d), "status", "-s"], check=True)
        self.assertEqual(tipos(d, "normal"), [])
        self.assertEqual(tipos(d, "total"), [("seguranca", "velho.py")])


class ContextoTest(unittest.TestCase):
    def test_vault(self):
        d = repo({"knowledge/a.md": "# a\n", ".claude/settings.json": "{}"})
        ctx, _c, _s = auditar.auditar(d)
        self.assertIn("vault", ctx)

    def test_ui_e_codigo(self):
        d = repo({"src/App.tsx": "export const A = () => null\n"})
        ctx, _c, _s = auditar.auditar(d)
        self.assertEqual(ctx[:1], ["codigo"])
        self.assertIn("ui", ctx)

    def test_vault_regras_settings(self):
        d = repo({"knowledge/a.md": "# a\n", ".claude/settings.json": "{}"})
        _c, conf, _s = auditar.auditar(d)
        self.assertIn(("regra", ".claude/settings.json"), [(a["tipo"], a["onde"].split(":")[0]) for a in conf])

    def test_sp_vazio_e_sem_gates(self):
        d = repo({"sp.md": "---\nslug: x\n---\n# SP\n\n## 1. Role\n\n\n## 3. Objective\n\n"})
        _c, conf, _s = auditar.auditar(d, sp=d / "sp.md")
        self.assertTrue(any(a["tipo"] == "regra" and "SP" in a["problema"] for a in conf))


class CicloTest(unittest.TestCase):
    def achados(self, texto):
        f = Path(tempfile.mkdtemp()) / "a.txt"
        f.write_text(texto, encoding="utf-8")
        return str(f)

    def test_aprovado_sem_bloqueantes(self):
        est = str(Path(tempfile.mkdtemp()) / "e.json")
        a = self.achados("[menor] a.py:1 estilo\n")
        self.assertEqual(auditar.main(["ciclo", est, "--achados", a]), 0)

    def test_corrigir_e_escalar(self):
        est = str(Path(tempfile.mkdtemp()) / "e.json")
        a = self.achados("[bloqueante] a.py:1 bug | verificar: pytest\n")
        self.assertEqual(auditar.main(["ciclo", est, "--achados", a, "--max", "2"]), 1)
        self.assertEqual(auditar.main(["ciclo", est, "--achados", a, "--max", "2"]), 2)
        self.assertEqual(auditar.main(["ciclo", est, "--achados", a, "--max", "2"]), 2)

    def test_rever_so_alterados(self):
        d = Path(tempfile.mkdtemp())
        (d / "a.py").write_text("1", encoding="utf-8")
        (d / "b.py").write_text("1", encoding="utf-8")
        est = str(d / "e.json")
        a = self.achados("[bloqueante] a.py:1 bug\n")
        auditar.main(["ciclo", est, "--achados", a, "--ficheiros", "a.py", "b.py", "--raiz", str(d)])
        (d / "a.py").write_text("2", encoding="utf-8")
        auditar.main(["ciclo", est, "--achados", a, "--ficheiros", "a.py", "b.py", "--raiz", str(d)])
        self.assertEqual(json.loads(Path(est).read_text())["historico"][-1]["rever"], ["a.py"])


if __name__ == "__main__":
    unittest.main()
