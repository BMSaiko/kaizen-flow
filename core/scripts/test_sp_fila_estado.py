"""Testes de scripts/sp-fila.py: estado em disco (bloqueio, escrita atómica, estado corrompido)."""
import json
import os
import time
import pytest
from datetime import datetime
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    _runner,
    _estado,
    _pid_morto,
    vivo,
)


def test_paralelo_seguinte_sem_slug_da_erro_e_nao_fecha_nada(tmp_path):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    make_sp(root, "b", folder="Doing")
    make_sp(root, "c")
    st = _estado(tmp_path, concorrencia=2, max=9, sessoes={"a": {}, "b": {}})
    antes = st.read_text(encoding="utf-8")
    calls = []
    with pytest.raises(ValueError, match="--slug"):
        sp_fila.seguinte(root, st, tmp_path / "rel", _runner(calls), datetime(2026, 10, 25, 12, 0))
    assert st.read_text(encoding="utf-8") == antes and calls == []


def test_dois_escritores_simultaneos_nao_perdem_registos(tmp_path):
    import threading
    st = _estado(tmp_path)

    def escreve(prefixo):
        for i in range(15):
            sp_fila.atualizar(st, lambda e, k=f"{prefixo}{i}": e["sessoes"].update({k: {}}))

    ts = [threading.Thread(target=escreve, args=(p,)) for p in "xy"]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(json.loads(st.read_text(encoding="utf-8"))["sessoes"]) == 30


def test_permission_error_ao_libertar_bloqueio_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows: antivírus/indexador seguram o .lock; unlink falha com PermissionError e não pode matar o escritor
    st = _estado(tmp_path)
    real, falhas = Path.unlink, []

    def unlink_instavel(self, *a, **k):
        if str(self).endswith(".lock") and len(falhas) < 3:
            falhas.append(self)
            raise PermissionError(13, "Acesso negado")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", unlink_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and not Path(f"{st}.lock").exists()


def test_permission_error_ao_criar_bloqueio_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows devolve PermissionError (não FileExistsError) enquanto o dono apaga o .lock
    st = _estado(tmp_path)
    real, falhas = sp_fila.os.open, []

    def open_instavel(p, *a, **k):
        if str(p).endswith(".lock") and len(falhas) < 3:
            falhas.append(p)
            raise PermissionError(13, "Acesso negado")
        return real(p, *a, **k)

    monkeypatch.setattr(sp_fila.os, "open", open_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and "w" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_permission_error_no_replace_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows: os.replace falha enquanto um leitor sem bloqueio tem o estado aberto
    st = _estado(tmp_path)
    real, falhas = sp_fila.os.replace, []

    def replace_instavel(a, b):
        if len(falhas) < 3:
            falhas.append(a)
            raise PermissionError(13, "Acesso negado")
        return real(a, b)

    monkeypatch.setattr(sp_fila.os, "replace", replace_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and "w" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_bloqueio_antigo_e_removido_e_escrita_e_atomica(tmp_path):
    import os
    st = _estado(tmp_path)
    lock = Path(f"{st}.lock")
    lock.write_text("morto", encoding="utf-8")
    os.utime(lock, (0, 0))
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"z": {}}))
    assert not lock.exists() and "z" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]
    assert not list(tmp_path.glob("*.tmp"))


def test_bloqueio_com_pid_morto_e_recuperado_de_imediato(tmp_path):
    # lock recente (mtime de agora) mas o dono já morreu: não esperar os LOCK_VELHO_S
    st = _estado(tmp_path)
    lock = Path(f"{st}.lock")
    lock.write_text(str(_pid_morto()), encoding="utf-8")
    t0 = time.monotonic()
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"z": {}}))
    assert time.monotonic() - t0 < 5 and not lock.exists()
    assert "z" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_bloqueio_regista_o_pid_do_dono(tmp_path):
    st = _estado(tmp_path)
    with sp_fila.bloqueio(st):
        assert Path(f"{st}.lock").read_text(encoding="utf-8").strip() == str(os.getpid())


def test_bloqueio_com_pid_vivo_nao_e_roubado(tmp_path):
    st = _estado(tmp_path)
    lock = Path(f"{st}.lock")
    lock.write_text(str(os.getpid()), encoding="utf-8")
    with pytest.raises(TimeoutError):
        with sp_fila.bloqueio(st, espera=0.2):
            pass
    assert lock.exists()


def test_seguinte_com_estado_bloqueado_sai_rc1_sem_tocar_no_estado(tmp_path, monkeypatch, capsys):
    # caso observado: «estado bloqueado há demasiado tempo» com 2 painéis ainda a correr; a fila não acaba nem marca falhados
    st = _estado(tmp_path, sessoes={"a": {"painel": "1"}, "b": {"painel": "2"}})
    antes = st.read_bytes()

    def bloqueado(*a, **k):
        raise TimeoutError(f"estado bloqueado há demasiado tempo: {st}.lock")

    monkeypatch.setattr(sp_fila, "seguinte", bloqueado)
    rc = sp_fila.main(["--seguinte", "--slug", "a", "--estado", str(st), "--root", str(tmp_path), "--relatorios", str(tmp_path / "rel")])
    assert rc == 1 and st.read_bytes() == antes
    assert "bloqueado" in capsys.readouterr().err
    assert not (tmp_path / "rel").exists()


def test_vigia_sobrevive_a_estado_bloqueado_e_avisa(tmp_path):
    def bloqueado(*a, **k):
        raise TimeoutError("estado bloqueado há demasiado tempo")

    ok, razao = sp_fila.lancar_seguinte_auto("r", "e", "rel", "a", seguinte_fn=bloqueado)
    assert ok is False and "bloqueado" in razao


@pytest.mark.parametrize("n", ["0", "-1", "-3"])
def test_concorrencia_invalida_e_recusada_com_mensagem(tmp_path, capsys, n):
    rc = sp_fila.main(["--concorrencia", n, "--estado", str(tmp_path / "e.json"), "--root", str(tmp_path / "sps")])
    assert rc == 1 and "N >= 1" in capsys.readouterr().err
    assert not (tmp_path / "e.json").exists()


def test_estado_corrompido_da_erro_claro_e_nao_apaga(tmp_path, capsys):
    st = tmp_path / "e.json"
    st.write_text('{"max": 3, "sessoes": {', encoding="utf-8")
    rc = sp_fila.main(["--seguinte", "--estado", str(st), "--root", str(tmp_path / "sps")])
    assert rc == 1 and "ilegível" in capsys.readouterr().err
    assert st.read_text(encoding="utf-8").startswith('{"max"')  # intacto para diagnóstico


@pytest.mark.parametrize("flag", ["--estado-vivo", "--gastos"])
def test_leituras_com_estado_corrompido_dao_erro_claro(tmp_path, capsys, flag):
    st = tmp_path / "e.json"
    st.write_text("{lixo", encoding="utf-8")
    assert sp_fila.main([flag, "--estado", str(st), "--root", str(tmp_path / "sps")]) == 1
    assert "ilegível" in capsys.readouterr().err


def test_parar_abandona_estado_corrompido(tmp_path, capsys):
    st = tmp_path / "e.json"
    st.write_text("{lixo", encoding="utf-8")
    assert sp_fila.main(["--parar", "--estado", str(st)]) == 0 and not st.exists()
