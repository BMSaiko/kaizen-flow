import importlib.util
import pathlib

_p = pathlib.Path(__file__).with_name("herdr-spike-agent.py")
_s = importlib.util.spec_from_file_location("herdr_spike_agent", _p)
m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m)


def test_dry_run_imprime_ciclo(capsys):
    assert m.main(["--dry-run", "--session", "x", "--model", "haiku"]) == 0
    out = capsys.readouterr().out
    for parte in ("workspace create", "agent start", "agent prompt", "agent list", "pane close", "session delete x"):
        assert parte in out
    assert out.count("herdr --session x") == 8


def test_plano_model_vai_apos_separador():
    class A:
        session, kind, model, prompt, timeout_ms = "s", "claude", "haiku", "p", 5
    ag = m.plano(A)[1]
    assert ag[-3:] == ["--", "--model", "haiku"]
