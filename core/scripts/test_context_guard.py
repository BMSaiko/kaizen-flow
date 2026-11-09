"""Testes de scripts/context-guard.py: medição do contexto em transcripts do Claude e rollouts do Codex."""
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("context_guard", Path(__file__).with_name("context-guard.py"))
cg = importlib.util.module_from_spec(_spec)
sys.modules["context_guard"] = cg
_spec.loader.exec_module(cg)


def write(path, rows, raw_tail=""):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n" + raw_tail, encoding="utf-8")
    return path


def claude_row(inp, cache_read=0, cache_write=0, **extra):
    msg = {"usage": {"input_tokens": inp, "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": cache_write}}
    return {"type": "assistant", "message": msg, **extra}


def codex_row(input_tokens, cached=0, output=10, total=None):
    info = {
        "last_token_usage": {"input_tokens": input_tokens, "cached_input_tokens": cached, "output_tokens": output},
        "total_token_usage": total or {"input_tokens": input_tokens},
    }
    return {"type": "event_msg", "payload": {"type": "token_count", "info": info}}


# --- Claude (regressão) ---

def test_context_guard_claude_soma_input_e_caches(tmp_path):
    f = write(tmp_path / "c.jsonl", [claude_row(10, 20, 30)])
    assert cg.context_tokens(f) == 60


def test_context_guard_claude_ignora_sidechain(tmp_path):
    f = write(tmp_path / "c.jsonl", [claude_row(100), claude_row(999, isSidechain=True)])
    assert cg.context_tokens(f) == 100


# --- Codex: esqueleto ---

def test_context_guard_codex_le_input_tokens_do_ultimo_pedido(tmp_path):
    f = write(tmp_path / "r.jsonl", [codex_row(40_000), codex_row(52_000, cached=30_000)])
    assert cg.context_tokens(f) == 52_000  # input_tokens já inclui a parte em cache


def test_context_guard_codex_estado_limite(tmp_path):
    f = write(tmp_path / "r.jsonl", [codex_row(100_000)])
    assert cg.state(cg.context_tokens(f), 100_000) == "limite"


def test_context_guard_cli_transcript_codex(tmp_path, capsys):
    f = write(tmp_path / "r.jsonl", [codex_row(90_000)])
    assert cg.main(["--transcript", str(f), "--limit", "100000"]) == 0
    assert capsys.readouterr().out.strip() == "90000 aviso"


# --- Codex: casos de borda ---

def test_context_guard_codex_info_nulo_e_ignorado(tmp_path):
    null_info = {"type": "event_msg", "payload": {"type": "token_count", "info": None}}
    f = write(tmp_path / "r.jsonl", [codex_row(33_000), null_info])
    assert cg.context_tokens(f) == 33_000


def test_context_guard_codex_so_info_nulo_devolve_none(tmp_path):
    null_info = {"type": "event_msg", "payload": {"type": "token_count", "info": None}}
    assert cg.context_tokens(write(tmp_path / "r.jsonl", [null_info])) is None


def test_context_guard_codex_formato_desconhecido_devolve_none(tmp_path):
    odd = {"type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": "x"}}}
    assert cg.context_tokens(write(tmp_path / "r.jsonl", [odd])) is None


def test_context_guard_codex_ignora_linha_truncada_no_fim(tmp_path):
    f = write(tmp_path / "r.jsonl", [codex_row(71_000)], raw_tail='{"type": "event_msg", "payl')
    assert cg.context_tokens(f) == 71_000


def test_context_guard_ficheiro_vazio_e_inexistente(tmp_path):
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    assert cg.context_tokens(empty) is None
    assert cg.context_tokens(tmp_path / "nao-existe.jsonl") is None


def test_context_guard_cli_sem_usage_rc1(tmp_path, capsys):
    f = tmp_path / "e.jsonl"
    f.write_text("", encoding="utf-8")
    assert cg.main(["--transcript", str(f)]) == 1


def test_context_guard_transcript_misto_usa_a_ultima_linha_valida(tmp_path):
    f = write(tmp_path / "m.jsonl", [claude_row(5), codex_row(77_000)])
    assert cg.context_tokens(f) == 77_000


# --- Modo hook ---

def test_context_guard_hook_codex_pede_handoff_no_limite(tmp_path):
    f = write(tmp_path / "r.jsonl", [codex_row(120_000)])
    payload = {"session_id": "s1", "transcript_path": str(f), "hook_event_name": "UserPromptSubmit"}
    out = cg.hook(payload, env={}, marker_dir=tmp_path / "m")
    assert "120K" in out["hookSpecificOutput"]["additionalContext"]
    assert cg.hook(payload, env={}, marker_dir=tmp_path / "m") is None  # uma vez por sessão


def test_context_guard_hook_codex_aviso_a_85_por_cento(tmp_path):
    f = write(tmp_path / "r.jsonl", [codex_row(86_000)])
    payload = {"session_id": "s2", "transcript_path": str(f), "hook_event_name": "PostToolUse"}
    out = cg.hook(payload, env={}, marker_dir=tmp_path / "m")
    assert "systemMessage" in out


# --- Variável do limiar ---

def test_context_guard_limite_kaizen_tem_prioridade_e_claude_continua(tmp_path):
    assert cg.limit_from_env({"KAIZEN_CONTEXT_LIMIT": "50000"}) == 50_000
    assert cg.limit_from_env({"CLAUDE_CONTEXT_LIMIT": "70000"}) == 70_000  # alias retrocompatível
    assert cg.limit_from_env({"KAIZEN_CONTEXT_LIMIT": "50000", "CLAUDE_CONTEXT_LIMIT": "70000"}) == 50_000
    assert cg.limit_from_env({"KAIZEN_CONTEXT_LIMIT": "abc", "CLAUDE_CONTEXT_LIMIT": "70000"}) == 70_000
    assert cg.limit_from_env({}) == cg.DEFAULT_LIMIT


# --- Rollout mais recente do Codex (payload sem caminho) ---

def test_context_guard_latest_rollout_escolhe_o_mais_recente(tmp_path):
    import os

    day = tmp_path / "2026" / "11" / "09"
    day.mkdir(parents=True)
    old = write(day / "rollout-a.jsonl", [codex_row(1_000)])
    new = write(day / "rollout-b.jsonl", [codex_row(2_000)])
    os.utime(old, (1_000, 1_000))
    os.utime(new, (2_000, 2_000))
    assert cg.latest_rollout(tmp_path) == str(new)
    assert cg.latest_rollout(tmp_path / "inexistente") is None


def test_context_guard_hook_codex_sem_transcript_path_usa_o_rollout_recente(tmp_path):
    root = tmp_path / "sessions" / "2026" / "11" / "09"
    root.mkdir(parents=True)
    write(root / "rollout-x.jsonl", [codex_row(120_000)])
    payload = {"session_id": "s3", "hook_event_name": "PostToolUse"}
    out = cg.hook(payload, env={"KAIZEN_CODEX_ROOT": str(tmp_path / "sessions")}, marker_dir=tmp_path / "m")
    assert "120K" in out["hookSpecificOutput"]["additionalContext"]


def test_context_guard_hook_sem_transcript_e_sem_codex_root_nao_faz_nada(tmp_path):
    payload = {"session_id": "s4", "hook_event_name": "PostToolUse"}
    assert cg.hook(payload, env={}, marker_dir=tmp_path / "m") is None
