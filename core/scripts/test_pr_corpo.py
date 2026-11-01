import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import pr_corpo

SP = """---
slug: demo
pr: {pol}
---
# Super Prompt

## 3. Objective (single sentence)

Fazer a coisa.

## Decisões

- Usar X.

## Progresso

- feito Y.

## Prova de done

- teste 4/4.
"""


def montar(pol, veredicto="APROVADO"):
    d = Path(tempfile.mkdtemp())
    (d / "sp.md").write_text(SP.format(pol=pol), encoding="utf-8")
    (d / "r.json").write_text(json.dumps({"veredicto": veredicto, "iteracao": 2}), encoding="utf-8")
    return [str(d / "sp.md"), "--review", str(d / "r.json")]


def correr(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = pr_corpo.main(args)
    return rc, out.getvalue(), err.getvalue()


class PrTest(unittest.TestCase):
    def test_corpo_tem_as_4_seccoes_preenchidas(self):
        rc, out, _ = correr(montar("auto"))
        self.assertEqual(rc, 0)
        for t in ("## O que foi feito", "## Decisões tomadas", "## O que ficou por fazer", "## Prova"):
            self.assertIn(t, out)
        for t in ("Fazer a coisa", "Usar X", "teste 4/4", "Review: APROVADO"):
            self.assertIn(t, out)
        self.assertNotIn("{", out)
        self.assertNotIn("Co-Authored-By", out)

    def test_auto_cria_com_gh(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as m:
            rc, _, _ = correr(montar("auto") + ["--criar", "--base", "main"])
        self.assertEqual(rc, 0)
        cmd = m.call_args[0][0]
        self.assertEqual(cmd[:3], ["gh", "pr", "create"])
        self.assertEqual(cmd[cmd.index("--base") + 1], "main")
        self.assertNotIn("Co-Authored-By", cmd[-1])

    def test_pergunta_nunca_e_review_reprovado_nao_criam(self):
        with mock.patch("subprocess.run") as m:
            self.assertEqual(correr(montar("pergunta") + ["--criar"])[0], 3)
            self.assertEqual(correr(montar("nunca") + ["--criar"])[0], 4)
            self.assertEqual(correr(montar("auto", "ESCALAR") + ["--criar"])[0], 2)
        self.assertFalse(any(c[0][0][:1] == ["gh"] for c in m.call_args_list))

    def test_dry_run_imprime_e_nunca_cria(self):
        with mock.patch("subprocess.run") as m:
            rc, out, err = correr(montar("auto") + ["--criar", "--dry-run", "--base", "main"])
        self.assertEqual(rc, 0)
        self.assertIn("## Prova", out)
        self.assertIn("Base: main", err)
        self.assertFalse(any(c[0][0][:1] == ["gh"] for c in m.call_args_list))

    def test_base_unica_e_ambigua(self):
        def git(saida):
            return mock.Mock(stdout=saida, returncode=0)
        uma = "  origin/HEAD -> origin/main\n  origin/main\n  origin/feat\n"
        tres = "  origin/main\n  origin/master\n  origin/dev\n"
        with mock.patch("subprocess.run", return_value=git(uma)):
            self.assertEqual(pr_corpo.detetar_base(".")[0], "main")
        with mock.patch("subprocess.run", return_value=git(tres)):
            base, cand = pr_corpo.detetar_base(".")
        self.assertIsNone(base)
        self.assertEqual(cand, ["main", "master", "dev"])

    def test_base_ambigua_com_criar_pede_confirmacao(self):
        amb = mock.Mock(stdout="  origin/main\n  origin/master\n", returncode=0)
        with mock.patch("subprocess.run", return_value=amb) as m:
            rc, _, _ = correr(montar("auto") + ["--criar"])
        self.assertEqual(rc, 6)
        self.assertFalse(any(c[0][0][:3] == ["gh", "pr", "create"] for c in m.call_args_list))

    def test_corpo_tem_provas_e_gates(self):
        sp = SP.format(pol="auto").replace("slug: demo", "slug: demo\ngates:\n  - cmd: python -I x.py\n") + "\nVer proofs/dry-run.txt\n"
        d = Path(tempfile.mkdtemp())
        (d / "sp.md").write_text(sp, encoding="utf-8")
        (d / "r.json").write_text(json.dumps({"veredicto": "APROVADO", "iteracao": 1}), encoding="utf-8")
        _, out, _ = correr([str(d / "sp.md"), "--review", str(d / "r.json")])
        self.assertIn("`proofs/dry-run.txt`", out)
        self.assertIn("`python -I x.py`", out)

    def test_atribuicao_removida_do_corpo(self):
        sp = SP.format(pol="auto") + "\nCo-Authored-By: bot\nGenerated with tool\n"
        d = Path(tempfile.mkdtemp())
        (d / "sp.md").write_text(sp, encoding="utf-8")
        (d / "r.json").write_text(json.dumps({"veredicto": "APROVADO", "iteracao": 1}), encoding="utf-8")
        _, out, _ = correr([str(d / "sp.md"), "--review", str(d / "r.json")])
        self.assertNotIn("Co-Authored-By", out)
        self.assertNotIn("Generated with", out)


if __name__ == "__main__":
    unittest.main()
