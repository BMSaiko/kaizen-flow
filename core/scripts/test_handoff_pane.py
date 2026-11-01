"""Testes de handoff_pane.py (argv de envio para painéis, deteção de backend, prompt com texto)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_pane as hp  # noqa: E402


def test_pane_id_exige_wezterm_pane():
    assert hp.pane_id({"WEZTERM_PANE": "7"}) == "7"
    with pytest.raises(hp.HandoffError, match="WEZTERM_PANE"):
        hp.pane_id({})


@pytest.mark.parametrize("send", [hp.send_argv, hp.tmux_send_argv])
def test_send_recusa_caracteres_de_controlo(send):
    for bad in ("a\nb", "a\rb", "a\x1bb"):
        with pytest.raises(hp.HandoffError):
            send("1", bad)


def test_argv_wezterm_e_tmux():
    assert hp.send_argv(3, "oi") == ["wezterm", "cli", "send-text", "--pane-id", "3", "--no-paste", "oi"]
    assert hp.enter_argv(3)[-1] == "\r"
    assert hp.tmux_send_argv("%1", "oi") == ["tmux", "send-keys", "-t", "%1", "-l", "oi"]
    assert hp.tmux_enter_argv("%1")[-1] == "Enter"


def test_detect_backend_prefere_wezterm_depois_tmux_depois_clipboard():
    assert hp.detect_backend({"WEZTERM_PANE": "1", "TMUX_PANE": "%2"}) == ("wezterm", "1")
    assert hp.detect_backend({"TMUX_PANE": "%2"}) == ("tmux", "%2")
    assert hp.detect_backend({}) == ("clipboard", None)


def test_argvs_recusa_clipboard():
    assert hp._argvs("tmux", "%1") == (hp.tmux_send_argv, hp.tmux_enter_argv)
    with pytest.raises(hp.HandoffError):
        hp._argvs("clipboard", None)


def test_prompt_has_text_usa_a_ultima_linha_do_prompt():
    assert hp.prompt_has_text("x\n❯ \n") is False
    assert hp.prompt_has_text("❯ antigo\n❯ \n") is False
    assert hp.prompt_has_text("❯ \n❯ escrito") is True
    assert hp.prompt_has_text("sem prompt") is False


class _Res:
    def __init__(self, stdout):
        self.stdout = stdout


def test_pane_exists_e_check_prompt_com_run_falso():
    run = lambda *a, **k: _Res('[{"pane_id": 4}]')  # noqa: E731
    hp.pane_exists(4, run=run)
    with pytest.raises(hp.HandoffError, match="não existe"):
        hp.pane_exists(9, run=run)
    with pytest.raises(hp.HandoffError, match="texto por enviar"):
        hp.check_prompt(4, run=lambda *a, **k: _Res("❯ rascunho"))
    hp.check_prompt(4, run=lambda *a, **k: _Res("❯ "))
