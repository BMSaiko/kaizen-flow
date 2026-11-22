"""Testes do arranque do sp-fila: sequencial nunca no checkout principal, painel por defeito, `--parar` sem filas órfãs."""
import json
from datetime import datetime

import sp_fila_execucao
from sp_fila_testlib import _estado, _pid_morto, make_sp, sp_fila
import contextlib


def test_sequencial_ensure_falhado_marca_falha_sem_mexer_no_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(sp_fila_execucao, "REPO", tmp_path)
    root = tmp_path / "sps"
    make_sp(root, "a")
    calls = []

    def run(argv, **_):
        calls.append(argv)

        class R:
            returncode = 1 if "ensure" in argv else 0
            stdout, stderr = "", "sem git"
        return R()
    st = _estado(tmp_path)
    sp_fila.seguinte(root, st, tmp_path / "rel", run, datetime(2026, 11, 22, 12, 0))
    assert not any("sp-move.py" in " ".join(map(str, c)) for c in calls)
    assert "a" in json.loads(st.with_name("ultima.json").read_text(encoding="utf-8"))["falhados"]


def test_arranque_sem_programa_nem_concorrencia_usa_painel(tmp_path, monkeypatch):
    vistos = {}
    monkeypatch.setattr(sp_fila.sp_fila_execucao, "_backend_defeito", lambda: object())
    monkeypatch.setattr(sp_fila, "load", lambda *a: [])

    def guardar(path, novo):
        vistos.update(novo)
        raise SystemExit(0)
    monkeypatch.setattr(sp_fila, "guardar", guardar)
    with contextlib.suppress(SystemExit):
        sp_fila.main(["--estado", str(tmp_path / "e.json"), "--root", str(tmp_path)])
    assert vistos["concorrencia"] == 1 and vistos["max"] == sp_fila.MAX_DEFEITO


def test_parar_remove_filas_de_paineis_orfas_e_poupa_as_vivas(tmp_path, monkeypatch):
    monkeypatch.setenv("SP_FILA_ROOT", str(tmp_path / "pf"))
    morta = sp_fila.sp_fila_paineis.pe.criar_fila(None)
    viva = sp_fila.sp_fila_paineis.pe.criar_fila(None, agora=datetime(2026, 1, 1))
    pasta = tmp_path / "pf"
    (pasta / morta / "vigia.pid").write_text(str(_pid_morto()), encoding="utf-8")
    import os
    (pasta / viva / "vigia.pid").write_text(str(os.getpid()), encoding="utf-8")
    mae = sp_fila.sp_fila_paineis.pe.criar_fila("mae")
    assert sp_fila.main(["--parar", "--estado", str(tmp_path / "nada.json")]) == 0
    assert not (pasta / morta).exists()
    assert (pasta / viva).exists() and (pasta / mae).exists()
    assert json.loads((pasta / viva / "fila.json").read_text(encoding="utf-8"))["fila"] == viva


def test_parar_poupa_fila_com_sp_ativo_e_fila_recem_criada_sem_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("SP_FILA_ROOT", str(tmp_path / "pf"))
    pe = sp_fila.sp_fila_paineis.pe
    pasta = tmp_path / "pf"
    ativa = pe.criar_fila(None)
    (pasta / ativa / "vigia.pid").write_text(str(_pid_morto()), encoding="utf-8")
    pe.registar(ativa, "s1")
    pe.transitar("s1", "a-correr", fila=ativa)
    nova = pe.criar_fila(None, agora=datetime(2026, 1, 2))
    velha = pe.criar_fila(None, agora=datetime(2026, 1, 3))
    import os
    os.utime(pasta / velha / "fila.json", (0, 0))
    assert sp_fila.filas_orfas() == [velha]
    assert nova not in sp_fila.filas_orfas() and ativa not in sp_fila.filas_orfas()
