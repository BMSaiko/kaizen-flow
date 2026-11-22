"""Testes do vigiar da fila pelo LLM (`sp_fila_vigiar.passo` puro e o CLI) com leituras sintéticas."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import sp_fila_vigiar as fv  # noqa: E402


def leitura(sps=None, vivo=True, log="", fim=False):
    return {"sps": sps or {}, "vigia_vivo": vivo, "log": log, "fila_existe": not fim}


def sp(estado, msg=None):
    return {"estado": estado, "msg": msg}


def test_primeiro_tick_emite_estado_atual_de_cada_sp():
    mem = fv.memoria_nova()
    linhas, fim = fv.passo(mem, leitura({"a": sp("a-correr"), "b": sp("pendente")}))
    assert linhas == ["a: a-correr", "b: pendente"]
    assert fim is None


def test_transicao_repetida_nao_volta_a_sair():
    mem = fv.memoria_nova()
    fv.passo(mem, leitura({"a": sp("a-correr")}))
    linhas, _ = fv.passo(mem, leitura({"a": sp("a-correr")}))
    assert linhas == []


def test_transicao_nova_sai_uma_vez():
    mem = fv.memoria_nova()
    fv.passo(mem, leitura({"a": sp("a-correr")}))
    linhas, _ = fv.passo(mem, leitura({"a": sp("pergunta", "qual ramo?")}))
    assert linhas == ["a: pergunta (qual ramo?) · DECISÃO DO UTILIZADOR"]
    assert fv.passo(mem, leitura({"a": sp("pergunta", "qual ramo?")}))[0] == []


def test_bloqueado_e_falhou_pedem_atencao():
    mem = fv.memoria_nova()
    linhas, _ = fv.passo(mem, leitura({"a": sp("bloqueado", "merge recusado"), "b": sp("falhou")}))
    assert linhas == ["a: bloqueado (merge recusado) · ATENÇÃO", "b: falhou · ATENÇÃO"]


def test_merge_do_log_sai_uma_vez_e_ignora_lock_ocupado():
    log = ("2026-11-15T10:00:00 merge a: ok 3 ficheiros\n"
           "2026-11-15T10:00:10 merge b: lock ocupado, repetir\n")
    mem = fv.memoria_nova()
    linhas, _ = fv.passo(mem, leitura({}, log=log))
    assert linhas == ["a: merge feito"]
    assert fv.passo(mem, leitura({}, log=log))[0] == []


def test_lancou_vem_da_seguinte_no_log():
    log = "2026-11-15T10:00:00 seguinte a: lancou\n"
    linhas, _ = fv.passo(fv.memoria_nova(), leitura({}, log=log))
    assert linhas == ["a: seguinte lancou"]


def test_fim_pelo_log():
    linhas, fim = fv.passo(fv.memoria_nova(), leitura({}, vivo=False, log="2026-11-15T10:00 fila terminada: tudo feito\n"))
    assert linhas == ["fim: tudo feito"]
    assert fim == 0


def test_fim_quando_estado_da_fila_desaparece():
    linhas, fim = fv.passo(fv.memoria_nova(), leitura({}, vivo=False, fim=True))
    assert linhas == ["fim: fila parada ou removida"]
    assert fim == 0


def test_vigia_morto_avisa_uma_vez_e_da_rc_1():
    mem = fv.memoria_nova()
    linhas, fim = fv.passo(mem, leitura({"a": sp("a-correr")}, vivo=False))
    assert "vigia morto" in linhas[-1] and "sp-vigia.py" in linhas[-1]
    assert fim == 1
    linhas2, fim2 = fv.passo(mem, leitura({"a": sp("a-correr")}, vivo=False))
    assert linhas2 == [] and fim2 == 1


def test_vigia_morto_sem_spots_por_fechar_nao_e_erro():
    """Vigia já saiu, mas todos os SPs estão tratados: fim 0."""
    log = "x merge a: ok\nx seguinte a: fim\nx fila terminada: ok\n"
    _, fim = fv.passo(fv.memoria_nova(), leitura({"a": sp("done")}, vivo=False, log=log))
    assert fim == 0


def test_cli_uma_vez_devolve_estado_e_rc(tmp_path, monkeypatch, capsys):
    pasta = tmp_path / "fila1"
    pasta.mkdir()
    (pasta / "vigia.log").write_text("", encoding="utf-8")
    monkeypatch.setattr(fv, "ler_fila", lambda fila: {"sps": {"a": sp("a-correr")}})
    monkeypatch.setattr(fv, "_pasta", lambda fila: pasta)
    monkeypatch.setattr(fv, "_vigia_vivo", lambda pidf: True)
    rc = fv.main(["fila1", "--uma-vez"])
    assert rc == 0
    assert "a: a-correr" in capsys.readouterr().out


def test_cli_fila_desconhecida(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fv, "_pasta", lambda fila: tmp_path / "nada")
    assert fv.main(["nada", "--uma-vez"]) == 1


def test_main_aceita_a_pasta_da_fila(tmp_path, monkeypatch, capsys):
    (tmp_path / "fila-x").mkdir()
    monkeypatch.setattr(fv.pe, "raiz", lambda: tmp_path)
    vistos = []
    monkeypatch.setattr(fv, "ler_tudo", lambda fila: vistos.append(fila) or
                        {"sps": {}, "vigia_vivo": True, "log": "", "fila_existe": True})
    assert fv.main([str(tmp_path / "fila-x"), "--uma-vez"]) == 0
    assert vistos == ["fila-x"]


def test_main_fila_desconhecida_rc_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fv.pe, "raiz", lambda: tmp_path)
    assert fv.main([str(tmp_path / "nao-existe"), "--uma-vez"]) == 1
