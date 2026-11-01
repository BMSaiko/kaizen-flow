import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import pr_watch


def pr(state="OPEN", mergeable="MERGEABLE", merge_state="CLEAN", review="APPROVED", checks=None):
    return {
        "state": state,
        "mergeable": mergeable,
        "mergeStateStatus": merge_state,
        "reviewDecision": review,
        "statusCheckRollup": checks if checks is not None else [],
    }


def ok(name="build"):
    return {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": "SUCCESS", "detailsUrl": "u"}


def bad(name="lint", concl="FAILURE"):
    return {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": concl,
            "detailsUrl": "https://x/run/1"}


def pend(name="slow"):
    return {"__typename": "CheckRun", "name": name, "status": "IN_PROGRESS", "conclusion": ""}


class Classify(unittest.TestCase):
    def test_merged(self):
        self.assertEqual(pr_watch.classify(pr(state="MERGED"))[0], "merged")

    def test_closed(self):
        self.assertEqual(pr_watch.classify(pr(state="CLOSED"))[0], "closed")

    def test_conflito(self):
        self.assertEqual(pr_watch.classify(pr(mergeable="CONFLICTING", checks=[ok()]))[0], "conflito")

    def test_erro_mostra_nome_e_url(self):
        est, det = pr_watch.classify(pr(checks=[ok(), bad("lint")]))
        self.assertEqual(est, "erro")
        self.assertIn("lint", det)
        self.assertIn("https://x/run/1", det)

    def test_erro_statuscontext(self):
        sc = {"__typename": "StatusContext", "context": "ci/x", "state": "FAILURE", "targetUrl": "t"}
        est, det = pr_watch.classify(pr(checks=[sc]))
        self.assertEqual(est, "erro")
        self.assertIn("ci/x", det)

    def test_erro_vence_conflito(self):
        self.assertEqual(pr_watch.classify(pr(mergeable="CONFLICTING", checks=[bad()]))[0], "erro")

    def test_timeout_e_erro(self):
        self.assertEqual(pr_watch.classify(pr(checks=[bad(concl="TIMED_OUT")]))[0], "erro")

    def test_pendente(self):
        self.assertEqual(pr_watch.classify(pr(merge_state="BLOCKED", checks=[ok(), pend()]))[0], "pendente")

    def test_pronto(self):
        self.assertEqual(pr_watch.classify(pr(checks=[ok()]))[0], "pronto")

    def test_pronto_sem_checks(self):
        self.assertEqual(pr_watch.classify(pr(review="", checks=[]))[0], "pronto")

    def test_review_pedido_nao_pronto(self):
        self.assertEqual(pr_watch.classify(pr(review="REVIEW_REQUIRED", merge_state="BLOCKED", checks=[ok()]))[0],
                         "aguarda-review")

    def test_changes_requested(self):
        self.assertEqual(pr_watch.classify(pr(review="CHANGES_REQUESTED", merge_state="BLOCKED", checks=[ok()]))[0],
                         "aguarda-review")

    def test_mergeable_desconhecido(self):
        self.assertEqual(pr_watch.classify(pr(mergeable="UNKNOWN", merge_state="UNKNOWN", checks=[ok()]))[0],
                         "pendente")

    def test_skipped_e_neutral_ok(self):
        c = [dict(ok(), conclusion="SKIPPED"), dict(ok("b"), conclusion="NEUTRAL")]
        self.assertEqual(pr_watch.classify(pr(checks=c))[0], "pronto")


class Fetch(unittest.TestCase):
    def test_comando_so_leitura(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=json.dumps(pr()), stderr="")
            out = pr_watch.fetch("12", repo="C:/r")
        args = run.call_args[0][0]
        self.assertEqual(args[:3], ["gh", "pr", "view"])
        self.assertIn("12", args)
        self.assertIn("statusCheckRollup", args[-1])
        self.assertEqual(run.call_args[1]["cwd"], "C:/r")
        self.assertEqual(out["state"], "OPEN")

    def test_falha_gh(self):
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=1, stdout="", stderr="boom")
            with self.assertRaises(pr_watch.GhError):
                pr_watch.fetch("12")


class Watch(unittest.TestCase):
    def run_watch(self, seq, **kw):
        it = iter(seq)
        buf = io.StringIO()
        extra = {}
        if kw.get("clock"):
            extra["clock"] = kw.pop("clock")
        with contextlib.redirect_stdout(buf):
            rc = pr_watch.watch("7", fetch_fn=lambda *_a, **_k: next(it), sleep=lambda s: None,
                                interval=1, max_seconds=kw.pop("max_seconds", 100), **extra, **kw)
        return rc, buf.getvalue().splitlines()

    def test_so_notifica_mudancas(self):
        rev = pr(review="REVIEW_REQUIRED", merge_state="BLOCKED", checks=[ok()])
        seq = [pr(merge_state="BLOCKED", checks=[pend()])] * 3 + [rev] * 2 + [pr(checks=[ok()])]
        rc, linhas = self.run_watch(seq)
        self.assertEqual(rc, 0)
        self.assertEqual(len(linhas), 3)
        self.assertIn("pendente", linhas[0])
        self.assertIn("aguarda-review", linhas[1])
        self.assertIn("pronto", linhas[2])

    def test_para_em_pronto(self):
        rc, linhas = self.run_watch([pr(checks=[ok()]), pr(state="MERGED")])
        self.assertEqual(rc, 0)
        self.assertEqual(len(linhas), 1)

    def test_para_em_erro_rc5(self):
        rc, linhas = self.run_watch([pr(merge_state="BLOCKED", checks=[pend()]), pr(checks=[bad("lint")])])
        self.assertEqual(rc, 5)
        self.assertIn("lint", linhas[-1])

    def test_para_em_conflito_rc6(self):
        rc, _ = self.run_watch([pr(mergeable="CONFLICTING", checks=[ok()])])
        self.assertEqual(rc, 6)

    def test_termina_em_merged_rc0(self):
        rc, _ = self.run_watch([pr(state="MERGED")])
        self.assertEqual(rc, 0)

    def test_closed_rc2(self):
        rc, linhas = self.run_watch([pr(state="CLOSED")])
        self.assertEqual(rc, 2)
        self.assertIn("closed", linhas[0])

    def test_erro_gh_repete_e_desiste(self):
        def boom(*_a, **_k):
            raise pr_watch.GhError("x")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = pr_watch.watch("7", fetch_fn=boom, sleep=lambda s: None, interval=1, max_seconds=100, max_falhas=3)
        self.assertEqual(rc, 4)

    def test_limite_de_duracao_rc3(self):
        t = iter(range(0, 1000, 60))
        rc, linhas = self.run_watch([pr(merge_state="BLOCKED", checks=[pend()])] * 50,
                                    max_seconds=120, clock=lambda: next(t))
        self.assertEqual(rc, 3)
        self.assertIn("limite", linhas[-1])

    def test_muda_de_erro_para_outro_erro_notifica(self):
        self.assertNotEqual(pr_watch.classify(pr(checks=[bad("a")])), pr_watch.classify(pr(checks=[bad("b")])))


class Cli(unittest.TestCase):
    def test_pr_url_aceite(self):
        self.assertEqual(pr_watch.pr_ref("https://github.com/o/r/pull/9"), "https://github.com/o/r/pull/9")

    def test_pr_numero(self):
        self.assertEqual(pr_watch.pr_ref("9"), "9")

    def test_pr_invalido(self):
        with self.assertRaises(ValueError):
            pr_watch.pr_ref("--web")


if __name__ == "__main__":
    unittest.main()
