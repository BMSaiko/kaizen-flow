"""Testes de sp_journal: checkpoint atómico + journal de passos por SP.

Cada teste indica o EC do catálogo (kaizen-flow docs/catalogo.json) que cobre.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sp_disco
import sp_journal

SCRIPTS = Path(__file__).resolve().parent
SLUG = "sp-teste"


def _estado_path(raiz):
    return sp_journal.caminhos(raiz, SLUG)[0]


def _journal_path(raiz):
    return sp_journal.caminhos(raiz, SLUG)[1]


def test_ec_001_inicio_sem_fim_e_interrompido(tmp_path):
    """EC-001: Ctrl+C a meio de uma fase: o passo sem «fim» é detetado."""
    sp_journal.inicio(tmp_path, SLUG, "da", "passo-1", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "da", "passo-1")
    sp_journal.inicio(tmp_path, SLUG, "da", "passo-2", idempotente=True)
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == ["passo-2"]
    assert est.fase == "da" and est.passo == "passo-2"
    assert est.acao == "repetir"


def test_ec_001_sem_interrupcao_acao_nada(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "dp", "plano", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "dp", "plano")
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == [] and est.acao == "nada"


def test_ec_001_estado_sem_ficheiros(tmp_path):
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == [] and est.acao == "nada" and est.fase is None


def test_ec_001_passo_nao_idempotente_reverte(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "merge", idempotente=False)
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == ["merge"] and est.acao == "reverter"


def test_ec_001_revertido_fecha_o_passo(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "merge", idempotente=False)
    sp_journal.revertido(tmp_path, SLUG, "da", "merge")
    est = sp_journal.estado(tmp_path, SLUG)
    assert est.interrompidos == [] and est.acao == "nada"


def test_ec_001_passo_repetido_fecha_com_o_ultimo_fim(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "p", idempotente=True)
    sp_journal.inicio(tmp_path, SLUG, "da", "p", idempotente=True)  # retoma repete
    sp_journal.fim(tmp_path, SLUG, "da", "p")
    assert sp_journal.estado(tmp_path, SLUG).interrompidos == []


def test_ec_019_fase_gravada_antes_do_handoff(tmp_path):
    """EC-019: a fase fica no checkpoint para a sessão nova retomar dela."""
    sp_journal.gravar_checkpoint(tmp_path, SLUG, "dp", "plano", extra={"nota": "contexto cheio"})
    dados = json.loads(_estado_path(tmp_path).read_text(encoding="utf-8"))
    assert dados["fase"] == "dp" and dados["passo"] == "plano" and dados["nota"] == "contexto cheio"
    assert dados["interrompido"] is False


def test_ec_004_gravacao_atomica_leitor_nunca_ve_json_parcial(tmp_path):
    """EC-004: escrever o estado durante leituras concorrentes nunca expõe JSON truncado."""
    alvo = _estado_path(tmp_path)
    sp_journal.gravar_checkpoint(tmp_path, SLUG, "da", "0", extra={"lixo": "x" * 20000})
    parar = threading.Event()
    maus = []

    def leitor():
        while not parar.is_set():
            try:
                texto = alvo.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                json.loads(texto)
            except ValueError:
                maus.append(texto[:40])

    t = threading.Thread(target=leitor)
    t.start()
    try:
        for i in range(60):
            sp_journal.gravar_checkpoint(tmp_path, SLUG, "da", str(i), extra={"lixo": "x" * 20000})
    finally:
        parar.set()
        t.join()
    assert maus == []


def test_ec_004_permission_error_transitorio_recuperado(tmp_path, monkeypatch):
    """EC-004: antivírus/leitor com o destino aberto (PermissionError no rename) recupera."""
    real = os.replace
    falhas = {"n": 0}

    def replace(a, b):
        if falhas["n"] < 5:
            falhas["n"] += 1
            raise PermissionError("destino aberto")
        return real(a, b)

    monkeypatch.setattr(os, "replace", replace)
    sp_journal.gravar_checkpoint(tmp_path, SLUG, "da", "p")
    assert falhas["n"] == 5
    assert json.loads(_estado_path(tmp_path).read_text(encoding="utf-8"))["passo"] == "p"


def test_ec_004_permission_error_permanente_levanta_em_2s(tmp_path, monkeypatch):
    def replace(a, b):
        raise PermissionError("bloqueado")

    monkeypatch.setattr(os, "replace", replace)
    t0 = time.monotonic()
    with pytest.raises(PermissionError):
        sp_journal.gravar_checkpoint(tmp_path, SLUG, "da", "p")
    assert time.monotonic() - t0 < 4.0


def test_guardar_retry_s_limita_o_tempo(tmp_path, monkeypatch):
    def replace(a, b):
        raise PermissionError("bloqueado")

    monkeypatch.setattr(os, "replace", replace)
    t0 = time.monotonic()
    with pytest.raises(PermissionError):
        sp_disco.guardar(tmp_path / "x.json", {"a": 1}, retry_s=0.2)
    assert time.monotonic() - t0 < 2.0


def test_guardar_sem_retry_s_mantem_o_defeito(tmp_path, monkeypatch):
    real = os.replace
    falhas = {"n": 0}

    def replace(a, b):
        if falhas["n"] < 3:
            falhas["n"] += 1
            raise PermissionError("x")
        return real(a, b)

    monkeypatch.setattr(os, "replace", replace)
    sp_disco.guardar(tmp_path / "x.json", {"a": 1})
    assert sp_disco.ler_json(tmp_path / "x.json") == {"a": 1}


def test_ec_050_linha_final_truncada_e_tolerada(tmp_path):
    """EC-050: linha final cortada é ignorada com aviso; as válidas anteriores contam."""
    sp_journal.inicio(tmp_path, SLUG, "da", "a", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "da", "a")
    with open(_journal_path(tmp_path), "ab") as f:
        f.write(b'{"ts": "2026-01-01", "pid": 1, "fase": "da", "pas')
    est = sp_journal.estado(tmp_path, SLUG)
    assert isinstance(est, sp_journal.Estado)
    assert est.interrompidos == [] and est.aviso
    assert not list(_journal_path(tmp_path).parent.glob("*.corrupt-*"))


def test_ec_050_append_depois_de_cauda_truncada_nao_cola_linhas(tmp_path):
    """EC-050: depois de um crash a meio da linha, o próximo evento não corrompe o journal."""
    sp_journal.inicio(tmp_path, SLUG, "da", "a", idempotente=True)
    with open(_journal_path(tmp_path), "ab") as f:
        f.write(b'{"ts": "2026-01-01", "pid": 1, "fase": "da", "pas')
    sp_journal.fim(tmp_path, SLUG, "da", "a")
    est = sp_journal.estado(tmp_path, SLUG)
    assert isinstance(est, sp_journal.Estado) and est.interrompidos == []
    restos = list(_journal_path(tmp_path).parent.glob("*.journal.jsonl.corrupt-*"))
    assert len(restos) == 1 and restos[0].read_bytes().startswith(b'{"ts"')


def test_ec_050_linha_do_meio_invalida_vai_para_quarentena(tmp_path):
    """EC-050: journal corrompido: quarentena .corrupt-<ts> + reconstrução, nunca apaga."""
    sp_journal.inicio(tmp_path, SLUG, "da", "a", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "da", "a")
    original = _journal_path(tmp_path).read_bytes()
    corrupto = original.replace(b'"evento"', b'"evento', 1)
    _journal_path(tmp_path).write_bytes(corrupto + original)
    est = sp_journal.estado(tmp_path, SLUG)
    assert isinstance(est, sp_journal.Corrompido)
    assert est.quarentena.exists() and ".corrupt-" in est.quarentena.name
    assert est.quarentena.read_bytes() == corrupto + original
    assert isinstance(est.reconstruido, sp_journal.Estado)
    assert not _journal_path(tmp_path).exists()


def test_ec_050_checkpoint_corrompido_quarentena_e_reconstrucao_do_journal(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "a", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "da", "a")
    sp_journal.inicio(tmp_path, SLUG, "da", "b", idempotente=True)
    _estado_path(tmp_path).write_text("{nao é json", encoding="utf-8")
    est = sp_journal.estado(tmp_path, SLUG)
    assert isinstance(est, sp_journal.Corrompido)
    assert est.quarentena.read_text(encoding="utf-8") == "{nao é json"
    assert est.reconstruido.interrompidos == ["b"]


def test_ec_050_reconstruir_do_frontmatter_e_git(tmp_path):
    sp = tmp_path / "sp.md"
    sp.write_text("---\nstatus: Doing\nphase: dp\nslug: x\n---\n# SP\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "agent/x"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "feat: um"],
        cwd=tmp_path,
        check=True,
    )
    est = sp_journal.reconstruir(tmp_path, SLUG, sp)
    assert est.fase == "dp" and est.reconstruido is True
    assert est.origem["branch"] == "agent/x" and est.origem["commit"] == "feat: um"
    assert est.interrompidos == [] and est.acao == "nada"


def test_ec_050_reconstruir_sem_git_nem_sp_nao_levanta(tmp_path):
    est = sp_journal.reconstruir(tmp_path, SLUG, None)
    assert est.fase is None and est.reconstruido is True


def test_ec_050_quarentena_nunca_sobrescreve(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "a", idempotente=True)
    for i in range(2):
        _journal_path(tmp_path).write_bytes(b"lixo\n" + f"{i}\n".encode() + b'{"x":1}\n')
        assert isinstance(sp_journal.estado(tmp_path, SLUG), sp_journal.Corrompido)
    assert len(list(_journal_path(tmp_path).parent.glob("*.journal.jsonl.corrupt-*"))) == 2


def test_caminho_com_espacos_e_acentos(tmp_path):
    raiz = tmp_path / "pasta com espaços" / "açúcar ção"
    raiz.mkdir(parents=True)
    sp_journal.inicio(raiz, SLUG, "da", "p", idempotente=True)
    sp_journal.fim(raiz, SLUG, "da", "p")
    assert sp_journal.estado(raiz, SLUG).interrompidos == []


@pytest.mark.skipif(os.name != "nt", reason="caminhos > 260 só limitam no Windows")
def test_ec_055_journal_caminho_maior_que_260(tmp_path):
    raiz = tmp_path
    for _ in range(12):
        raiz = raiz / ("d" * 30)
    caminho_estado = sp_journal.caminhos(raiz, SLUG)[0]
    assert len(str(raiz / ".kaizen" / "estado" / f"{SLUG}.json")) > 260
    assert str(caminho_estado).startswith("\\\\?\\")
    sp_journal.inicio(raiz, SLUG, "da", "p", idempotente=True)
    assert sp_journal.estado(raiz, SLUG).interrompidos == ["p"]


def test_crlf_preservado_no_journal(tmp_path):
    """Bytes: o journal usa só \\n, nunca converte para \\r\\n."""
    sp_journal.inicio(tmp_path, SLUG, "da", "p", idempotente=True)
    dados = _journal_path(tmp_path).read_bytes()
    assert b"\r\n" not in dados and dados.endswith(b"\n")
    sp = tmp_path / "sp.md"
    sp.write_bytes(b"---\r\nphase: da\r\n---\r\n# x\r\n")
    est = sp_journal.reconstruir(tmp_path, SLUG, sp)
    assert est.fase == "da"
    assert sp.read_bytes() == b"---\r\nphase: da\r\n---\r\n# x\r\n"


def test_evento_tem_os_campos_do_contrato(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "p", idempotente=False)
    linha = json.loads(_journal_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
    assert set(linha) == {"ts", "pid", "fase", "passo", "evento", "idempotente"}
    assert linha["evento"] == "inicio" and linha["idempotente"] is False and linha["pid"] == os.getpid()


@given(
    eventos=st.lists(
        st.tuples(st.sampled_from(["inicio", "fim", "revertido"]), st.sampled_from(["a", "b", "c"]), st.booleans()),
        max_size=25,
    ),
    corte=st.floats(min_value=0.0, max_value=1.0),
)
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_ec_050_truncagem_arbitraria_nunca_deixa_estado_ilegivel(tmp_path_factory, eventos, corte):
    """EC-050: journal truncado num byte qualquer dá sempre Estado ou Corrompido com quarentena feita."""
    raiz = tmp_path_factory.mktemp("hyp")
    for ev, passo, idem in eventos:
        getattr(sp_journal, ev)(raiz, SLUG, "da", passo, *([idem] if ev == "inicio" else []))
    jp = _journal_path(raiz)
    if jp.exists():
        dados = jp.read_bytes()
        jp.write_bytes(dados[: int(len(dados) * corte)])
    est = sp_journal.estado(raiz, SLUG)
    if isinstance(est, sp_journal.Corrompido):
        assert est.quarentena.exists()
        assert isinstance(est.reconstruido, sp_journal.Estado)
    else:
        assert isinstance(est, sp_journal.Estado)
        assert isinstance(est.interrompidos, list) and est.acao in ("repetir", "reverter", "nada")


_SCRIPT_SINAL = """
import sys, time
sys.path.insert(0, {scripts!r})
import sp_journal
raiz, slug = sys.argv[1], sys.argv[2]
sp_journal.instalar_sinais(raiz, slug)
sp_journal.inicio(raiz, slug, "da", "longo", idempotente=True)
print("pronto", flush=True)
for _ in range(600):  # fatias curtas: no Windows o sleep longo só acorda com SIGINT
    time.sleep(0.05)
"""


def _correr_e_sinalizar(tmp_path, quando):
    script = tmp_path / "filho.py"
    script.write_text(_SCRIPT_SINAL.format(scripts=str(SCRIPTS)), encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    p = subprocess.Popen(
        [sys.executable, str(script), str(tmp_path), SLUG],
        stdout=subprocess.PIPE,
        text=True,
        creationflags=flags,
    )
    try:
        assert p.stdout.readline().strip() == "pronto"
        quando(p)
        p.wait(timeout=10)
    finally:
        if p.poll() is None:
            p.kill()
    return p


def test_ec_001_sinal_de_interrupcao_grava_checkpoint(tmp_path):
    """EC-001: SIGINT (CTRL_BREAK no Windows) deixa checkpoint com interrompido: true."""
    sinal = signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
    p = _correr_e_sinalizar(tmp_path, lambda proc: proc.send_signal(sinal))
    assert p.returncode != 0
    dados = json.loads(_estado_path(tmp_path).read_text(encoding="utf-8"))
    assert dados["interrompido"] is True and dados["fase"] == "da" and dados["passo"] == "longo"
    assert sp_journal.estado(tmp_path, SLUG).interrompidos == ["longo"]


@pytest.mark.skipif(os.name == "nt", reason="SIGTERM não é entregável a um filho no Windows")
def test_ec_057_sigterm_grava_checkpoint(tmp_path):
    p = _correr_e_sinalizar(tmp_path, lambda proc: proc.send_signal(signal.SIGTERM))
    assert p.returncode != 0
    assert json.loads(_estado_path(tmp_path).read_text(encoding="utf-8"))["interrompido"] is True


def test_ec_057_handler_de_fecho_de_consola_grava_checkpoint(tmp_path):
    """EC-057: CTRL_CLOSE_EVENT é tratado como Ctrl+C: o handler grava o checkpoint."""
    sp_journal.inicio(tmp_path, SLUG, "da", "longo", idempotente=True)
    sp_journal._ATUAL[sp_journal._chave(tmp_path, SLUG)] = ("da", "longo")
    assert sp_journal._ao_interromper(tmp_path, SLUG) is True
    assert json.loads(_estado_path(tmp_path).read_text(encoding="utf-8"))["interrompido"] is True


def test_ec_057_instalar_sinais_sem_thread_principal_nao_levanta(tmp_path):
    erros = []

    def alvo():
        try:
            sp_journal.instalar_sinais(tmp_path, SLUG)
        except Exception as e:  # noqa: BLE001
            erros.append(e)

    t = threading.Thread(target=alvo)
    t.start()
    t.join()
    assert erros == []


def test_performance_gravar_checkpoint_p95_abaixo_de_200ms(tmp_path):
    tempos = []
    for i in range(50):
        t0 = time.perf_counter()
        sp_journal.gravar_checkpoint(tmp_path, SLUG, "da", str(i))
        tempos.append(time.perf_counter() - t0)
    tempos.sort()
    assert tempos[int(len(tempos) * 0.95) - 1] < 0.2


def test_performance_ler_1000_linhas_abaixo_de_100ms(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "da", "semente", idempotente=True)
    sp_journal.fim(tmp_path, SLUG, "da", "semente")
    modelo = _journal_path(tmp_path).read_bytes().splitlines()
    _journal_path(tmp_path).write_bytes(b"\n".join(modelo * 500) + b"\n")
    assert len(_journal_path(tmp_path).read_bytes().splitlines()) == 1000
    melhor = 1.0
    for _ in range(3):  # melhor de 3: ruido de antivirus/CPU nao e custo do estado()
        t0 = time.perf_counter()
        est = sp_journal.estado(tmp_path, SLUG)
        melhor = min(melhor, time.perf_counter() - t0)
    assert melhor < 0.1
    assert est.interrompidos == []


def test_cli_help_rc0():
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "sp_journal.py"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "estado" in r.stdout


def test_cli_inicio_fim_estado(tmp_path):
    def cli(*args):
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPTS / "sp_journal.py"), *args, "--slug", SLUG, "--raiz", str(tmp_path)],
            capture_output=True,
            text=True,
        )

    assert cli("inicio", "--fase", "da", "--passo", "p1").returncode == 0
    r = cli("estado")
    assert r.returncode == 0
    saida = json.loads(r.stdout)
    assert saida["interrompidos"] == ["p1"] and saida["acao"] == "repetir"
    assert cli("fim", "--fase", "da", "--passo", "p1").returncode == 0
    assert json.loads(cli("estado").stdout)["interrompidos"] == []


def test_cli_reconstruir(tmp_path):
    sp = tmp_path / "sp.md"
    sp.write_text("---\nphase: dr\n---\n", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / "sp_journal.py"), "reconstruir", "--slug", SLUG, "--raiz", str(tmp_path), "--sp", str(sp)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0 and json.loads(r.stdout)["fase"] == "dr"
