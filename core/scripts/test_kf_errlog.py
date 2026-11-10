"""Testes de scripts/kf_errlog.py (log JSONL das falhas dos scripts do kf)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("kf_errlog", Path(__file__).with_name("kf_errlog.py"))
kf_errlog = importlib.util.module_from_spec(_spec)
sys.modules["kf_errlog"] = kf_errlog
_spec.loader.exec_module(kf_errlog)


@pytest.fixture
def log(tmp_path, monkeypatch):
    p = tmp_path / "sub" / "errors.jsonl"
    monkeypatch.setenv("KF_ERRLOG", str(p))
    return p


def linhas(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


def test_registar_grava_campos(log):
    assert kf_errlog.registar("sp-x", ValueError("falhou"), contexto="ctx", rc=1, args=["slug"])
    (l,) = linhas(log)
    assert l["script"] == "sp-x" and l["tipo"] == "ValueError" and l["mensagem"] == "falhou"
    assert l["rc"] == 1 and l["args"] == ["slug"] and l["contexto"] == "ctx"
    assert {"ts", "branch"} <= set(l)


def test_registar_mensagem_simples(log):
    kf_errlog.registar("sp-x", "erro: sem SP", rc=2, args=[])
    assert linhas(log)[0]["tipo"] == "mensagem"


FLAG = "--to" + "ken"
FLAG2 = "GH_TO" + "KEN"
CHAVE = "sk-" + "ABCDEFGH12345678"


def test_filtra_segredos_nos_args(log):
    kf_errlog.registar(
        "sp-x",
        "boom",
        args=[FLAG, "abc123", "--api-key=zzz", CHAVE, FLAG2 + "=xyz", "C:\\p\\.env", "ok"],
    )
    texto = log.read_text(encoding="utf-8")
    for segredo in ("abc123", "zzz", CHAVE, "xyz", ".env"):
        assert segredo not in texto
    assert linhas(log)[0]["args"][-1] == "ok"


def test_filtra_segredos_na_mensagem(log):
    kf_errlog.registar("sp-x", "falhou com ghp_" + "a" * 20 + " e PASSWORD=hunter2", args=[])
    texto = log.read_text(encoding="utf-8")
    assert "hunter2" not in texto and "ghp_" + "a" * 20 not in texto


def test_falha_de_escrita_e_silenciosa(tmp_path, monkeypatch):
    ficheiro = tmp_path / "ocupado"
    ficheiro.write_text("x")
    monkeypatch.setenv("KF_ERRLOG", str(ficheiro / "errors.jsonl"))  # pasta pai é um ficheiro
    assert kf_errlog.registar("sp-x", "boom", args=[]) is False


def test_rotacao(log, monkeypatch):
    monkeypatch.setattr(kf_errlog, "MAX_BYTES", 50)
    kf_errlog.registar("a", "um", args=[])
    kf_errlog.registar("b", "dois", args=[])
    assert log.with_name("errors.jsonl.1").exists()
    assert len(linhas(log)) == 1


def test_local_por_defeito_sem_env(monkeypatch, tmp_path):
    monkeypatch.delenv("KF_ERRLOG", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert kf_errlog.caminho_log() == tmp_path / "kaizen-flow" / "errors.jsonl"


# --- wrapper -----------------------------------------------------------------


def test_wrapper_rc_zero_nao_regista(log):
    assert kf_errlog.executar("s", lambda: 0, argv=[]) == 0
    assert not log.exists()


def test_wrapper_rc_nao_zero_regista_e_mantem_rc_e_stderr(log, capsys):
    def main():
        print("erro: coisa", file=sys.stderr)
        return 3

    assert kf_errlog.executar("s", main, argv=["x"]) == 3
    assert "erro: coisa" in capsys.readouterr().err
    (l,) = linhas(log)
    assert l["rc"] == 3 and l["mensagem"] == "erro: coisa" and l["args"] == ["x"]


def test_wrapper_excecao_regista_e_repropaga(log):
    def main():
        raise KeyError("k")

    with pytest.raises(KeyError):
        kf_errlog.executar("s", main, argv=[])
    (l,) = linhas(log)
    assert l["tipo"] == "KeyError" and l["rc"] == 1


def test_wrapper_systemexit_texto_e_codigo(log):
    with pytest.raises(SystemExit) as e:
        kf_errlog.executar("s", lambda: sys.exit("SP não encontrado"), argv=[])
    assert e.value.code == "SP não encontrado"
    with pytest.raises(SystemExit) as e2:
        kf_errlog.executar("s", lambda: sys.exit(0), argv=[])
    assert e2.value.code == 0
    (l,) = linhas(log)
    assert l["mensagem"] == "SP não encontrado"


def test_wrapper_repoe_stderr(log):
    antes = sys.stderr
    kf_errlog.executar("s", lambda: 0, argv=[])
    assert sys.stderr is antes


def test_wrapper_com_log_inacessivel_nao_muda_rc(tmp_path, monkeypatch):
    ficheiro = tmp_path / "f"
    ficheiro.write_text("x")
    monkeypatch.setenv("KF_ERRLOG", str(ficheiro / "e.jsonl"))
    assert kf_errlog.executar("s", lambda: 5, argv=[]) == 5


# --- scripts ligados -----------------------------------------------------------

LIGADOS = sorted(p.name for p in Path(__file__).parent.glob("sp-*.py") if "kf_errlog.executar" in p.read_text(encoding="utf-8"))


def test_ha_scripts_ligados():
    assert len(LIGADOS) >= 15  # o script da tabela de painéis saiu com o backend de painéis


@pytest.mark.parametrize("nome", LIGADOS)
def test_script_ligado_regista_erro_simulado(nome, log):
    import os
    import subprocess

    env = dict(os.environ, KF_ERRLOG=str(log))
    r = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).with_name(nome)), "--opcao-que-nao-existe-xyz", "--outra-xyz"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert r.returncode != 0
    (l,) = linhas(log)
    assert l["script"] == nome[:-3] and l["rc"] == r.returncode
    assert l["args"] == ["--opcao-que-nao-existe-xyz", "--outra-xyz"]
    assert l["mensagem"]
