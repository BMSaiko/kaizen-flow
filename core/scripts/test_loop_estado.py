"""Testes de scripts/loop_estado.py (estado persistente dos loops de manutenção)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop_estado as le  # noqa: E402


def test_set_get_roundtrip(tmp_path):
    fim = int(time.time()) + 3600
    le.set_estado("ronda", fim, base=tmp_path, perm="SB: commit,merge", acao="limpar")
    d = le.get_estado("ronda", tmp_path)
    assert d["fim"] == fim and d["perm"] == "SB: commit,merge" and d["acao"] == "limpar"


def test_expirado_ou_corrompido_conta_como_inativo(tmp_path):
    le.set_estado("ronda", int(time.time()) - 5, base=tmp_path)
    (tmp_path / "manutencao.json").write_text("{lixo", encoding="utf-8")
    assert le.get_estado("ronda", tmp_path) is None
    assert le.get_estado("manutencao", tmp_path) is None
    assert le.ativos(tmp_path) == []


def test_nome_invalido_recusado(tmp_path):
    with pytest.raises(ValueError):
        le.set_estado("../x", 1, base=tmp_path)


def test_parse_fim_formas():
    now = 1_800_000_000
    assert le.parse_fim("1h", now) == now + 3600
    assert le.parse_fim("30m", now) == now + 1800
    assert le.parse_fim("1800000123", now) == 1_800_000_123
    assert le.parse_fim("10:30", now) > now
    with pytest.raises(ValueError):
        le.parse_fim("amanhã", now)


def test_clear_e_ativos(tmp_path):
    fim = int(time.time()) + 600
    le.set_estado("ronda", fim, base=tmp_path)
    le.set_estado("manutencao", fim, base=tmp_path)
    assert [d["skill"] for d in le.ativos(tmp_path)] == ["manutencao", "ronda"]
    le.clear("ronda", tmp_path)
    le.clear("ronda", tmp_path)  # idempotente
    assert [d["skill"] for d in le.ativos(tmp_path)] == ["manutencao"]


def test_bloco_e_ordem_vazios_sem_loops(tmp_path):
    assert le.bloco_handoff(tmp_path) == "" and le.ordem_retoma(tmp_path) == ""


def test_bloco_e_ordem_com_loop(tmp_path):
    le.set_estado("ronda", int(time.time()) + 600, base=tmp_path, perm="SB: commit", alvos="SB,kaizen-flow")
    bloco = le.bloco_handoff(tmp_path)
    assert bloco.startswith("## Loops ativos") and "/ronda" in bloco and "SB: commit" in bloco
    assert "sem novo grill" in le.ordem_retoma(tmp_path)


def test_cli_set_get_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SB_LOOPS_DIR", str(tmp_path))
    assert le.main(["set", "ronda", "--fim", "1h", "--perm", "SB: commit"]) == 0
    assert le.main(["get", "ronda"]) == 0
    assert le.main(["clear", "ronda"]) == 0
    assert le.main(["get", "ronda"]) == 1
