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
    assert rc == 1 and "EC-043" in texto and "painel-7" in texto and texto.startswith("EC-043 O quê: ") and "\n  Próximo: " in texto


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


def test_so_fins_retoma_na_fase_seguinte_ec001(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "dp", "inicio"), ("dp", "dp", "fim")])
    ponto = SR.ponto_de_retoma(tmp_path, SLUG)
    assert ponto["abertos"] == [] and ponto["fase"] == "da"


def test_commit_concluido_nao_retoma_ec001(tmp_path):
    _passos(tmp_path, SLUG, [("commit", "commit", "inicio"), ("commit", "commit", "fim")])
    assert SR.ponto_de_retoma(tmp_path, SLUG)["fase"] == "concluido"


def test_revertido_nao_ressuscita_lock_orfao_ec027(tmp_path):
    sp_disco.escrever_lock_sp(tmp_path, SLUG, {"pid": None, "painel": "p1", "ts": 1.0, "hb": time.time() - 99999})
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    sp_journal.revertido(tmp_path, SLUG, "da", "p1")
    assert sp_disco.dono(tmp_path, SLUG)["estado"] == "orfao"


def test_unlock_de_outro_painel_nao_liberta_ec043(tmp_path):
    assert SR.main(["--raiz", str(tmp_path), SLUG, "--lock", "--painel", "p1"]) == 0
    assert SR.main(["--raiz", str(tmp_path), SLUG, "--unlock", "--painel", "p2"]) == 0
    assert sp_disco.dono(tmp_path, SLUG)["estado"] == "vivo"


def test_ec043_mostra_idade_do_heartbeat_e_unlock(tmp_path):
    sp_disco.tomar_lock(tmp_path, SLUG, "painel-7", pid=None)
    rc, texto = SR.resume(tmp_path, SLUG)
    assert rc == 1 and "heartbeat há" in texto and "--unlock" in texto


def test_restart_de_slug_inexistente_rc1_sem_criar_pastas(tmp_path):
    rc, _ = SR.resume(tmp_path, "nao-existe", restart=True, confirmar=lambda: True)
    assert rc == 1 and not (tmp_path / ".kaizen" / "estado" / "arquivo").exists()


@pytest.mark.parametrize("mau", ["../x", "a/b", "a" + chr(92) + "b", ".."])
def test_slug_com_separadores_rc2(tmp_path, mau):
    assert SR.resume(tmp_path, mau)[0] == 2


def test_fecho_a_meio_com_lock_tomado_liberta_e_fica_candidato_ec057(tmp_path):
    codigo = (
        "import sys, os, time; sys.path.insert(0, sys.argv[1]); import sp_disco, sp_journal;"
        "r=sys.argv[2]; sp_journal.inicio(r, sys.argv[3], 'da', 'p1'); sp_disco.tomar_lock(r, sys.argv[3], 'pf');"
        "sp_journal.instalar_sinais(r, sys.argv[3]); print('pronto', flush=True); [time.sleep(0.05) for _ in range(1200)]"
    )
    sc = str(Path(__file__).resolve().parent)
    import signal

    win = os.name == "nt"  # Windows: CTRL_BREAK_EVENT corre o handler SIGBREAK (SIGTERM seria TerminateProcess, sem handler)
    filho = subprocess.Popen([sys.executable, "-c", codigo, sc, str(tmp_path), SLUG], stdout=subprocess.PIPE, text=True,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if win else 0)
    try:
        assert filho.stdout.readline().strip() == "pronto"
        assert sp_disco.dono(tmp_path, SLUG)["estado"] == "vivo"
        os.kill(filho.pid, signal.CTRL_BREAK_EVENT if win else signal.SIGTERM)
        filho.wait(10)
    finally:
        filho.kill()
    assert sp_disco.dono(tmp_path, SLUG)["estado"] == "livre"
    assert sp_journal.estado(tmp_path, SLUG).interrompido is True
    assert SR.candidatos(tmp_path) == [SLUG]


def test_from_em_slug_sem_estado_rc1_sem_tocar_no_journal(tmp_path):
    rc, _ = SR.resume(tmp_path, "nao-existe", from_fase="dp")
    assert rc == 1 and not (tmp_path / ".kaizen").exists()


@pytest.mark.parametrize("mau", ["../x", "a/b", ".."])
@pytest.mark.parametrize("flag", ["--lock", "--unlock"])
def test_lock_unlock_slug_invalido_rc2_sem_ficheiros(tmp_path, mau, flag):
    assert SR.main([mau, flag, "--raiz", str(tmp_path)]) == 2
    assert not list(tmp_path.rglob("*.lock.json"))


def test_renovar_lock_a_falhar_nao_parte_o_journal(tmp_path, monkeypatch):
    def rebenta(*a, **k):
        raise PermissionError("antivirus")
    monkeypatch.setattr(sp_disco, "renovar_lock", rebenta)
    sp_journal.inicio(tmp_path, SLUG, "da", "p1")
    sp_journal.fim(tmp_path, SLUG, "da", "p1")
    assert [e["evento"] for e in SR._eventos(tmp_path, SLUG)] == ["inicio", "fim"]


def test_restart_com_from_rc2(tmp_path):
    assert SR.resume(tmp_path, SLUG, from_fase="dp", restart=True, confirmar=lambda: True)[0] == 2


def test_from_avisa_de_passos_abertos_em_fases_anteriores(tmp_path):
    sp_journal.inicio(tmp_path, SLUG, "dp", "p1")
    rc, texto = SR.resume(tmp_path, SLUG, from_fase="da")
    assert rc == 0 and "dp/p1" in texto


# --- pausa por quota/rede (preflight-erros-ux, EC-016/017) e formato EC -------------------

from datetime import datetime as _dt  # noqa: E402

import sp_painel_estado as _pe  # noqa: E402


def _pausado(root, motivo="EC-016 quota/limite de uso do modelo: usage limit", retoma="2026-11-18T15:00:00"):
    _pe.criar_fila("f1", root=root, ordem=[SLUG])
    _pe.registar("f1", SLUG, root=root, pane="1")
    _pe.transitar(SLUG, "a-correr", fila="f1", root=root)
    _pe.transitar(SLUG, "bloqueado", msg="pausa", fila="f1", root=root, motivo=motivo, retoma_em=retoma)


def test_pausa_por_quota_recusa_antes_de_retoma_em_ec016(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio"), ("dp", "p1", "fim")])
    _pausado(tmp_path / "filas")
    rc, texto = SR.resume(tmp_path, SLUG, agora=_dt(2026, 11, 18, 14, 0), painel_root=tmp_path / "filas")
    assert rc == 1 and texto.startswith(f"EC-016 O quê: SP {SLUG} em pausa até 2026-11-18T15:00:00")
    assert "Estado guardado: checkpoint e journal intactos" in texto and f"kaizen resume {SLUG}" in texto
    rc, texto = SR.resume(tmp_path, SLUG, agora=_dt(2026, 11, 18, 15, 0, 1), painel_root=tmp_path / "filas")
    assert rc == 0 and "retomar" in texto


def test_pausa_de_rede_usa_ec017(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio")])
    _pausado(tmp_path / "filas", motivo="EC-017 rede indisponível: ECONNRESET")
    rc, texto = SR.resume(tmp_path, SLUG, agora=_dt(2026, 11, 18, 14, 0), painel_root=tmp_path / "filas")
    assert rc == 1 and texto.startswith("EC-017 ")


def test_sessao_expirada_sem_retoma_em_deixa_retomar(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio")])
    _pausado(tmp_path / "filas", motivo="EC-066 sessão/login do modelo expirado", retoma=None)
    rc, _ = SR.resume(tmp_path, SLUG, agora=_dt(2026, 11, 18, 14, 0), painel_root=tmp_path / "filas")
    assert rc == 0


def test_bloqueio_que_nao_e_pausa_nao_trava_o_resume(tmp_path):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio")])
    _pausado(tmp_path / "filas", motivo="gate vermelho", retoma="2099-01-01T00:00:00")
    rc, _ = SR.resume(tmp_path, SLUG, agora=_dt(2026, 11, 18, 14, 0), painel_root=tmp_path / "filas")
    assert rc == 0


@pytest.mark.parametrize("args,ec", [
    ({"slug": "a/b"}, "EC-067"), ({"slug": SLUG, "from_fase": "x"}, "EC-067"),
    ({"slug": SLUG, "restart": True, "from_fase": "dp"}, "EC-067"), ({"slug": SLUG}, "EC-050"),
    ({"slug": SLUG, "restart": True, "confirmar": lambda: False}, "EC-006"),
])
def test_recusas_no_formato_de_4_partes(tmp_path, args, ec):
    import kf_erros
    rc, texto = SR.resume(raiz=tmp_path, painel_root=tmp_path / "filas", **args)
    lido = kf_erros.ler(texto)
    assert rc in (1, 2) and lido is not None and lido.ec == ec


def test_main_corre_o_pre_voo_so_como_aviso(tmp_path, capsys, monkeypatch):
    _passos(tmp_path, SLUG, [("dp", "p1", "inicio")])
    chamado = {}

    class PF:
        @staticmethod
        def diagnosticar(slug, repo, ignorar_orfao):
            chamado.update(slug=slug, ignorar=ignorar_orfao)
            import kf_erros

            class P:
                def texto(self):
                    return kf_erros.erro("EC-060", "árvore suja", "x", "nada alterado", "y")
            return [P()]

    import sp_carregar
    monkeypatch.setattr(sp_carregar, "carregar", lambda *a, **k: PF)
    assert SR.main([SLUG, "--raiz", str(tmp_path)]) == 0
    err = capsys.readouterr().err
    assert chamado == {"slug": SLUG, "ignorar": True} and "aviso do pré-voo:\nEC-060 O quê: árvore suja" in err
