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


class _Painel:
    """Ecrã simulado: o texto fica no prompt até o Enter número `enters_perdidos + 1`."""

    def __init__(self, enters_perdidos=0, textos_perdidos=0):
        self.perdidos = enters_perdidos
        self.textos_perdidos = textos_perdidos  # escritas descartadas (sessão a reiniciar depois de /clear)
        self.escritas = 0
        self.enters = 0
        self.texto = ""

    def run(self, argv, **kw):
        if argv[-1] == "\r":
            self.enters += 1
            if self.enters > self.perdidos:
                self.texto = ""
            return _Res("")
        if "get-text" in argv:
            return _Res("saida\n❯ " + self.texto)
        self.escritas += 1
        if self.escritas > self.textos_perdidos:
            self.texto = argv[-1]
        return _Res("")


def _enviar(painel, **kw):
    return hp.send_confirmed(3, "/michi x", hp.send_argv, hp.enter_argv, lambda p: hp.read_screen("wezterm", p, painel.run),
                             run=painel.run, sleep=lambda s: None, **kw)


def test_send_confirmed_um_enter_basta_quando_o_prompt_fica_vazio():
    p = _Painel()
    _enviar(p)
    assert p.enters == 1


def test_send_confirmed_reenvia_o_enter_ate_o_prompt_esvaziar():
    p = _Painel(enters_perdidos=2)
    _enviar(p)
    assert p.enters == 3


def test_send_confirmed_esgota_tentativas_e_falha():
    p = _Painel(enters_perdidos=99)
    with pytest.raises(hp.HandoffError, match="Enter não submeteu"):
        _enviar(p)
    assert p.enters == hp.ENTER_TRIES


def test_send_confirmed_reescreve_o_texto_perdido_depois_do_clear():
    p = _Painel(textos_perdidos=1)
    _enviar(p)
    assert (p.escritas, p.enters) == (2, 1)


def test_send_confirmed_falha_se_o_texto_nunca_chega_ao_prompt():
    p = _Painel(textos_perdidos=99)
    with pytest.raises(hp.HandoffError, match="não chegou ao prompt"):
        _enviar(p)
    assert p.enters == 0


def test_read_screen_usa_get_text_no_wezterm_e_capture_pane_no_tmux():
    vistos = []
    run = lambda argv, **k: vistos.append(argv) or _Res("x")  # noqa: E731
    assert hp.read_screen("wezterm", 3, run) == "x"
    hp.read_screen("tmux", "%1", run)
    assert vistos == [["wezterm", "cli", "get-text", "--pane-id", "3"], ["tmux", "capture-pane", "-p", "-t", "%1"]]


def test_send_lines_com_screen_confirma_cada_linha():
    p = _Painel(enters_perdidos=1)
    hp.send_lines(["/clear", "/michi y"], 3, hp.send_argv, hp.enter_argv, run=p.run, sleep=lambda s: None,
                  screen=lambda pane: hp.read_screen("wezterm", pane, p.run))
    assert p.enters == 3  # 1.ª linha: Enter perdido + reenvio; 2.ª linha: um Enter (o contador perdido já passou)


def test_pane_exists_e_check_prompt_com_run_falso():
    run = lambda *a, **k: _Res('[{"pane_id": 4}]')  # noqa: E731
    hp.pane_exists(4, run=run)
    with pytest.raises(hp.HandoffError, match="não existe"):
        hp.pane_exists(9, run=run)
    with pytest.raises(hp.HandoffError, match="texto por enviar"):
        hp.check_prompt(4, run=lambda *a, **k: _Res("❯ rascunho"))
    hp.check_prompt(4, run=lambda *a, **k: _Res("❯ "))


def test_run_hidden_wezterm_sem_auto_start_e_timeout(monkeypatch):
    import subprocess as sp
    import handoff_pane as hp
    vistos = {}

    def fake_run(argv, **kw):
        vistos.update(argv=argv, kw=kw)
        raise sp.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(hp.subprocess, "run", fake_run)
    import pytest
    with pytest.raises(hp.HandoffError, match="não respondeu"):
        hp.run_hidden(["wezterm", "cli", "list"], capture_output=True)
    assert vistos["argv"][:3] == ["wezterm", "cli", "--no-auto-start"]
    assert vistos["kw"]["timeout"] == hp.CLI_TIMEOUT


def test_run_hidden_wezterm_rc_erro_vira_handoff_error(monkeypatch):
    import subprocess as sp
    import handoff_pane as hp
    import pytest

    def fake_run(argv, **kw):
        raise sp.CalledProcessError(1, argv)

    monkeypatch.setattr(hp.subprocess, "run", fake_run)
    with pytest.raises(hp.HandoffError, match="inacessível"):
        hp.run_hidden(["wezterm", "cli", "list"], check=True)
