"""Testes de sp_fila_nucleo.py e dos subcomandos do sp-fila (run|status|watch|stop|resume|gastos, --motor herdr)."""
import json

import pytest

import sp_fila_nucleo as nucleo
import sp_painel_estado as pe
from herdr_fake import FakeHerdr
from sp_fila_testlib import _estado, _runner, make_sp, sp_fila


_real_backend_defeito = None


def _real():
    import importlib.util
    spec = importlib.util.find_spec("sp_fila_execucao")
    src = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(src)  # cópia limpa: o conftest só altera o módulo já importado
    return src._backend_defeito


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    monkeypatch.setattr(nucleo, "HERDR_RUN", None)
    monkeypatch.setattr(nucleo, "RUN", None)


def test_traduzir_subcomandos_para_flags_antigas():
    assert nucleo.traduzir(["stop"]) == ("stop", ["--parar"])
    assert nucleo.traduzir(["gastos", "--estado", "x"]) == ("gastos", ["--gastos", "--estado", "x"])
    assert nucleo.traduzir(["run", "--max", "2"]) == ("run", ["--max", "2"])
    assert nucleo.traduzir(["--dry-run", "--max", "2"]) == ("run", ["--dry-run", "--max", "2"])  # alias: sem subcomando = run


def test_run_motor_herdr_corre_uma_fila_no_fake(tmp_path, monkeypatch, capsys):
    global _real_backend_defeito
    _real_backend_defeito = _real()
    root = tmp_path / "sps"
    make_sp(root, "a")
    fake = FakeHerdr()
    calls = []
    monkeypatch.setattr(nucleo, "HERDR_RUN", fake)
    monkeypatch.setattr(nucleo, "RUN", _runner(calls))
    monkeypatch.setattr(sp_fila.sp_fila_execucao, "_backend_defeito", _real_backend_defeito)  # o conftest troca-o por um falso
    monkeypatch.setattr(sp_fila, "_arrancar_vigia", lambda estado: None)
    monkeypatch.setattr(sp_fila.sp_fila_paineis, "enviar_prompt", lambda *a, **k: None)  # o ecrã do fake não tem `❯` (e2e real: F5)
    monkeypatch.setattr(sp_fila.sp_fila_paineis, "_em_master", lambda *a, **k: True)
    st = tmp_path / "estado.json"
    rc = sp_fila.main(["run", "--motor", "herdr", "--concorrencia", "1", "--root", str(root), "--estado", str(st),
                       "--relatorios", str(tmp_path / "rel")])
    out = capsys.readouterr().out
    assert rc == 0 and "lançado em painéis · a" in out
    estado = json.loads(st.read_text(encoding="utf-8"))
    assert pe.ler(estado["fila_paineis"], "a")["estado"] == "a-correr"
    assert any(c[1:3] == ["pane", "run"] and "claude --model" in c[4] for c in fake.chamadas)  # agente lançado via herdr
    assert len(fake.panes) == 1


def _fila_com(tmp_path, monkeypatch, slugs):
    monkeypatch.setenv(pe.ENV_ROOT, str(tmp_path / "pe"))
    fila = pe.criar_fila("mae")
    for s in slugs:
        pe.registar(fila, s, worktree=f"/wt/sb-{s}")
    return fila


def test_resume_readota_vivos_marca_mortos_e_nao_duplica(tmp_path, monkeypatch):
    fila = _fila_com(tmp_path, monkeypatch, ["a", "b"])
    fake = FakeHerdr()
    viva = fake._novo_pane("w1", "w1:t1", "/wt/sb-a")
    for s, p in (("a", viva), ("b", "w1:p999")):
        assert pe.reclamar_vaga(s, fila=fila, pane=p)
    estado = {"fila_paineis": fila, "sessoes": {"a": {"worktree": "/wt/sb-a"}, "b": {"worktree": "/wt/sb-b"}}, "falhados": [], "feitos": []}
    out = nucleo.retomar(estado, nucleo.herdr_ops.HerdrOps(run=fake))
    assert out == {"adotados": ["a"], "mortos": ["b"]}
    assert list(estado["sessoes"]) == ["a"] and estado["falhados"] == ["b"]
    assert pe.ler(fila, "b")["estado"] == "falhou" and pe.ler(fila, "a")["estado"] == "a-correr"
    assert not [c for c in fake.chamadas if c[1:3] in (["pane", "run"], ["tab", "create"], ["workspace", "create"])]
    # idempotente
    assert nucleo.retomar(estado, nucleo.herdr_ops.HerdrOps(run=fake)) == {"adotados": ["a"], "mortos": []}
    assert estado["falhados"] == ["b"]


def test_main_resume_relanca_o_vigia(tmp_path, monkeypatch, capsys):
    fila = _fila_com(tmp_path, monkeypatch, ["a"])
    fake = FakeHerdr()
    viva = fake._novo_pane("w1", "w1:t1", "/wt/sb-a")
    pe.reclamar_vaga("a", fila=fila, pane=viva)
    st = _estado(tmp_path, fila_paineis=fila, concorrencia=1, sessoes={"a": {"worktree": "/wt/sb-a"}})
    vigias = []
    monkeypatch.setattr(nucleo, "HERDR_RUN", fake)
    monkeypatch.setattr(sp_fila, "_arrancar_vigia", lambda e: vigias.append(e))
    assert sp_fila.main(["resume", "--estado", str(st)]) == 0
    assert vigias == [st] and "adotados: a" in capsys.readouterr().out
    assert list(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == ["a"]


def test_resume_sem_fila_da_erro(tmp_path, capsys):
    assert sp_fila.main(["resume", "--estado", str(tmp_path / "nada.json")]) == 1
    assert "sem fila em curso" in capsys.readouterr().err


def test_aliases_stop_e_gastos(tmp_path, capsys):
    st = _estado(tmp_path)
    assert sp_fila.main(["gastos", "--estado", str(st)]) == 0
    assert sp_fila.main(["stop", "--estado", str(st)]) == 0
    assert not st.exists() and "fila abandonada" in capsys.readouterr().out


def test_status_lista_filas(tmp_path, monkeypatch, capsys):
    _fila_com(tmp_path, monkeypatch, ["a"])
    assert sp_fila.main(["status"]) == 0
    assert "a" in capsys.readouterr().out


def test_motor_defeito_herdr_com_fallback():
    assert nucleo.motor_defeito(which=lambda _: "/usr/bin/herdr") == "herdr"
    assert nucleo.motor_defeito(which=lambda _: None) == "antigo"


def test_motor_antigo_ainda_escolhivel(tmp_path):
    nucleo.MOTOR_ATUAL = "herdr"
    sp_fila.main(["--motor", "antigo", "--dry-run", "--root", str(tmp_path / "sps"), "--estado", str(tmp_path / "e.json")])
    assert nucleo.MOTOR_ATUAL == "antigo"
