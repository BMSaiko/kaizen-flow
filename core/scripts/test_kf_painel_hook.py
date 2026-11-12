"""Testes de scripts/kf_painel_hook.py: hooks Stop/Notification/UserPromptSubmit que atualizam o estado do painel."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

import kf_painel_hook as ph
import sp_painel_estado as pe

SCRIPTS = Path(__file__).resolve().parent
T0 = datetime(2026, 11, 12, 10, 0, 0)
SLUG = "kaizenflow-term-estado-2026-11-12"
BRANCH = "agent/kaizenflow-term-estado-2026-11"  # ramo truncado, como o sb-worktree faz


@pytest.fixture
def fila(tmp_path):
    fid = pe.criar_fila(programa="prog", ordem=[SLUG, "outro-sp-2026-11-12"], root=tmp_path, agora=T0)
    pe.transitar(SLUG, "a-correr", fila=fid, root=tmp_path, agora=T0)
    return fid, tmp_path


def _estado(fid, root, slug=SLUG):
    return pe.ler(fid, slug, root=root)


# --- esquema ---

def test_sp_novo_tem_fase_e_pergunta_nulos(tmp_path):
    fid = pe.criar_fila(programa="p", ordem=["a"], root=tmp_path, agora=T0)
    sp = pe.ler(fid, "a", root=tmp_path)
    assert sp["fase"] is None and sp["pergunta"] is None


def test_esquema_so_tem_metadados(fila):
    fid, root = fila
    ph.aplicar({"hook_event_name": "Notification", "message": "texto secreto da conversa", "prompt": "x"},
               slug=SLUG, root=root, agora=T0)
    bruto = (root / fid / f"{SLUG}.json").read_text(encoding="utf-8")
    assert "texto secreto" not in bruto and "prompt" not in json.loads(bruto)
    assert set(json.loads(bruto)) == {"slug", "fila", "estado", "modelo", "worktree", "pane", "inicio", "fim", "msg",
                                      "atualizado", "fase", "pergunta"}


# --- eventos ---

def test_notification_marca_pergunta(fila):
    fid, root = fila
    assert ph.aplicar({"hook_event_name": "Notification"}, slug=SLUG, root=root, agora=T0)
    sp = _estado(fid, root)
    assert (sp["estado"], sp["pergunta"]) == ("pergunta", "notification")


def test_stop_marca_pergunta_se_o_sp_nao_esta_feito(fila):
    fid, root = fila
    ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=root, agora=T0)
    sp = _estado(fid, root)
    assert (sp["estado"], sp["pergunta"]) == ("pergunta", "stop")


def test_stop_marca_done_se_o_sp_esta_em_done(fila):
    fid, root = fila
    ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=root, agora=T0, sp_feito=True)
    sp = _estado(fid, root)
    assert (sp["estado"], sp["pergunta"]) == ("done", None) and sp["fim"]


def test_prompt_volta_a_a_correr_e_limpa_a_pergunta(fila):
    fid, root = fila
    ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=root, agora=T0)
    ph.aplicar({"hook_event_name": "UserPromptSubmit"}, slug=SLUG, root=root, agora=T0)
    sp = _estado(fid, root)
    assert (sp["estado"], sp["pergunta"]) == ("a-correr", None)


def test_evento_desconhecido_nao_escreve(fila):
    fid, root = fila
    antes = (root / fid / f"{SLUG}.json").read_bytes()
    assert not ph.aplicar({"hook_event_name": "PreToolUse"}, slug=SLUG, root=root, agora=T0)
    assert (root / fid / f"{SLUG}.json").read_bytes() == antes


# --- tolerância ---

def test_slug_sem_fila_ou_transicao_invalida_nao_rebenta(fila):
    fid, root = fila
    assert not ph.aplicar({"hook_event_name": "Stop"}, slug="nao-existe", root=root, agora=T0)
    pe.transitar(SLUG, "bloqueado", fila=fid, root=root, agora=T0)
    assert not ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=root, agora=T0)  # bloqueado → pergunta: inválida
    assert _estado(fid, root)["estado"] == "bloqueado"


def test_raiz_inexistente_ou_json_corrompido_nao_rebenta(tmp_path):
    assert not ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=tmp_path / "nada", agora=T0)
    fid = pe.criar_fila(programa="p", ordem=[SLUG], root=tmp_path, agora=T0)
    (tmp_path / fid / f"{SLUG}.json").write_text("{lixo", encoding="utf-8")
    assert not ph.aplicar({"hook_event_name": "Stop"}, slug=SLUG, root=tmp_path, agora=T0)


def test_leitura_de_ficheiro_antigo_sem_fase_nem_pergunta(fila):
    fid, root = fila
    p = root / fid / f"{SLUG}.json"
    dados = json.loads(p.read_text(encoding="utf-8"))
    dados.pop("fase"), dados.pop("pergunta")
    p.write_text(json.dumps(dados), encoding="utf-8")
    assert ph.aplicar({"hook_event_name": "Notification"}, slug=SLUG, root=root, agora=T0)
    assert _estado(fid, root)["pergunta"] == "notification"


# --- slug ---

def test_resolver_slug_por_prefixo_do_ramo(fila):
    fid, root = fila
    assert ph.resolver_slug(env={}, ramo=BRANCH, root=root) == SLUG


def test_resolver_slug_prefere_a_variavel_de_ambiente(fila):
    _, root = fila
    assert ph.resolver_slug(env={"KAIZEN_SLUG": "outro-sp-2026-11-12"}, ramo=BRANCH, root=root) == "outro-sp-2026-11-12"


def test_resolver_slug_sem_correspondencia_devolve_none(fila):
    _, root = fila
    assert ph.resolver_slug(env={}, ramo="master", root=root) is None
    assert ph.resolver_slug(env={}, ramo=None, root=root) is None


# --- CLI ---

def test_cli_le_o_stdin_e_nunca_falha(fila):
    fid, root = fila
    env = {"PATH": "", "SP_FILA_ROOT": str(root), "KAIZEN_SLUG": SLUG, "SYSTEMROOT": "C:\\Windows"}
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "kf_painel_hook.py")], input=json.dumps({"hook_event_name": "Notification"}),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert _estado(fid, root)["estado"] == "pergunta"
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "kf_painel_hook.py")], input="não é json", capture_output=True, text=True, env=env)
    assert r.returncode == 0
