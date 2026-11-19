"""Testes de falha (testes-falha-90 §4.4) dos caminhos de erro de sp_journal e sp_disco, em processo.

Sinais chamados no próprio processo (handlers repostos no fim), disco cheio, quarentena com colisão de nome,
cauda truncada, CLI, recuperação de lock a meio e heartbeat em thread. Herméticos: só `tmp_path`.

Uso: python -m pytest core/scripts/test_falha_journal_disco.py -q
rc: o do pytest
"""
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

import sp_disco
import sp_journal

SLUG = "sp-falha"
SCRIPTS = Path(__file__).resolve().parent
SINAIS = [s for s in (getattr(signal, n, None) for n in ("SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP")) if s is not None]


@pytest.fixture
def sinais_repostos():
    """Guarda e repõe os handlers: `instalar_sinais` em processo não pode vazar para os outros testes."""
    antes = {s: signal.getsignal(s) for s in SINAIS}
    yield
    for s, h in antes.items():
        signal.signal(s, h)


def _checkpoint(raiz):
    return json.loads(sp_journal.caminhos(raiz, SLUG)[0].read_bytes().decode("utf-8"))


# --- sinais ---

def test_ec_001_handler_sigint_grava_checkpoint_e_levanta_keyboardinterrupt(tmp_path, sinais_repostos):
    """EC-001: Ctrl+C a meio de um passo grava `interrompido`, repõe o handler anterior e sobe como KeyboardInterrupt."""
    anterior = signal.getsignal(signal.SIGINT)
    assert sp_journal.instalar_sinais(tmp_path, SLUG) is True
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    with pytest.raises(KeyboardInterrupt):
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
    cp = _checkpoint(tmp_path)
    assert cp["interrompido"] is True and (cp["fase"], cp["passo"]) == ("da", "p1")
    assert signal.getsignal(signal.SIGINT) is anterior
    assert sp_journal.estado(tmp_path, SLUG).interrompidos == ["p1"]


def test_ec_057_handler_sigterm_grava_checkpoint_e_sai_com_128_mais_sinal(tmp_path, sinais_repostos):
    """EC-057: pedido de fecho (SIGTERM) grava o checkpoint e sai com 128+15."""
    sp_journal.instalar_sinais(tmp_path, SLUG)
    sp_journal.inicio(tmp_path, SLUG, "gates", "g2")
    with pytest.raises(SystemExit) as e:
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    assert e.value.code == 128 + int(signal.SIGTERM)
    assert _checkpoint(tmp_path)["interrompido"] is True


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP não existe no Windows (lá é CTRL_CLOSE_EVENT, EC-057)")
def test_ec_069_handler_sighup_grava_checkpoint(tmp_path, sinais_repostos):
    """EC-069: fechar o painel no Linux/macOS manda SIGHUP; sem handler o processo morria sem checkpoint."""
    sp_journal.instalar_sinais(tmp_path, SLUG)
    sp_journal.inicio(tmp_path, SLUG, "da", "p3")
    with pytest.raises(SystemExit) as e:
        signal.getsignal(signal.SIGHUP)(signal.SIGHUP, None)
    assert e.value.code == 128 + int(signal.SIGHUP)
    assert _checkpoint(tmp_path)["interrompido"] is True


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="SIGHUP não existe no Windows (lá é CTRL_CLOSE_EVENT, EC-057)")
def test_ec_069_sighup_num_processo_real_grava_checkpoint(tmp_path):
    """EC-069: processo filho real que recebe SIGHUP (painel fechado) deixa o checkpoint `interrompido`."""
    script = tmp_path / "filho.py"
    script.write_bytes((
        "import sys, time\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "import sp_journal\n"
        "sp_journal.instalar_sinais(sys.argv[1], sys.argv[2])\n"
        "sp_journal.inicio(sys.argv[1], sys.argv[2], 'da', 'longo')\n"
        "print('pronto', flush=True)\n"
        "for _ in range(600):\n"
        "    time.sleep(0.05)\n"
    ).encode())
    p = subprocess.Popen([sys.executable, str(script), str(tmp_path), SLUG], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "pronto"
        p.send_signal(signal.SIGHUP)
        p.wait(timeout=10)
    finally:
        if p.poll() is None:
            p.kill()
        p.stdout.close()
    assert p.returncode == 128 + int(signal.SIGHUP)
    assert _checkpoint(tmp_path)["interrompido"] is True
    assert sp_journal.estado(tmp_path, SLUG).interrompidos == ["longo"]


def test_ec_057_ao_interromper_com_disco_a_falhar_devolve_false(tmp_path, monkeypatch):
    """EC-057: sem conseguir gravar (disco cheio, permissões) o handler não rebenta: devolve False e deixa o sinal seguir."""
    def sem_disco(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sp_journal, "gravar_checkpoint", sem_disco)
    assert sp_journal._ao_interromper(tmp_path, SLUG) is False


def test_ec_042_ao_interromper_com_lock_preso_grava_na_mesma(tmp_path, monkeypatch):
    """EC-042: lock preso por outro processo na saída não impede o checkpoint."""
    def preso(*a, **k):
        raise TimeoutError("estado bloqueado")

    monkeypatch.setattr(sp_disco, "libertar_lock", preso)
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    assert sp_journal._ao_interromper(tmp_path, SLUG) is True
    assert _checkpoint(tmp_path)["interrompido"] is True


# --- quarentena e journal corrompido ---

class _RelogioParado(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, 6, tzinfo=timezone.utc)


def test_ec_050_quarentena_com_o_mesmo_carimbo_nunca_sobrescreve(tmp_path, monkeypatch):
    """EC-050: duas quarentenas no mesmo microssegundo ganham sufixo -1, -2; nenhuma cópia anterior se perde."""
    monkeypatch.setattr(sp_journal, "datetime", _RelogioParado)
    p = tmp_path / "x.json"
    destinos = []
    for i in range(3):
        p.write_bytes(b"mau %d" % i)
        destinos.append(sp_journal._quarentena(p))
    assert [d.name.rsplit("-", 1)[-1] for d in destinos[1:]] == ["1", "2"]
    assert [d.read_bytes() for d in destinos] == [b"mau 0", b"mau 1", b"mau 2"]
    b = [sp_journal._quarentena_bytes(p, b"c%d" % i) for i in range(2)]
    assert b[0] != b[1] and [d.read_bytes() for d in b] == [b"c0", b"c1"]


def test_ec_050_cauda_invalida_sem_newline_vai_para_quarentena_e_o_resto_fica(tmp_path):
    """EC-050: crash a meio da última linha deixa lixo sem `\\n`; o próximo evento isola-o e não perde os anteriores."""
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    jp = sp_journal.caminhos(tmp_path, SLUG)[1]
    with open(jp, "ab") as f:
        f.write(b'{"ts": "2026", "evento": "fi')
    sp_journal.fim(tmp_path, SLUG, "da", "p1")
    q = list(jp.parent.glob(f"{jp.name}.corrupt-*"))
    assert len(q) == 1 and q[0].read_bytes() == b'{"ts": "2026", "evento": "fi'
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == [] and est.acao == "nada"


def test_ec_050_cauda_valida_sem_newline_e_fechada_sem_quarentena(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    jp = sp_journal.caminhos(tmp_path, SLUG)[1]
    jp.write_bytes(jp.read_bytes().rstrip(b"\n"))
    sp_journal.fim(tmp_path, SLUG, "da", "p1")
    assert not list(jp.parent.glob("*.corrupt-*"))
    assert len(jp.read_bytes().splitlines()) == 2


@pytest.mark.parametrize("linha", [b"[1, 2]", b'"inicio"', b'{"evento": "inicio", "fase": 1, "passo": "x"}',
                                   b'{"evento": "inicio", "fase": "da", "passo": null}', b'{"evento": "outro", "fase": "a", "passo": "b"}'])
def test_ec_050_evento_com_forma_errada_e_rejeitado(linha):
    assert sp_journal._evento(linha) is None


def test_ec_050_journal_com_linha_de_forma_errada_vai_para_quarentena_e_reconstroi(tmp_path):
    jp = sp_journal.caminhos(tmp_path, SLUG)[1]
    jp.parent.mkdir(parents=True)
    jp.write_bytes(b'[1]\n{"evento": "inicio", "fase": "da", "passo": "a"}\n')
    sp = tmp_path / "sp.md"
    sp.write_bytes(b"---\r\nphase: DA\r\n---\r\n# t\r\n")
    est = sp_journal.estado(tmp_path, SLUG, sp)
    assert isinstance(est, sp_journal.Corrompido) and est.quarentena.exists()
    assert est.reconstruido.reconstruido is True and est.reconstruido.fase == "DA"


def test_ec_050_reconstruir_sem_sp_legivel_nem_git_nao_rebenta(tmp_path, monkeypatch):
    """EC-050: SP inexistente, SP sem frontmatter e git ausente dão Estado com fase/origem vazias, nunca exceção."""
    def sem_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(sp_journal.painel_backend, "run_hidden", sem_git)
    assert sp_journal.reconstruir(tmp_path, SLUG, tmp_path / "nao-existe.md").fase is None
    sem_fm = tmp_path / "sem.md"
    sem_fm.write_bytes(b"# sem frontmatter\n")
    est = sp_journal.reconstruir(tmp_path, SLUG, sem_fm)
    assert est.fase is None and est.origem == {"branch": None, "commit": None}
    fm_sem_phase = tmp_path / "fm.md"
    fm_sem_phase.write_bytes(b"---\nstatus: Doing\n---\n")
    assert sp_journal.reconstruir(tmp_path, SLUG, fm_sem_phase).fase is None


# --- CLI em processo ---

def test_cli_inicio_fim_revertido_e_estado(tmp_path, capsys):
    base = ["--slug", SLUG, "--raiz", str(tmp_path)]
    assert sp_journal.main(["inicio", *base, "--fase", "da", "--passo", "a", "--nao-idempotente"]) == 0
    assert sp_journal.main(["inicio", *base, "--fase", "da", "--passo", "b"]) == 0
    assert sp_journal.main(["fim", *base, "--fase", "da", "--passo", "b"]) == 0
    capsys.readouterr()
    assert sp_journal.main(["estado", *base]) == 0
    est = json.loads(capsys.readouterr().out)
    assert est["interrompidos"] == ["a"] and est["acao"] == "reverter"
    assert sp_journal.main(["revertido", *base, "--fase", "da", "--passo", "a"]) == 0
    capsys.readouterr()
    sp_journal.main(["estado", *base])
    assert json.loads(capsys.readouterr().out)["acao"] == "nada"


def test_cli_sem_fase_ou_passo_e_erro_de_uso(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        sp_journal.main(["inicio", "--slug", SLUG, "--raiz", str(tmp_path), "--fase", "da"])
    assert e.value.code == 2 and "--passo" in capsys.readouterr().err
    assert not sp_journal.caminhos(tmp_path, SLUG)[1].exists()


def test_ec_050_cli_estado_corrompido_avisa_e_devolve_json(tmp_path, capsys):
    cp = sp_journal.caminhos(tmp_path, SLUG)[0]
    cp.parent.mkdir(parents=True)
    cp.write_bytes(b"\x00\xff nao e json")
    assert sp_journal.main(["estado", "--slug", SLUG, "--raiz", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "quarentena" in out.err
    dados = json.loads(out.out)
    assert dados["corrompido"] is True and Path(dados["quarentena"]).exists()


def test_cli_reconstruir(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sp_journal, "_git", lambda *a: None)
    sp = tmp_path / "sp.md"
    sp.write_bytes("---\nphase: DP\n---\n# título ção\n".encode())
    assert sp_journal.main(["reconstruir", "--slug", SLUG, "--raiz", str(tmp_path), "--sp", str(sp)]) == 0
    dados = json.loads(capsys.readouterr().out)
    assert dados["reconstruido"] is True and dados["fase"] == "DP"


# --- sp_disco: recuperação de lock, unlink preso, heartbeat ---

def _pid_morto():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_ec_041_recuperacao_que_morreu_a_meio_e_limpa_por_idade(tmp_path):
    """EC-041: `.rec` de uma recuperação morta a meio bloqueia só até LOCK_VELHO_S; depois é limpa e o lock recupera."""
    lock = tmp_path / "x.lock"
    lock.write_bytes(str(_pid_morto()).encode())
    guarda = Path(f"{lock}.rec")
    guarda.write_bytes(b"")
    assert sp_disco._recuperar(lock) is False and guarda.exists()  # recente: outra recuperação pode estar a correr
    velho = time.time() - sp_disco.LOCK_VELHO_S - 5
    os.utime(guarda, (velho, velho))
    assert sp_disco._recuperar(lock) is False and not guarda.exists()
    assert sp_disco._recuperar(lock) is True and not lock.exists()


def test_ec_041_guarda_impossivel_de_apagar_nao_impede_a_recuperacao(tmp_path, monkeypatch):
    lock = tmp_path / "x.lock"
    lock.write_bytes(str(_pid_morto()).encode())
    real = pathlib.Path.unlink

    def unlink(self, missing_ok=False):
        if self.name.endswith(".rec"):
            raise PermissionError("antivírus")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    assert sp_disco._recuperar(lock) is True
    assert not lock.exists() and Path(f"{lock}.rec").exists()  # fica para a recuperação por idade


def test_ec_051_unlink_do_lock_preso_e_tentado_de_novo(tmp_path, monkeypatch):
    """EC-051: antivírus segura o `.lock` na largada: tenta de novo até conseguir (sem largar o lock por apagar)."""
    real = pathlib.Path.unlink
    falhas = {"n": 3}

    def unlink(self, missing_ok=False):
        if self.name.endswith(".lock") and falhas["n"]:
            falhas["n"] -= 1
            raise PermissionError("antivírus")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    monkeypatch.setattr(sp_disco.time, "sleep", lambda s: None)
    with sp_disco.bloqueio(tmp_path / "f"):
        pass
    assert falhas["n"] == 0 and not (tmp_path / "f.lock").exists()


def test_ec_051_unlink_do_lock_sempre_preso_acaba_por_levantar(tmp_path, monkeypatch):
    real = pathlib.Path.unlink

    def unlink(self, missing_ok=False):
        if self.name.endswith(".lock"):
            raise PermissionError("antivírus")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)
    monkeypatch.setattr(sp_disco.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError), sp_disco.bloqueio(tmp_path / "f"):
        pass


def test_ec_043_heartbeat_em_thread_renova_e_sobrevive_a_erros_de_disco(tmp_path, monkeypatch):
    """EC-043: o heartbeat em thread renova o lock; um OSError numa renovação não mata a thread."""
    lk = sp_disco.tomar_lock(tmp_path, SLUG, painel="p1")
    hb0 = sp_disco.dono(tmp_path, SLUG)["hb"]
    real = lk.heartbeat
    chamadas = {"n": 0}

    def hb(forcar=False):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise OSError("disco ocupado")
        return real(forcar)

    monkeypatch.setattr(lk, "heartbeat", hb)
    lk.iniciar_heartbeat(intervalo=0.01)
    limite = time.monotonic() + 5
    while sp_disco.dono(tmp_path, SLUG)["hb"] == hb0 and time.monotonic() < limite:
        time.sleep(0.01)
    lk.parar()
    assert chamadas["n"] >= 2 and sp_disco.dono(tmp_path, SLUG)["hb"] > hb0
    assert not lk._thread.is_alive()
    assert sp_disco.libertar_lock(tmp_path, SLUG) is True


def test_ec_043_lock_sp_com_heartbeat_liberta_a_saida(tmp_path):
    with sp_disco.lock_sp(tmp_path, SLUG, painel="p1", heartbeat=True) as lk:
        assert lk._thread.is_alive()
        assert sp_disco.dono(tmp_path, SLUG)["estado"] == "vivo"
    assert not lk._thread.is_alive()
    assert sp_disco.dono(tmp_path, SLUG) == {"estado": "livre"}


def test_ec_043_libertar_lock_que_desaparece_entretanto_devolve_false(tmp_path, monkeypatch):
    """EC-043: outro processo larga o lock entre o `exists()` e a leitura: False, sem exceção."""
    sp_disco.tomar_lock(tmp_path, SLUG, painel="p1")
    p = sp_disco.caminho_lock_sp(tmp_path, SLUG)

    def some(path, defeito=None):
        Path(path).unlink()
        return defeito

    monkeypatch.setattr(sp_disco, "ler_json", some)
    assert sp_disco.libertar_lock(tmp_path, SLUG) is False and not p.exists()


def test_ec_043_renovar_lock_de_outro_processo_vivo_nao_mexe(tmp_path):
    """EC-043: o lock vivo de outro pid (outro painel) não é renovado por este processo."""
    sp_disco.escrever_lock_sp(tmp_path, SLUG, {"pid": os.getppid(), "painel": "outro", "ts": 1.0, "hb": time.time()})
    antes = sp_disco.caminho_lock_sp(tmp_path, SLUG).read_bytes()
    assert sp_disco.renovar_lock(tmp_path, SLUG) is False
    assert sp_disco.caminho_lock_sp(tmp_path, SLUG).read_bytes() == antes
