import tempfile
import unittest
from datetime import date
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

_p = Path(__file__).resolve().parent / "sp-envelhecer.py"
env = carregar(_p, "sp_env", registar=False, fresco=True)


def mk(root, name, prio, updated, status="TODO", extra=""):
    d = Path(root) / "p" / "sp" / status
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.md"
    f.write_text(f"---\nstatus: {status}\nslug: {name}\npriority: {prio}\ncreated: {updated}\nupdated: {updated}\n{extra}---\n# x\n", encoding="utf-8")
    return f


class T(unittest.TestCase):
    def test_target(self):
        self.assertEqual(env.target("P3", 13), "P3")
        self.assertEqual(env.target("P3", 14), "P2")
        self.assertEqual(env.target("P3", 28), "P1")
        self.assertEqual(env.target("P1", 99), "P1")

    def test_apply_idempotente(self):
        with tempfile.TemporaryDirectory() as r:
            f = mk(r, "a", "P3", "2026-10-01")
            today = date(2026, 11, 1)
            for _ in range(2):
                for sp, old, new, base, age in env.plan(r, today):
                    env.apply(sp, new, base)
            txt = f.read_text(encoding="utf-8")
            self.assertIn("priority: P1", txt)
            self.assertEqual(txt.count("priority_base: P3"), 1)
            self.assertEqual(env.plan(r, today), [])

    def test_recente_nao_sobe(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "b", "P3", "2026-10-30")
            self.assertEqual(env.plan(r, date(2026, 11, 1)), [])

    def test_hook_um_por_dia(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "c", "P3", "2026-10-01")
            st = Path(r) / "stamp"
            env.main(["--hook", "--root", r, "--stamp", str(st)])
            self.assertTrue(st.exists())
            self.assertIn("priority: P1", next(Path(r).rglob("c.md")).read_text(encoding="utf-8"))

    def test_bloqueado_nao_sobe(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "dep", "P3", "2026-10-30")
            mk(r, "blq", "P3", "2026-10-01", extra="depends_on: [dep]\n")
            mk(r, "livre", "P3", "2026-10-01")
            slugs = [x[0].slug for x in env.plan(r, date(2026, 11, 1))]
            self.assertEqual(slugs, ["livre"])

    def test_dependencia_cumprida_sobe(self):
        with tempfile.TemporaryDirectory() as r:
            mk(r, "dep", "P3", "2026-10-30", status="Done")
            mk(r, "ok", "P3", "2026-10-01", extra="depends_on: [dep]\n")
            slugs = [x[0].slug for x in env.plan(r, date(2026, 11, 1))]
            self.assertEqual(slugs, ["ok"])


if __name__ == "__main__":
    unittest.main()
