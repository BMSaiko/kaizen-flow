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
    le.set_estado("ronda", int(time.time()) + 600, base=tmp_path, perm="SB: commit", alvos="SB,kaizen-flow",
                   sessao="dono", pid=999_999_991)
    bloco = le.bloco_handoff(tmp_path, session_id="dono")
    assert bloco.startswith("## Loops ativos") and "/ronda" in bloco and "SB: commit" in bloco
    assert le.bloco_handoff(tmp_path, session_id="alheia") == ""
    assert "sem novo grill" in le.ordem_retoma(tmp_path, session_id="dono")


def test_cli_set_get_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SB_LOOPS_DIR", str(tmp_path))
    assert le.main(["set", "ronda", "--fim", "1h", "--perm", "SB: commit"]) == 0
    assert le.main(["get", "ronda"]) == 0
    assert le.main(["clear", "ronda"]) == 0
    assert le.main(["get", "ronda"]) == 1


def test_parse_fim_ate_as():
    now = 1_800_000_000
    assert le.parse_fim("até às 10:30", now) == le.parse_fim("10:30", now)
    assert le.parse_fim("ate as 10h30", now) == le.parse_fim("10:30", now)
    assert le.parse_fim("90m", now) == now + 5400
    assert le.parse_fim("até às 10", now) == le.parse_fim("10:00", now)


def test_log_por_volta(tmp_path):
    le.set_estado("ronda", int(time.time()) + 600, base=tmp_path)
    le.log("ronda", "volta 1: simplificar scripts/x.py", base=tmp_path)
    le.log("ronda", "volta 2: limpar", base=tmp_path)
    linhas = le.ler_log("ronda", base=tmp_path)
    assert len(linhas) == 2 and "volta 2" in linhas[1]
    le.clear("ronda", tmp_path)
    assert le.ler_log("ronda", base=tmp_path) == linhas  # o log sobrevive ao clear (relatório final)


def test_teto_de_tentativas(tmp_path):
    for i in range(1, 6):
        assert le.tentativa("ronda", "erro-x", base=tmp_path) == i
    assert le.tentativa("ronda", "erro-x", base=tmp_path) == 6
    assert le.tentativas_esgotadas("ronda", "erro-x", base=tmp_path)
    assert not le.tentativas_esgotadas("ronda", "erro-y", base=tmp_path)


def test_bloqueio_por_repo(tmp_path):
    le.set_estado("ronda", int(time.time()) + 600, base=tmp_path)
    assert le.lock("ronda", "SB", base=tmp_path) is True
    assert le.lock("manutencao", "SB", base=tmp_path) is False  # outro loop no mesmo repo
    assert le.lock("ronda", "SB", base=tmp_path) is True  # o dono repete
    assert le.lock("manutencao", "kaizen-flow", base=tmp_path) is True
    le.unlock("ronda", "SB", base=tmp_path)
    assert le.lock("manutencao", "SB", base=tmp_path) is True


def test_cli_novos(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_LOOPS_DIR", str(tmp_path))
    assert le.main(["set", "ronda", "--fim", "1h"]) == 0
    assert le.main(["log", "ronda", "volta 1"]) == 0
    assert le.main(["tentativa", "ronda", "k"]) == 0
    assert le.main(["lock", "ronda", "SB"]) == 0
    assert le.main(["lock", "manutencao", "SB"]) == 1
    assert le.main(["unlock", "ronda", "SB"]) == 0


def _fut():
    return int(time.time()) + 3600


def test_ativos_filtra_pela_sessao_dona(tmp_path):
    le.set_estado("manutencao", _fut(), base=tmp_path, sessao="dono", pid=999_999_991)
    assert [d["skill"] for d in le.ativos(tmp_path, session_id="dono")] == ["manutencao"]
    assert le.ativos(tmp_path, session_id="alheia") == []
    assert len(le.ativos(tmp_path)) == 1  # sem filtro: todos (lock, handoff)


def test_dono_pelo_pid_ancestral_sobrevive_ao_clear(tmp_path):
    import os
    le.set_estado("ronda", _fut(), base=tmp_path, sessao="antiga", pid=os.getppid())
    assert le.ativos(tmp_path, session_id="nova-apos-clear")


def test_estado_antigo_sem_dono_nao_afeta_ninguem(tmp_path):
    le.set_estado("ronda", _fut(), base=tmp_path)
    assert le.ativos(tmp_path, session_id="qualquer") == []


def test_cli_set_grava_dono_do_env_e_adotar_transfere(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_LOOPS_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    monkeypatch.setenv("CLAUDE_PID", "999999992")
    assert le.main(["set", "ronda", "--fim", "1h"]) == 0
    d = le.get_estado("ronda")
    assert d["sessao"] == "s1" and d["pid"] == 999_999_992
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s2")
    monkeypatch.setenv("CLAUDE_PID", "999999993")
    assert le.main(["adotar", "ronda"]) == 0
    d = le.get_estado("ronda")
    assert d["sessao"] == "s2" and d["pid"] == 999_999_993
    assert le.main(["set", "ronda", "--fim", "1h", "--acao", "limpar"]) == 0  # set seguinte mantém o dono
    assert le.get_estado("ronda")["sessao"] == "s2"


def test_ordem_retoma_so_para_o_dono(tmp_path):
    le.set_estado("manutencao", _fut(), base=tmp_path, sessao="dono", pid=999_999_991)
    assert le.ordem_retoma(tmp_path, session_id="alheia") == ""
    assert "/manutencao" in le.ordem_retoma(tmp_path, session_id="dono")
