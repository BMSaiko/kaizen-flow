"""Testes de handoff_spawn.py (`--spawn`): run/sleep/copy falsos, sem painéis nem worktrees reais."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_pane as hp  # noqa: E402
import handoff_spawn as hs  # noqa: E402


class _Res:
    def __init__(self, stdout=""):
        self.stdout = stdout


class FakeRun:
    """Regista os argv e responde conforme o comando; `screen` é o que o painel mostra."""

    def __init__(self, screen="❯ "):
        self.calls = []
        self.screen = screen

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "ensure" in argv:
            return _Res("aviso\nC:/wt/" + argv[-1] + "\n")
        if argv[:2] == ["tmux", "split-window"]:
            return _Res("%9\n")
        if argv[:2] == ["tmux", "capture-pane"]:
            return _Res(self.screen)
        return _Res()


def _spawn(slugs, **kw):
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("registar", False)
    return hs.spawn(slugs, **kw)


def test_dry_run_nao_toca_em_nada_e_adia_o_excedente():
    run = FakeRun()
    res = _spawn(["a", "b", "c"], backend="tmux", maximo=2, dry_run=True, run=run)
    assert run.calls == []
    assert [r["ok"] for r in res] == [True, True, False]
    assert "adiado" in res[2]["erro"]


def test_tmux_cria_painel_e_envia_o_michi_auto():
    run = FakeRun()
    res = _spawn(["meu-sp"], backend="tmux", run=run)
    assert res == [{"slug": "meu-sp", "ok": True, "painel": "%9", "worktree": "C:/wt/meu-sp"}]
    assert ["tmux", "send-keys", "-t", "%9", "-l", "/michi --auto meu-sp"] in run.calls
    assert ["tmux", "send-keys", "-t", "%9", "Enter"] in run.calls


def test_enter_perdido_esgota_tentativas_e_fica_em_erro():
    run = FakeRun(screen="❯ /michi --auto x")  # o texto nunca sai do prompt
    res = _spawn(["x"], backend="tmux", run=run)
    assert res[0]["ok"] is False
    assert "Enter não submeteu" in res[0]["erro"]
    assert sum(c == ["tmux", "send-keys", "-t", "%9", "Enter"] for c in run.calls) == hs.SPAWN_ENTER_TRIES


def test_falha_de_um_sp_nao_para_os_outros():
    base = FakeRun()

    def run(argv, **kw):
        if "ensure" in argv and argv[-1] == "mau":
            raise OSError("sem worktree")
        return base(argv, **kw)

    res = _spawn(["mau", "bom"], backend="tmux", run=run)
    assert [r["ok"] for r in res] == [False, True]
    assert res[0]["erro"] == "sem worktree"


def test_clipboard_imprime_cd_e_copia_o_ultimo(capsys):
    copiado = []
    res = _spawn(["a", "b"], backend="clipboard", run=FakeRun(), copy=copiado.append)
    assert all(r["ok"] and r["painel"] is None for r in res)
    out = capsys.readouterr().out
    assert "a: cd C:/wt/a && claude" in out and "/michi --auto b" in out
    assert copiado == ["/michi --auto b"]


def test_wait_prompt_aprova_aviso_mcp_e_depois_segue():
    ecras = iter(["new MCP servers found", "❯ "])
    chamadas = []

    def fake(argv, **kw):
        chamadas.append(argv)
        if argv[:2] == ["tmux", "capture-pane"]:
            return _Res(next(ecras))
        return _Res()

    hs._wait_prompt("tmux", "%1", fake, lambda s: None)
    teclas = [c[-1] for c in chamadas if c[:2] == ["tmux", "send-keys"]]
    assert teclas == ["Down", "Space", "Down", "Enter"]


def test_wait_prompt_desiste_sem_prompt(monkeypatch):
    monkeypatch.setattr(hs, "SPAWN_READY_S", 3)
    with pytest.raises(hp.HandoffError, match="não ficou pronto"):
        hs._wait_prompt("tmux", "%1", lambda argv, **kw: _Res("a carregar"), lambda s: None)
