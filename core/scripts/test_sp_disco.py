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


# --- lock exclusivo por SP com heartbeat (EC-041/042/043, EC-027) ---

def _pid_morto():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_lock_sp_livre_cria_e_liberta(tmp_path):
    """EC-043: o dono grava pid, painel e heartbeat; libertar apaga o lock."""
    with sp_disco.lock_sp(tmp_path, "sp-a", painel="p1"):
        d = sp_disco.dono(tmp_path, "sp-a")
        assert d["estado"] == "vivo" and d["pid"] == os.getpid() and d["painel"] == "p1"
    assert sp_disco.dono(tmp_path, "sp-a")["estado"] == "livre"


def test_lock_sp_segundo_painel_e_recusado_com_o_dono(tmp_path):
    """EC-043 / EC-042: lock vivo nunca é roubado; o erro indica o painel dono."""
    with sp_disco.lock_sp(tmp_path, "sp-a", painel="p1"):
        with pytest.raises(sp_disco.LockOcupado) as e:
            with sp_disco.lock_sp(tmp_path, "sp-a", painel="p2"):
                pass
        assert e.value.dono["painel"] == "p1"
        assert sp_disco.dono(tmp_path, "sp-a")["pid"] == os.getpid()


def test_lock_sp_pid_morto_e_orfao_e_recuperado(tmp_path):
    """EC-027 / EC-041: dono morto = órfão; o lock é recuperado por quem retoma."""
    sp_disco.escrever_lock_sp(tmp_path, "sp-a", {"pid": _pid_morto(), "painel": "p0", "hb": time.time()})
    assert sp_disco.dono(tmp_path, "sp-a")["estado"] == "orfao"
    with sp_disco.lock_sp(tmp_path, "sp-a", painel="p2"):
        assert sp_disco.dono(tmp_path, "sp-a")["painel"] == "p2"


def test_lock_sp_heartbeat_antigo_e_orfao_mesmo_com_pid_vivo(tmp_path):
    """EC-027: pid vivo mas heartbeat parado (processo preso/pid reutilizado) = órfão."""
    sp_disco.escrever_lock_sp(tmp_path, "sp-a", {"pid": os.getpid(), "painel": "p0", "hb": time.time() - sp_disco.HEARTBEAT_VELHO_S - 5})
    assert sp_disco.dono(tmp_path, "sp-a")["estado"] == "orfao"


def test_heartbeat_renova_o_lock(tmp_path):
    with sp_disco.lock_sp(tmp_path, "sp-a", painel="p1") as lk:
        antes = sp_disco.dono(tmp_path, "sp-a")["hb"]
        time.sleep(0.02)
        lk.heartbeat()
        assert sp_disco.dono(tmp_path, "sp-a")["hb"] > antes


def test_lock_sp_corrompido_vai_para_quarentena(tmp_path):
    """EC-041: lock ilegível é movido para `.corrupt-*` (nunca apagado) e o SP fica livre."""
    p = sp_disco.caminho_lock_sp(tmp_path, "sp-a")
    p.parent.mkdir(parents=True)
    p.write_text("{a meio", encoding="utf-8")
    d = sp_disco.dono(tmp_path, "sp-a")
    assert d["estado"] == "corrompido"
    with sp_disco.lock_sp(tmp_path, "sp-a", painel="p1"):
        pass
    assert list(p.parent.glob("sp-a.lock.json.corrupt-*"))


def test_lock_sp_corrida_de_dois_processos_so_um_ganha(tmp_path):
    """EC-043: duas tentativas simultâneas, exatamente uma entra."""
    codigo = (
        "import sys, time, sp_disco\n"
        "try:\n"
        "    with sp_disco.lock_sp(sys.argv[1], 'sp-a', painel=sys.argv[2]):\n"
        "        print('ganhou', flush=True); time.sleep(1.5)\n"
        "except sp_disco.LockOcupado:\n"
        "    print('recusado', flush=True)\n"
    )
    scripts = os.path.dirname(os.path.abspath(__file__))
    env = {**os.environ, "PYTHONPATH": scripts}
    ps = [subprocess.Popen([sys.executable, "-c", codigo, str(tmp_path), f"p{i}"], stdout=subprocess.PIPE, text=True, env=env) for i in range(2)]
    saidas = sorted(p.communicate()[0].strip() for p in ps)
    assert saidas == ["ganhou", "recusado"]


def test_lock_sem_pid_so_expira_pelo_silencio_do_heartbeat(tmp_path):
    """EC-027: dono sem processo (michi por CLI): vivo com heartbeat recente, órfão depois de HEARTBEAT_SEM_PID_S."""
    lk = sp_disco.tomar_lock(tmp_path, "sp-a", painel="p1", pid=None)
    assert sp_disco.dono(tmp_path, "sp-a")["estado"] == "vivo"
    assert sp_disco.dono(tmp_path, "sp-a", agora=time.time() + sp_disco.HEARTBEAT_SEM_PID_S + 5)["estado"] == "orfao"
    sp_disco.renovar_lock(tmp_path, "sp-a")
    assert sp_disco.libertar_lock(tmp_path, "sp-a", pid=None) is True
    assert sp_disco.dono(tmp_path, "sp-a")["estado"] == "livre"
    assert lk.pid is None
