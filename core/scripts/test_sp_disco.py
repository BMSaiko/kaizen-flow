"""Testes de scripts/sp_disco.py: bloqueio, escrita atómica e leitura tolerante de JSON."""
import json
import os
import subprocess
import sys
import time

import pytest

import sp_disco


def test_ler_json_tolerante(tmp_path):
    assert sp_disco.ler_json(tmp_path / "nao-existe.json") is None
    assert sp_disco.ler_json(tmp_path / "nao-existe.json", {}) == {}
    mau = tmp_path / "mau.json"
    mau.write_text("{a meio", encoding="utf-8")
    assert sp_disco.ler_json(mau, {"x": 1}) == {"x": 1}
    bom = tmp_path / "bom.json"
    bom.write_text('{"a": 1}', encoding="utf-8")
    assert sp_disco.ler_json(bom) == {"a": 1}


def test_guardar_escreve_json_e_nao_deixa_temporarios(tmp_path):
    p = tmp_path / "e.json"
    sp_disco.guardar(p, {"nome": "ação"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"nome": "ação"}
    assert "ação" in p.read_text(encoding="utf-8")  # ensure_ascii=False
    sp_disco.guardar(p, {"nome": "b"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"nome": "b"}
    assert [f.name for f in tmp_path.iterdir()] == ["e.json"]


def test_bloqueio_cria_e_larga_o_lock(tmp_path):
    alvo = tmp_path / "estado"
    with sp_disco.bloqueio(alvo):
        lock = tmp_path / "estado.lock"
        assert int(lock.read_text(encoding="utf-8")) == os.getpid()
    assert not lock.exists()


def test_bloqueio_recupera_lock_de_dono_morto(tmp_path):
    morto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    (tmp_path / "estado.lock").write_text(morto.stdout.strip(), encoding="utf-8")
    with sp_disco.bloqueio(tmp_path / "estado", espera=5):
        pass
    assert not (tmp_path / "estado.lock").exists()


def test_bloqueio_nunca_apaga_lock_de_dono_vivo(tmp_path):
    (tmp_path / "estado.lock").write_text(str(os.getpid()), encoding="utf-8")
    with pytest.raises(TimeoutError):
        with sp_disco.bloqueio(tmp_path / "estado", espera=0.3):
            pass
    assert (tmp_path / "estado.lock").exists()


def test_bloqueio_recupera_lock_sem_pid_por_idade(tmp_path):
    lock = tmp_path / "estado.lock"
    lock.write_text("", encoding="utf-8")
    velho = time.time() - sp_disco.LOCK_VELHO_S - 5
    os.utime(lock, (velho, velho))
    with sp_disco.bloqueio(tmp_path / "estado", espera=5):
        pass


def test_pid_vivo():
    assert sp_disco.pid_vivo(os.getpid())
    assert not sp_disco.pid_vivo(0)
