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
    with pytest.raises(TimeoutError), sp_disco.bloqueio(tmp_path / "estado", espera=0.3):
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
        with pytest.raises(sp_disco.LockOcupado) as e, sp_disco.lock_sp(tmp_path, "sp-a", painel="p2"):
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
        "import sys, time, pathlib, sp_disco\n"
        "sinal = pathlib.Path(sys.argv[1], 'recusou.flag')\n"
        "try:\n"
        "    with sp_disco.lock_sp(sys.argv[1], 'sp-a', painel=sys.argv[2]):\n"
        "        print('ganhou', flush=True)\n"
        "        limite = time.monotonic() + 10\n"  # segura o lock até o outro ser recusado
        "        while not sinal.exists() and time.monotonic() < limite:\n"
        "            time.sleep(0.01)\n"
        "except sp_disco.LockOcupado:\n"
        "    print('recusado', flush=True); sinal.touch()\n"
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


def test_renovar_lock_so_de_dono_vivo_e_proprio_ec027(tmp_path):
    assert sp_disco.renovar_lock(tmp_path, "x") is False  # sem lock: nunca recria
    assert not sp_disco.caminho_lock_sp(tmp_path, "x").exists()
    sp_disco.escrever_lock_sp(tmp_path, "x", {"pid": os.getpid() + 1, "painel": "p", "ts": 1.0, "hb": time.time()})
    antes = sp_disco.ler_json(sp_disco.caminho_lock_sp(tmp_path, "x"))["hb"]
    assert sp_disco.renovar_lock(tmp_path, "x") is False  # pid alheio
    assert sp_disco.ler_json(sp_disco.caminho_lock_sp(tmp_path, "x"))["hb"] == antes


def test_heartbeat_do_dono_antigo_nao_pisa_o_novo(tmp_path):
    antigo = sp_disco.tomar_lock(tmp_path, "x", "p1", pid=None)
    sp_disco.escrever_lock_sp(tmp_path, "x", {"pid": None, "painel": "p2", "ts": antigo.ts + 1, "hb": time.time()})
    assert antigo.heartbeat() is False
    assert sp_disco.ler_json(sp_disco.caminho_lock_sp(tmp_path, "x"))["painel"] == "p2"


def test_libertar_lock_sem_chave_pid_vai_para_quarentena(tmp_path):
    p = sp_disco.caminho_lock_sp(tmp_path, "x")
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert sp_disco.libertar_lock(tmp_path, "x", pid=None) is False
    assert not p.exists() and list(p.parent.glob("*.corrupt-*"))


def test_tomar_e_heartbeat_menos_de_200ms(tmp_path):
    t = time.perf_counter()
    lk = sp_disco.tomar_lock(tmp_path, "x", "p")
    lk.heartbeat()
    assert time.perf_counter() - t < 0.2


def test_maquina_de_estados_do_lock_contra_modelo_de_referencia(tmp_path_factory):
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st

    @settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.lists(st.sampled_from(["tomar", "libertar", "renovar", "expirar"]), max_size=15))
    def corre(ops):
        raiz = tmp_path_factory.mktemp("m")
        modelo = "livre"  # livre | vivo | orfao
        for op in ops:
            if op == "tomar":
                if modelo == "vivo":
                    with pytest.raises(sp_disco.LockOcupado):
                        sp_disco.tomar_lock(raiz, "x", "p", pid=None)
                else:
                    sp_disco.tomar_lock(raiz, "x", "p", pid=None)
                    modelo = "vivo"
            elif op == "libertar":
                sp_disco.libertar_lock(raiz, "x", pid=None)
                modelo = "livre"
            elif op == "renovar":
                assert sp_disco.renovar_lock(raiz, "x") is (modelo == "vivo")  # orfao nunca ressuscita
            elif modelo != "livre":
                d = sp_disco.ler_json(sp_disco.caminho_lock_sp(raiz, "x"))
                d["hb"] = time.time() - 99999
                sp_disco.escrever_lock_sp(raiz, "x", d)
                modelo = "orfao"
            assert sp_disco.dono(raiz, "x")["estado"] == modelo
            assert len(list(sp_disco.caminho_lock_sp(raiz, "x").parent.glob("x.lock.json"))) == (modelo != "livre")

    corre()
