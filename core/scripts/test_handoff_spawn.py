"""Testes de handoff_spawn.py (`--spawn`): run/sleep/copy falsos, sem painéis nem worktrees reais."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_pane as hp  # noqa: E402
import handoff_spawn as hs  # noqa: E402


class _Res:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


class FakeRun:
    """Regista os argv e responde conforme o comando; `screen` é o que o painel mostra."""

    def __init__(self, screen=None):
        self.calls = []
        self.screen = screen  # None = painel real: o texto escrito aparece no prompt e o Enter limpa-o
        self.typed = ""

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if "ensure" in argv:
            return _Res("aviso\nC:/wt/" + argv[-1] + "\n")
        if argv[:2] == ["tmux", "split-window"]:
            return _Res("%9\n")
        if argv[:2] == ["tmux", "send-keys"]:
            self.typed = argv[-1] if "-l" in argv else ""
        if argv[:2] == ["tmux", "capture-pane"]:
            return _Res(self.screen if self.screen is not None else "❯ " + self.typed)
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


def _cfg(tmp_path, conteudo):
    p = tmp_path / "modelos.json"
    p.write_bytes(conteudo.encode("utf-8"))
    return p


_CFG = '{"papeis": {"michi-exec": {"model": "claude-haiku-5-5", "effort": "low"}}}'
_FLAGS = ["claude", "--model", "claude-haiku-5-5", "--effort", "low"]


def test_claude_cmd_junta_modelo_e_effort_do_papel(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "MODELOS", _cfg(tmp_path, _CFG))
    assert hs._claude_cmd() == _FLAGS


@pytest.mark.parametrize("conteudo", [None, "{nao json", '{"papeis": {}}'])
def test_claude_cmd_sem_config_valida_avisa_e_lanca_so_claude(tmp_path, monkeypatch, capsys, conteudo):
    path = tmp_path / "falta.json" if conteudo is None else _cfg(tmp_path, conteudo)
    monkeypatch.setattr(hs, "MODELOS", path)
    assert hs._claude_cmd() == ["claude"]
    assert "aviso" in capsys.readouterr().err


def test_painel_background_e_dry_run_levam_o_modelo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(hs, "MODELOS", _cfg(tmp_path, _CFG))
    run = FakeRun()
    _spawn(["x"], backend="tmux", run=run)
    assert any(c[-5:] == _FLAGS or all(f in c for f in _FLAGS[1:]) for c in run.calls if "split-window" in c)
    abertos = []
    monkeypatch.setattr(hs, "_spawn_pane", lambda b, wt, r, cmd=("claude",): abertos.append(list(cmd)) or "bg1")
    _spawn(["y"], backend="background", run=FakeRun())
    assert abertos == [[*_FLAGS, "-p", "/michi --auto y"]]
    res = _spawn(["z"], backend="tmux", run=FakeRun(), dry_run=True)
    assert res[0]["cmd"] == " ".join(_FLAGS)
    _spawn(["w"], backend="clipboard", run=FakeRun(), copy=lambda s: None)
    assert "cd C:/wt/w && " + " ".join(_FLAGS) in capsys.readouterr().out


def test_wait_prompt_desiste_sem_prompt(monkeypatch):
    monkeypatch.setattr(hs, "SPAWN_READY_S", 3)
    with pytest.raises(hp.HandoffError, match="não ficou pronto"):
        hs._wait_prompt("tmux", "%1", lambda argv, **kw: _Res("a carregar"), lambda s: None)


def _sp(raiz, pasta, slug, nivel):
    d = raiz / "knowledge" / "projects" / "p" / "x" / "sp" / pasta
    d.mkdir(parents=True, exist_ok=True)
    linhas = ["---", f"status: {pasta}", f"michi_modelo: {nivel}", "---", "# x", ""]
    (d / f"{slug}.md").write_text(chr(10).join(linhas), encoding="utf-8")


_CFG_NIVEIS = ('{"papeis": {"michi-exec": {"model": "claude-sonnet-5-5", "effort": "medium"},'
               ' "michi-complexo": {"model": "claude-opus-5-5", "effort": "medium"},'
               ' "michi-critico": {"model": "claude-fable-5-2", "effort": "low"}},'
               ' "michi_modelo": {"default": "michi-exec", "complexo": "michi-complexo", "critico": "michi-critico"}}')


def test_claude_cmd_usa_o_nivel_michi_do_sp_em_curso(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "MODELOS", _cfg(tmp_path, _CFG_NIVEIS))
    monkeypatch.setattr(hs, "RAIZ", tmp_path)
    _sp(tmp_path, "Doing", "sp-c", "complexo")
    _sp(tmp_path, "TODO", "sp-k", "critico")
    assert hs._claude_cmd("sp-c") == ["claude", "--model", "claude-opus-5-5", "--effort", "medium"]
    assert hs._claude_cmd("sp-k") == ["claude", "--model", "claude-fable-5-2", "--effort", "low"]
    assert hs._claude_cmd("sem-sp") == ["claude", "--model", "claude-sonnet-5-5", "--effort", "medium"]


def test_spawn_dry_run_leva_o_modelo_do_nivel_de_cada_sp(tmp_path, monkeypatch):
    monkeypatch.setattr(hs, "MODELOS", _cfg(tmp_path, _CFG_NIVEIS))
    monkeypatch.setattr(hs, "RAIZ", tmp_path)
    _sp(tmp_path, "Doing", "sp-c", "complexo")
    res = _spawn(["sp-c", "outro"], backend="tmux", run=FakeRun(), dry_run=True)
    assert "claude-opus-5-5" in res[0]["cmd"] and "claude-sonnet-5-5" in res[1]["cmd"]


def test_herdr_lanca_agente_e_envia_o_michi_por_herdr_ops(monkeypatch):
    """No herdr o handoff fala só por `herdr_ops`: painel novo, agente `claude`, prompt `agent prompt` (sem ler o ecrã)."""
    from herdr_fake import FakeHerdr
    fake = FakeHerdr()

    def run(argv, **kw):
        if "ensure" in argv:
            return _Res("aviso\n/wt/meu-sp\n")
        return fake(argv, **kw)

    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    res = _spawn(["meu-sp"], backend="herdr", run=run)
    assert res[0]["ok"] and res[0]["worktree"] == "/wt/meu-sp"
    pane = res[0]["painel"]
    assert ["herdr", "agent", "prompt", pane, "/michi --auto meu-sp"] in fake.chamadas
    assert not any(c[:3] in (["herdr", "pane", "send-text"], ["herdr", "pane", "read"]) for c in fake.chamadas)
    assert any(c[:3] == ["herdr", "pane", "run"] and "command claude" in c[4] for c in fake.chamadas)


def test_herdr_espera_pela_deteccao_do_agente_antes_do_prompt(monkeypatch):
    """Corrida real: `agent prompt` logo após o `claude` arrancar dá agent_not_found; repete até o agente ser detetado."""
    import json
    from herdr_fake import FakeHerdr
    fake = FakeHerdr()
    falhas = {"n": 2}

    def run(argv, **kw):
        if "ensure" in argv:
            return _Res("/wt/meu-sp\n")
        if argv[1:3] == ["agent", "prompt"] and falhas["n"]:
            falhas["n"] -= 1
            fake.chamadas.append(list(argv))
            return _Res(json.dumps({"error": {"code": "agent_not_found", "message": "x"}}), 1)
        return fake(argv, **kw)

    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    res = _spawn(["meu-sp"], backend="herdr", run=run, sleep=lambda s: None)
    assert res[0]["ok"] and falhas["n"] == 0
