"""Testes de scripts/sp-fila.py: estado em disco (bloqueio, escrita atómica, estado corrompido)."""
import json
import os
import time
import pytest
import sp_fila_estado
from datetime import datetime
from pathlib import Path
from sp_fila_testlib import (
    sp_fila,
    make_sp,
    _runner,
    _estado,
    _pid_morto,
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


def _arranca(tmp_path, root, *extra):
    return sp_fila.main(["--root", str(root), "--estado", str(tmp_path / "estado.json"), "--relatorios", str(tmp_path / "rel"), *extra])


def _obsoleta(tmp_path, root, **over):
    make_sp(root, "velho", folder="Done")
    make_sp(root, "novo")
    base = {"inicio": "2020-01-01T10:00:00", "sessoes": {"velho": {}}, "vigia": {"pid": 0, "ts": "2020-01-01T10:05:00", "incidentes": []}}
    base.update(over)
    return _estado(tmp_path, **base)


@pytest.fixture
def sem_lancar(monkeypatch):
    """Nenhum teste deste ficheiro lança uma sessão real: `seguinte` é trocado por um stub que só regista."""
    chamadas = []
    monkeypatch.setattr(sp_fila, "seguinte", lambda *a, **k: chamadas.append(1) or {"acao": "fim", "motivo": "teste", "relatorio": "-"})
    return chamadas


def _arquivadas(tmp_path):
    return sorted((tmp_path / "obsoletas").glob("*.json"))


def test_fila_obsoleta_arquiva_e_arranca(tmp_path, sem_lancar, capsys):
    root = tmp_path / "sps"
    st = _obsoleta(tmp_path, root, inicio=None)  # sem data legível
    antes = st.read_text(encoding="utf-8")
    assert _arranca(tmp_path, root) == 0
    err = capsys.readouterr().err
    assert err.count("fila obsoleta arquivada:") == 1 and "EC-038" not in err
    arq = _arquivadas(tmp_path)
    assert len(arq) == 1 and arq[0].read_text(encoding="utf-8") == antes
    assert st.exists() and sp_fila.ler(st).get("inicio")  # estado novo


def test_fila_antiga_arquiva_e_arranca(tmp_path, sem_lancar, capsys):
    root = tmp_path / "sps"
    _obsoleta(tmp_path, root)
    assert _arranca(tmp_path, root) == 0
    assert "fila obsoleta arquivada:" in capsys.readouterr().err and len(_arquivadas(tmp_path)) == 1


def test_vigia_vivo_protege_a_fila(tmp_path, sem_lancar, monkeypatch, capsys):
    root = tmp_path / "sps"
    st = _obsoleta(tmp_path, root, fila_paineis="fila-y")
    pidfile = tmp_path / "vigia.pid"
    pidfile.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(sp_fila.sp_vigia, "caminhos", lambda pasta: (pidfile, None, None))
    monkeypatch.setattr(sp_fila.sp_fila_paineis.pe, "pid_vivo", lambda pid: True)
    assert _arranca(tmp_path, root) == 1
    assert "fila já em curso" in capsys.readouterr().err and st.exists() and not _arquivadas(tmp_path)


def test_pidfile_ilegivel_conta_como_viva(tmp_path, monkeypatch):
    pidfile = tmp_path / "vigia.pid"
    pidfile.write_text("lixo", encoding="utf-8")
    monkeypatch.setattr(sp_fila.sp_vigia, "caminhos", lambda pasta: (pidfile, None, None))
    assert sp_fila.vigia_vivo({"fila_paineis": "f"}) is True
    pidfile.unlink()
    assert sp_fila.vigia_vivo({"fila_paineis": "f"}) is False
    assert sp_fila.vigia_vivo({}) is False


def test_dry_run_diz_arquivaria_sem_tocar(tmp_path, capsys):
    root = tmp_path / "sps"
    st = _obsoleta(tmp_path, root)
    antes = st.read_text(encoding="utf-8")
    assert _arranca(tmp_path, root, "--dry-run") == 0
    assert "arquivaria" in capsys.readouterr().out
    assert st.read_text(encoding="utf-8") == antes and not _arquivadas(tmp_path)


def test_json_corrompido_da_ec045_e_fica_intacto(tmp_path, capsys):
    root = tmp_path / "sps"
    make_sp(root, "novo")
    st = tmp_path / "estado.json"
    st.write_text("{truncado", encoding="utf-8")
    assert _arranca(tmp_path, root) == 1
    assert st.read_text(encoding="utf-8") == "{truncado" and not _arquivadas(tmp_path)


def test_flag_abandonar_obsoleta_continua_aceite(tmp_path, sem_lancar):
    root = tmp_path / "sps"
    _obsoleta(tmp_path, root)
    assert _arranca(tmp_path, root, "--abandonar-obsoleta") == 0


def test_fila_viva_nunca_e_tocada(tmp_path, capsys):
    root = tmp_path / "sps"
    agora = datetime.now().isoformat(timespec="seconds")
    make_sp(root, "em-curso", folder="Doing")
    st = _estado(tmp_path, inicio="2020-01-01T10:00:00", sessoes={"em-curso": {}}, vigia={"pid": 0, "ts": "2020-01-01T10:05:00", "incidentes": []})
    assert _arranca(tmp_path, root, "--abandonar-obsoleta") == 1
    assert "fila já em curso" in capsys.readouterr().err and st.exists()
    st.write_text(json.dumps({"inicio": agora, "sessoes": {}, "vigia": {"pid": 0, "ts": agora}}), encoding="utf-8")
    assert _arranca(tmp_path, root, "--abandonar-obsoleta") == 1 and st.exists()


def test_fila_vazia_antiga_e_obsoleta(tmp_path):
    items = sp_fila.load(tmp_path / "sps", None)
    antigo = {"inicio": "2020-01-01T10:00:00", "sessoes": {}}
    assert "nenhum SP em Doing" in sp_fila.fila_obsoleta(antigo, items, datetime(2026, 11, 9))
    assert sp_fila.fila_obsoleta({"inicio": "2026-11-09T11:30:00", "sessoes": {}}, items, datetime(2026, 11, 9, 12)) is None


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
    real, falhas = sp_fila_estado.os.open, []

    def open_instavel(p, *a, **k):
        if str(p).endswith(".lock") and len(falhas) < 3:
            falhas.append(p)
            raise PermissionError(13, "Acesso negado")
        return real(p, *a, **k)

    monkeypatch.setattr(sp_fila_estado.os, "open", open_instavel)
    sp_fila.atualizar(st, lambda e: e["sessoes"].update({"w": {}}))
    assert len(falhas) == 3 and "w" in json.loads(st.read_text(encoding="utf-8"))["sessoes"]


def test_permission_error_no_replace_e_tentado_de_novo(tmp_path, monkeypatch):
    # Windows: os.replace falha enquanto um leitor sem bloqueio tem o estado aberto
    st = _estado(tmp_path)
    real, falhas = sp_fila_estado.os.replace, []

    def replace_instavel(a, b):
        if len(falhas) < 3:
            falhas.append(a)
            raise PermissionError(13, "Acesso negado")
        return real(a, b)

    monkeypatch.setattr(sp_fila_estado.os, "replace", replace_instavel)
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
    with pytest.raises(TimeoutError), sp_fila.bloqueio(st, espera=0.2):
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


@pytest.mark.parametrize("flag", ["--gastos"])
def test_leituras_com_estado_corrompido_dao_erro_claro(tmp_path, capsys, flag):
    st = tmp_path / "e.json"
    st.write_text("{lixo", encoding="utf-8")
    assert sp_fila.main([flag, "--estado", str(st), "--root", str(tmp_path / "sps")]) == 1
    assert "ilegível" in capsys.readouterr().err


def test_parar_abandona_estado_corrompido(tmp_path, capsys):
    st = tmp_path / "e.json"
    st.write_text("{lixo", encoding="utf-8")
    assert sp_fila.main(["--parar", "--estado", str(st)]) == 0 and not st.exists()


def test_estado_por_mae_nao_se_partilha(tmp_path):
    import sp_fila_estado as fe
    a, b = fe.estado_de("mae-a", tmp_path), fe.estado_de("mae-b", tmp_path)
    assert a != b and a.name == "fila.json"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    fe.guardar(a, {"sessoes": {"ta1": {}}})
    fe.guardar(b, {"sessoes": {"tb1": {}}})
    assert fe.estados_existentes(tmp_path) == [a, b]
    assert fe.localizar("tb1", tmp_path, tmp_path / "x.json") == b
    assert fe.localizar("nada", tmp_path, tmp_path / "x.json") is None
    assert fe.localizar(None, tmp_path, tmp_path / "x.json") is None  # ambíguo: duas filas


def test_fila_de_paineis_nao_e_estado(tmp_path):
    """`fila-<id>/fila.json` dos painéis vive na mesma pasta: `localizar` cai no legado, não nele."""
    import sp_fila_estado as fe
    p = tmp_path / "fila-1" / "fila.json"
    p.parent.mkdir(parents=True)
    fe.guardar(p, {"fila": "fila-1", "ordem": ["s1"], "sessoes": {"s1": {}}})
    legado = tmp_path / "legado.json"
    fe.guardar(legado, {"max": None, "usados": 0, "sessoes": {"s1": {}}})
    assert fe.estados_existentes(tmp_path) == []
    assert fe.localizar("s1", tmp_path, legado) == legado
