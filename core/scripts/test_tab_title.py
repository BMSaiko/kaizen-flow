#!/usr/bin/env python3
import subprocess
import unittest
from unittest import mock
from pathlib import Path
from sp_carregar import carregar  # noqa: E402

tt = carregar(Path(__file__).with_name("tab-title.py"), "tab_title", registar=False, fresco=True)


class TabTitleTest(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(tt.sanitize("Renomear Sessão/Tab!"), "renomear-sess-o-tab")
        self.assertEqual(tt.sanitize("renomear-sessao-tab-ao-arrancar-2026-10-26.md"), "renomear-sessao-tab-ao-arrancar")

    def test_truncate(self):
        out = tt.sanitize("a" * 30 + "-" + "b" * 30)
        self.assertLessEqual(len(out), 40)
        self.assertFalse(out.endswith("-"))

    def test_no_pane(self):
        calls = []
        self.assertFalse(tt.set_title("x", env={}, run=lambda *a, **k: calls.append(a)))
        self.assertEqual(calls, [])

    def test_wezterm_missing(self):
        def boom(*a, **k):
            raise FileNotFoundError("wezterm")
        self.assertFalse(tt.set_title("x", pane="3", run=boom))

    def test_command_failure(self):
        def fail(*a, **k):
            raise subprocess.CalledProcessError(1, "wezterm")
        self.assertFalse(tt.set_title("x", pane="3", run=fail))

    def test_argv(self):
        seen = []
        self.assertTrue(tt.set_title("meu slug", env={"WEZTERM_PANE": "7"}, run=lambda a, **k: seen.append(a)))
        self.assertEqual(seen[0], ["wezterm", "cli", "--no-auto-start", "set-tab-title", "--pane-id", "7", "meu-slug"])

    def test_main_rc0_without_pane(self):
        # sem WEZTERM_PANE real: senão o teste renomeia o painel onde corre («abc»)
        with mock.patch.dict("os.environ"), mock.patch.object(tt.subprocess, "run") as run:
            tt.os.environ.pop("WEZTERM_PANE", None)
            self.assertEqual(tt.main(["abc", "--pane", ""]), 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
