"""Testes de scripts/handoff.py (ficheiros temporários; nada fala com o WezTerm)."""
import importlib.util
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("handoff", Path(__file__).with_name("handoff.py"))
handoff = importlib.util.module_from_spec(_spec)
sys.modules["handoff"] = handoff
_spec.loader.exec_module(handoff)

BODY = "**Feito**\n- a\n\n**Por fazer**\n- b\n\n**Próximo passo**\nc\n"


def test_write_cria_ficheiro_com_nome_data_hora_slug(tmp_path):
    path = handoff.write(tmp_path / "handoffs", BODY, "Conversa Livre!", now=datetime(2026, 10, 18, 9, 5))
    assert path.name == "2026-10-18-0905-conversa-livre.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "type: handoff" in text and "**Próximo passo**" in text


def test_write_slug_vazio_usa_omissao(tmp_path):
    path = handoff.write(tmp_path / "handoffs", BODY, "", now=datetime(2026, 10, 18, 9, 5))
    assert path.name == "2026-10-18-0905-conversa.md"


def test_write_nao_apaga_o_ficheiro_acabado_de_escrever_nem_recentes(tmp_path):
    folder = tmp_path / "handoffs"
    first = handoff.write(folder, BODY, "a", now=datetime(2026, 10, 18, 9, 5))
    second = handoff.write(folder, BODY, "b", now=datetime(2026, 10, 18, 9, 6))
    assert first.exists() and second.exists()


def test_write_limpa_so_handoffs_md_com_mais_de_7_dias(tmp_path):
    folder = tmp_path / "handoffs"
    folder.mkdir()
    old, fresh, other = folder / "velho.md", folder / "novo.md", folder / "notas.txt"
    for f in (old, fresh, other):
        f.write_text("x", encoding="utf-8")
    ancient = time.time() - 8 * 86400
    os.utime(old, (ancient, ancient))
    os.utime(other, (ancient, ancient))
    handoff.write(folder, BODY, "z", now=datetime.now())
    assert not old.exists() and fresh.exists() and other.exists()


def test_consume_imprime_e_so_depois_apaga(tmp_path):
    path = handoff.write(tmp_path / "handoffs", BODY, "z", now=datetime(2026, 10, 18, 9, 5))
    seen = []
    handoff.consume(path, out=lambda text: seen.append((text, path.exists())))
    assert "**Próximo passo**" in seen[0][0] and seen[0][1] is True
    assert not path.exists()


def test_consume_falha_a_imprimir_nao_apaga(tmp_path):
    path = handoff.write(tmp_path / "handoffs", BODY, "z", now=datetime(2026, 10, 18, 9, 5))

    def boom(text):
        raise OSError("sem saída")

    with pytest.raises(OSError):
        handoff.consume(path, out=boom)
    assert path.exists()


def test_consume_recusa_o_que_nao_e_handoff(tmp_path):
    outside = tmp_path / "outros" / "x.md"
    outside.parent.mkdir()
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(handoff.HandoffError):
        handoff.consume(outside, out=lambda text: None)
    assert outside.exists()
    txt = tmp_path / "handoffs" / "x.txt"
    txt.parent.mkdir()
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(handoff.HandoffError):
        handoff.consume(txt, out=lambda text: None)


def test_consume_inexistente_da_erro_limpo(tmp_path):
    with pytest.raises(handoff.HandoffError, match="não existe"):
        handoff.consume(tmp_path / "handoffs" / "nao.md", out=lambda text: None)


def test_prompt_manda_ler_com_consume_e_e_uma_linha(tmp_path):
    path = tmp_path / "handoffs" / "x.md"
    text = handoff.continuation_prompt(path)
    assert "--consume" in text and str(path) in text and "\n" not in text and "\r" not in text


def test_dry_run_mostra_clear_e_prompt_no_painel(tmp_path, capsys):
    path = handoff.write(tmp_path / "handoffs", BODY, "z", now=datetime(2026, 10, 18, 9, 5))
    assert handoff.main(["--launch", str(path), "--auto", "--dry-run", "--pane", "7"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 4
    assert "/clear" in out[0] and "--pane-id 7" in out[0]
    assert "--consume" in out[2] and str(path) in out[2]
    assert path.exists()


def test_auto_recusa_ficheiro_inexistente_ou_fora_de_handoffs(tmp_path, capsys):
    assert handoff.main(["--launch", str(tmp_path / "handoffs" / "nao.md"), "--auto", "--dry-run", "--pane", "7"]) == 1
    other = tmp_path / "x.md"
    other.write_text("x", encoding="utf-8")
    assert handoff.main(["--launch", str(other), "--auto", "--dry-run", "--pane", "7"]) == 1
    assert "erro" in capsys.readouterr().err


def test_send_manda_clear_e_depois_o_prompt(tmp_path):
    calls = []
    handoff.send("continua", "7", delay=0, gap=0, enter_gap=0, run=lambda argv, check: calls.append(argv),
                 sleep=lambda s: None)
    texts = [c[-1] for c in calls]
    assert texts == ["/clear", "\r", "continua", "\r"]


def test_write_recusa_handoff_com_mais_de_25_linhas(tmp_path):
    with pytest.raises(handoff.HandoffError, match="máx 25"):
        handoff.write(tmp_path / "handoffs", "x\n" * 26, "z", now=datetime(2026, 10, 18, 9, 5))


def test_write_aceita_25_linhas_e_recusa_secao_copiada_do_sp(tmp_path):
    handoff.write(tmp_path / "handoffs", "x\n" * 25, "z", now=datetime(2026, 10, 18, 9, 5))
    with pytest.raises(handoff.HandoffError, match="secção do SP"):
        handoff.write(tmp_path / "handoffs", "## Objective\nc\n", "z", now=datetime(2026, 10, 18, 9, 6))
