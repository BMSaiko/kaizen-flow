"""Testes de propriedades (Hypothesis) do checkpoint/journal, do estado corrompido e do lock de SP.

Determinísticos: o perfil `kaizen` do `conftest.py` fixa `derandomize=True` (mesma semente em cada corrida).
Cada propriedade nomeia o EC que garante; contraexemplo = bug (correção mínima no módulo dono + EC).
"""
import json
import os
import time

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sp_disco
import sp_journal

SLUG = "sp-prop"
_FIXTURE = [HealthCheck.function_scoped_fixture]
PASSOS = st.lists(st.sampled_from(["p1", "p2", "p3", "p4"]), min_size=1, max_size=8)


# --- sentinelas das fixtures de injeção (provam que a fixture faz o que diz) ---

def test_sentinela_falha_replace_falha_n_vezes_e_depois_passa(tmp_path, falha_replace):
    origem, destino = tmp_path / "a", tmp_path / "b"
    origem.write_bytes(b"x")
    injetor = falha_replace(2)
    for _ in range(2):
        with pytest.raises(PermissionError):
            os.replace(origem, destino)
    os.replace(origem, destino)
    assert (injetor.chamadas, injetor.falhas) == (3, 2) and destino.read_bytes() == b"x"


def test_sentinela_tempo_falso_avanca_sem_dormir(tempo_falso):
    rel = tempo_falso(sp_disco, inicio=100.0)
    assert sp_disco.time.time() == 100.0
    sp_disco.time.sleep(30)
    assert sp_disco.time.time() == 130.0 and sp_disco.time.monotonic() == 130.0 and rel.dormidos == [30]
    assert sp_disco.time.strftime("%Y")  # o resto do módulo `time` continua o real


def test_ec_051_guardar_sobrevive_a_replace_que_falha_n_vezes(tmp_path, falha_replace, tempo_falso):
    """EC-051: `os.replace` falha 3 vezes (antivírus) e depois passa; o checkpoint fica escrito e inteiro."""
    tempo_falso(sp_disco)
    injetor = falha_replace(3)
    p = tmp_path / "estado.json"
    sp_disco.guardar(p, {"fase": "da", "passo": "p"}, retry_s=2.0)
    assert injetor.falhas == 3 and json.loads(p.read_text(encoding="utf-8")) == {"fase": "da", "passo": "p"}
    assert not list(tmp_path.glob("*.tmp"))


def test_ec_051_guardar_desiste_ao_fim_do_retry_e_nao_corrompe(tmp_path, falha_replace, tempo_falso):
    tempo_falso(sp_disco)
    p = tmp_path / "estado.json"
    sp_disco.guardar(p, {"v": 1})
    falha_replace(10**6)
    with pytest.raises(PermissionError):
        sp_disco.guardar(p, {"v": 2}, retry_s=2.0)
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 1}  # o anterior fica legível


# --- (a) checkpoint/journal: interrupção num ponto arbitrário ---

@given(passos=PASSOS, corte=st.integers(min_value=0, max_value=16), meia_linha=st.binary(max_size=40))
@settings(max_examples=80, suppress_health_check=_FIXTURE)
def test_ec_001_interrupcao_arbitraria_retoma_sem_repetir_nem_perder(tmp_path_factory, passos, corte, meia_linha):
    """EC-001: corrida de passos parada no evento `corte` (e opcionalmente a meio de uma linha): o estado lê-se,
    os passos com `fim` nunca são repetidos, o passo aberto é o único a repetir, e a retoma fecha tudo."""
    raiz = tmp_path_factory.mktemp("a")
    eventos = [(ev, p) for p in passos for ev in ("inicio", "fim")]
    feitos = eventos[: min(corte, len(eventos))]
    for ev, p in feitos:
        getattr(sp_journal, ev)(raiz, SLUG, "da", p)
    jp = sp_journal.caminhos(raiz, SLUG)[1]
    if feitos and meia_linha:
        with open(jp, "ab") as f:  # crash a meio de escrever o evento seguinte
            f.write(meia_linha.replace(b"\n", b""))
    est = sp_journal.estado(raiz, SLUG)
    assert isinstance(est, sp_journal.Estado), est
    abertos = []
    for ev, p in feitos:
        if ev == "inicio":
            abertos = [x for x in abertos if x != p] + [p]
        else:
            abertos = [x for x in abertos if x != p]
    assert est.interrompidos == abertos
    assert est.acao == ("repetir" if abertos else "nada")
    for p in est.interrompidos:  # retoma: repete só os abertos
        sp_journal.inicio(raiz, SLUG, "da", p)
        sp_journal.fim(raiz, SLUG, "da", p)
    depois = sp_journal.estado(raiz, SLUG)
    assert isinstance(depois, sp_journal.Estado) and depois.interrompidos == [] and depois.acao == "nada"


@given(passos=PASSOS, nao_idem=st.sets(st.sampled_from(["p1", "p2", "p3", "p4"])))
@settings(max_examples=40, suppress_health_check=_FIXTURE)
def test_ec_001_passo_nao_idempotente_aberto_pede_reverter(tmp_path_factory, passos, nao_idem):
    raiz = tmp_path_factory.mktemp("r")
    for p in passos[:-1]:
        sp_journal.inicio(raiz, SLUG, "da", p, idempotente=p not in nao_idem)
        sp_journal.fim(raiz, SLUG, "da", p)
    ultimo = passos[-1]
    sp_journal.inicio(raiz, SLUG, "da", ultimo, idempotente=ultimo not in nao_idem)
    est = sp_journal.estado(raiz, SLUG)
    assert est.interrompidos == [ultimo]
    assert est.acao == ("reverter" if ultimo in nao_idem else "repetir")


# --- (b) estado corrompido: bytes arbitrários nunca lançam ---

@given(lixo=st.binary(max_size=300))
@settings(max_examples=80, suppress_health_check=_FIXTURE)
def test_ec_050_checkpoint_com_bytes_arbitrarios_vai_para_quarentena(tmp_path_factory, lixo):
    """EC-050: checkpoint com bytes quaisquer: `estado` nunca lança; se não for um objeto JSON vai para `.corrupt-*`
    (nunca apagado, bytes intactos) e o estado é reconstruído dos eventos."""
    raiz = tmp_path_factory.mktemp("b")
    sp_journal.inicio(raiz, SLUG, "da", "p1")
    cp = sp_journal.caminhos(raiz, SLUG)[0]
    cp.write_bytes(lixo)
    est = sp_journal.estado(raiz, SLUG)
    try:
        valido = isinstance(json.loads(lixo.decode("utf-8")), dict)
    except (ValueError, UnicodeDecodeError):
        valido = False
    if valido:
        assert isinstance(est, sp_journal.Estado) and est.interrompidos == ["p1"]
    else:
        assert isinstance(est, sp_journal.Corrompido)
        assert est.quarentena.read_bytes() == lixo and not cp.exists()
        assert est.reconstruido.interrompidos == ["p1"]


@given(lixo=st.binary(min_size=1, max_size=300), prefixo=st.integers(min_value=0, max_value=3))
@settings(max_examples=80, suppress_health_check=_FIXTURE)
def test_ec_050_journal_com_bytes_arbitrarios_nunca_lanca(tmp_path_factory, lixo, prefixo):
    raiz = tmp_path_factory.mktemp("j")
    for i in range(prefixo):
        sp_journal.inicio(raiz, SLUG, "da", f"p{i}")
    jp = sp_journal.caminhos(raiz, SLUG)[1]
    jp.parent.mkdir(parents=True, exist_ok=True)
    antes = jp.read_bytes() if jp.exists() else b""
    jp.write_bytes(antes + lixo)
    est = sp_journal.estado(raiz, SLUG)
    if isinstance(est, sp_journal.Corrompido):
        assert est.quarentena.read_bytes() == antes + lixo and not jp.exists()
    else:
        assert isinstance(est, sp_journal.Estado) and est.acao in ("repetir", "reverter", "nada")
    sp_journal.inicio(raiz, SLUG, "da", "depois")  # escrever a seguir nunca rebenta
    assert "depois" in sp_journal.estado(raiz, SLUG).interrompidos


@given(lixo=st.binary(max_size=200))
@settings(max_examples=60, suppress_health_check=_FIXTURE)
def test_ec_043_lock_com_bytes_arbitrarios_nunca_lanca_nem_se_perde(tmp_path_factory, lixo):
    """EC-043: lock de SP ilegível: `dono` nunca lança; tomar o lock põe o ilegível em `.corrupt-*` (nunca apagado)."""
    raiz = tmp_path_factory.mktemp("l")
    p = sp_disco.caminho_lock_sp(raiz, SLUG)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(lixo)
    d = sp_disco.dono(raiz, SLUG)
    assert d["estado"] in ("livre", "vivo", "orfao", "corrompido")
    if d["estado"] == "vivo":
        return
    lk = sp_disco.tomar_lock(raiz, SLUG, "painel", pid=None)
    assert sp_disco.dono(raiz, SLUG)["estado"] == "vivo" and lk.painel == "painel"
    if d["estado"] == "corrompido":
        assert [q.read_bytes() for q in p.parent.glob(f"{p.name}.corrupt-*")] == [lixo]


# --- (c) locks: pid vivo/morto × heartbeat recente/antigo ---

@given(
    pid=st.one_of(st.none(), st.integers(min_value=1, max_value=4_000_000)),
    vivo=st.booleans(),
    idade=st.floats(min_value=0, max_value=10_000, allow_nan=False),
)
@settings(max_examples=120, suppress_health_check=_FIXTURE)
def test_ec_041_dono_decide_por_pid_e_heartbeat_de_forma_deterministica(tmp_path_factory, monkeypatch, pid, vivo, idade):
    """EC-041: `vivo` só com pid vivo e heartbeat ≤ 90 s (sem pid: ≤ 1800 s); caso contrário `orfao`; igual em cada leitura."""
    raiz = tmp_path_factory.mktemp("c")
    monkeypatch.setattr(sp_disco, "pid_vivo", lambda p: vivo)
    agora = time.time()  # `tomar_lock`/`renovar_lock` leem a hora real
    sp_disco.escrever_lock_sp(raiz, SLUG, {"pid": pid, "painel": "x", "ts": agora - idade, "hb": agora - idade})
    if pid is None:
        esperado = "vivo" if idade <= sp_disco.HEARTBEAT_SEM_PID_S else "orfao"
    else:
        esperado = "vivo" if vivo and idade <= sp_disco.HEARTBEAT_VELHO_S else "orfao"
    leituras = {sp_disco.dono(raiz, SLUG, agora=agora)["estado"] for _ in range(3)}
    assert leituras == {esperado}
    if any(abs(idade - lim) < 5 for lim in (sp_disco.HEARTBEAT_VELHO_S, sp_disco.HEARTBEAT_SEM_PID_S)):
        return  # na fronteira, a hora real que `tomar_lock` lê já passou o limite: só a decisão com `agora` fixo conta
    if esperado == "vivo":
        with pytest.raises(sp_disco.LockOcupado):
            sp_disco.tomar_lock(raiz, SLUG, "outro", pid=None)
    else:
        assert sp_disco.renovar_lock(raiz, SLUG) is False  # órfão nunca ressuscita


@given(pid=st.one_of(st.integers(), st.booleans(), st.floats(allow_nan=True), st.text(max_size=5)),
       hb=st.one_of(st.integers(), st.floats(allow_nan=True, allow_infinity=True), st.none(), st.text(max_size=5)))
@settings(max_examples=120, suppress_health_check=_FIXTURE)
def test_ec_041_dono_com_pid_ou_heartbeat_absurdos_nunca_lanca(tmp_path_factory, pid, hb):
    """EC-041: pid/heartbeat fora do intervalo (negativo, enorme, bool, texto, NaN) dão um estado, nunca uma exceção."""
    raiz = tmp_path_factory.mktemp("x")
    p = sp_disco.caminho_lock_sp(raiz, SLUG)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps({"pid": pid, "painel": "x", "hb": hb}).encode("utf-8"))
    assert sp_disco.dono(raiz, SLUG)["estado"] in ("vivo", "orfao", "corrompido")
