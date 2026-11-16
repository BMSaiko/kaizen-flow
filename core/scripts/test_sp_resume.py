"""Testes de sp-resume: retoma de SPs interrompidos (EC-001, EC-027, EC-043, UC-031, UC-032)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import kaizen_engine
import sp_disco
import sp_journal

SR = kaizen_engine.load("sp-resume")
SCRIPT = Path(__file__).resolve().parent / "sp-resume.py"
SLUG = "sp-r"


def _passos(raiz, slug, seq):
    for fase, passo, ev in seq:
        {"inicio": sp_journal.inicio, "fim": sp_journal.fim}[ev](raiz, slug, fase, passo)


def test_candidatos_so_orfaos_fora_de_done_ec027(tmp_path):
    _passos(tmp_path, "a", [("dp", "p1", "inicio")])
    _passos(tmp_path, "b", [("dp", "p1", "inicio")])
    _passos(tmp_path, "c", [("dp", "p1", "inicio")])
    done = tmp_path / "knowledge" / "projects" / "x" / "y" / "sp" / "Done"
    done.mkdir(parents=True)
    (done / "c.md").write_text("x", encoding="utf-8")
    lk = sp_disco.tomar_lock(tmp_path, "b", "painel-b")  # b em curso (este processo vivo)
    try:
        assert SR.candidatos(tmp_path) == ["a"]
    finally:
        sp_disco.libertar_lock(tmp_path, "b")
    assert lk.slug == "b"


def test_sem_candidatos_rc0_nada_a_retomar(tmp_path, capsys):
    assert SR.main(["--raiz", str(tmp_path)]) == 0
    assert "nada a retomar" in capsys.readouterr().out


def test_varios_candidatos_lista_e_pede_escolha(tmp_path, capsys):
    _passos(tmp_path, "a", [("dp", "p1", "inicio")])
    _passos(tmp_path, "b", [("da", "p1", "inicio")])
    assert SR.main(["--raiz", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "a" in out and "b" in out


def test_um_candidato_retoma_ec001(tmp_path, capsys):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio"), ("dp", "p1", "fim"), ("da", "p2", "inicio")])
    assert SR.main(["--raiz", str(tmp_path)]) == 0
    assert "em da" in capsys.readouterr().out


def test_passo_concluido_nao_corre_duas_vezes_ec001(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio"), ("dp", "p1", "fim"), ("da", "p2", "inicio")])
    ponto = SR.ponto_de_retoma(tmp_path, SLUG)
    assert ponto["ultimo_fim"] == {"fase": "dp", "passo": "p1"}
    assert [a["passo"] for a in ponto["abertos"]] == ["p2"]  # só p2 é repetido
    assert ponto["acao"] == "repetir" and ponto["fase"] == "da"


def test_passo_nao_idempotente_pede_reverter(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "p1", idempotente=False)
    ponto = SR.ponto_de_retoma(tmp_path, SLUG)
    assert ponto["acao"] == "reverter"
    rc, texto = SR.resume(tmp_path, SLUG)
    assert rc == 0 and "michi-checkpoint.py restore" in texto and "--apply" in texto


def test_from_fase_invalida_rc2_com_lista(tmp_path):
    rc, texto = SR.resume(tmp_path, SLUG, from_fase="nao-existe")
    assert rc == 2 and all(f in texto for f in SR.FASES)


def test_from_fase_reverte_abertos_a_partir_dela(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio"), ("dp", "p1", "fim"), ("da", "p2", "inicio")])
    rc, texto = SR.resume(tmp_path, SLUG, from_fase="dp")
    assert rc == 0 and "em dp" in texto
    assert SR.ponto_de_retoma(tmp_path, SLUG)["abertos"] == []


def test_restart_sem_confirmacao_nao_altera_uc032(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio")])
    antes = sp_journal.caminhos(tmp_path, SLUG)[1].read_bytes()
    for confirmar in (None, lambda: False):
        rc, _ = SR.resume(tmp_path, SLUG, restart=True, confirmar=confirmar)
        assert rc == 1
    assert sp_journal.caminhos(tmp_path, SLUG)[1].read_bytes() == antes


def test_restart_confirmado_arquiva_sem_apagar_uc032(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio"), ("dp", "p1", "fim")])
    rc, texto = SR.resume(tmp_path, SLUG, restart=True, confirmar=lambda: True)
    assert rc == 0
    arquivo = list((tmp_path / ".kaizen" / "estado" / "arquivo").iterdir())
    assert len(arquivo) == 1 and (arquivo[0] / f"{SLUG}.journal.jsonl").exists() and (arquivo[0] / f"{SLUG}.json").exists()
    assert not sp_journal.caminhos(tmp_path, SLUG)[0].exists()
    assert SR.candidatos(tmp_path) == []


def test_segundo_painel_recebe_ec043_com_dono(tmp_path):
    sp_disco.tomar_lock(tmp_path, SLUG, "painel-7")
    try:
        rc, texto = SR.resume(tmp_path, SLUG)
    finally:
        sp_disco.libertar_lock(tmp_path, SLUG)
    assert rc == 1 and "EC-043" in texto and "painel-7" in texto and texto.count("·") >= 3


def test_lock_unlock_cli_ec043(tmp_path, capsys):
    assert SR.main(["--raiz", str(tmp_path), SLUG, "--lock", "--painel", "p1"]) == 0
    assert sp_disco.dono(tmp_path, SLUG)["estado"] == "vivo"
    assert SR.main(["--raiz", str(tmp_path), SLUG, "--lock"]) == 1
    assert "EC-043" in capsys.readouterr().err
    assert SR.main(["--raiz", str(tmp_path), SLUG, "--unlock"]) == 0
    assert sp_disco.dono(tmp_path, SLUG)["estado"] == "livre"


def test_help_rc0():
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--restart" in r.stdout


def test_decisao_de_retoma_menos_de_2s(tmp_path):
    for i in range(200):
        sp_journal.inicio(tmp_path, SLUG, "da", f"p{i}")
        sp_journal.fim(tmp_path, SLUG, "da", f"p{i}")
    t = time.perf_counter()
    SR.ponto_de_retoma(tmp_path, SLUG)
    SR.candidatos(tmp_path)
    assert time.perf_counter() - t < 2


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.tuples(st.sampled_from(["dp", "da", "gates"]), st.sampled_from(["p1", "p2", "p3"]), st.sampled_from(["inicio", "fim"])), max_size=12))
def test_ponto_de_retoma_nunca_repete_passo_fechado(tmp_path_factory, seq):
    raiz = tmp_path_factory.mktemp("h")
    _passos(raiz, SLUG, seq)
    ponto = SR.ponto_de_retoma(raiz, SLUG)
    est = sp_journal.estado(raiz, SLUG)
    assert sorted(a["passo"] for a in ponto["abertos"]) == sorted(est.interrompidos)
    assert ponto["acao"] == est.acao
