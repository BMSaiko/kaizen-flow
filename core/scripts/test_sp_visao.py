"""Testes de sp-visao.py (VISION.md por projeto: init, validate, resumo).

Uso: python -m pytest scripts/test_sp_visao.py -q
rc: o do pytest
"""
import subprocess
import sys
from pathlib import Path

import pytest
from sp_carregar import carregar

AQUI = Path(__file__).resolve().parent
visao = carregar(AQUI / "sp-visao.py")

VALIDO = """---
projeto: demo
ui: sim
stack: node, python
design_system: DESIGN.md
orcamento: 5 USD por SP, 20 USD por dia
---
# demo: visão

## Goal
Ajudar equipas pequenas a planear refeições sem desperdício.

## Users
- Famílias com 2 a 5 pessoas.

## Success criteria
- [ ] `npm test` passa em CI.
- [ ] Observação: um utilizador novo cria a primeira lista em menos de 2 minutos.

## Constraints
- Sem telemetria; funciona offline.

## Non-goals
- Não há conta de utilizador na v1.

## Milestones
1. Lista de compras.
2. Planeamento semanal.
"""


def _escrever(tmp_path, texto):
    f = tmp_path / "VISION.md"
    f.write_text(texto, encoding="utf-8")
    return f


def test_init_cria_esqueleto_com_frontmatter_e_seccoes(tmp_path):
    assert visao.main(["init", "demo", "--dir", str(tmp_path)]) == 0
    texto = (tmp_path / "demo" / "VISION.md").read_text(encoding="utf-8")
    for chave in ("projeto: demo", "ui:", "stack:", "design_system:", "orcamento:"):
        assert chave in texto
    for sec in visao.SECCOES:
        assert f"## {sec}" in texto


def test_init_nao_sobrescreve_sem_force(tmp_path, capsys):
    assert visao.main(["init", "demo", "--dir", str(tmp_path)]) == 0
    assert visao.main(["init", "demo", "--dir", str(tmp_path)]) == 1
    assert "já existe" in capsys.readouterr().err
    assert visao.main(["init", "demo", "--dir", str(tmp_path), "--force"]) == 0


def test_init_recusa_nome_invalido(tmp_path, capsys):
    assert visao.main(["init", "../fora", "--dir", str(tmp_path)]) == 2
    assert visao.main(["init", "", "--dir", str(tmp_path)]) == 2
    assert not (tmp_path.parent / "fora").exists()


def test_esqueleto_gerado_e_analisavel_mas_nao_valido(tmp_path, capsys):
    visao.main(["init", "demo", "--dir", str(tmp_path)])
    capsys.readouterr()
    assert visao.main(["validate", str(tmp_path / "demo" / "VISION.md")]) == 1
    saida = capsys.readouterr()
    assert "Goal" in saida.err and "orcamento" in saida.err


def test_validate_feliz(tmp_path, capsys):
    assert visao.main(["validate", str(_escrever(tmp_path, VALIDO))]) == 0
    assert "ok" in capsys.readouterr().out


def test_validate_vazio(tmp_path, capsys):
    assert visao.main(["validate", str(_escrever(tmp_path, ""))]) == 1
    assert "frontmatter" in capsys.readouterr().err


def test_validate_ficheiro_inexistente(tmp_path, capsys):
    assert visao.main(["validate", str(tmp_path / "nao-existe.md")]) == 1
    assert "não encontrado" in capsys.readouterr().err


@pytest.mark.parametrize("marca", ["TBD", "tbd", "TODO", "(preencher)", "<preencher>"])
def test_ec_079_validate_rejeita_placeholders(tmp_path, capsys, marca):
    texto = VALIDO.replace("Ajudar equipas pequenas a planear refeições sem desperdício.", marca)
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "Goal" in capsys.readouterr().err


def test_validate_seccao_em_falta(tmp_path, capsys):
    texto = VALIDO.replace("## Non-goals\n- Não há conta de utilizador na v1.\n\n", "")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "Non-goals" in capsys.readouterr().err


def test_validate_criterio_sem_comando_nem_observacao(tmp_path, capsys):
    texto = VALIDO.replace("- [ ] `npm test` passa em CI.", "- [ ] Ficar bonito.")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "critério" in capsys.readouterr().err


def test_validate_sem_criterios(tmp_path, capsys):
    texto = VALIDO.replace("- [ ] `npm test` passa em CI.\n- [ ] Observação: um utilizador novo cria a primeira lista em menos de 2 minutos.\n", "")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "Success criteria" in capsys.readouterr().err


def test_validate_ui_invalido(tmp_path, capsys):
    texto = VALIDO.replace("ui: sim", "ui: talvez")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "ui" in capsys.readouterr().err


def test_validate_ui_sim_exige_design_system(tmp_path, capsys):
    texto = VALIDO.replace("design_system: DESIGN.md", "design_system: nenhum")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "design_system" in capsys.readouterr().err


def test_validate_ui_nao_dispensa_design_system(tmp_path):
    texto = VALIDO.replace("ui: sim", "ui: nao").replace("design_system: DESIGN.md", "design_system: nenhum")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 0


def test_validate_orcamento_sem_numero(tmp_path, capsys):
    texto = VALIDO.replace("orcamento: 5 USD por SP, 20 USD por dia", "orcamento: baixo")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    assert "orcamento" in capsys.readouterr().err


def test_ec_080_validate_utf8_com_acentos_e_bom(tmp_path):
    f = tmp_path / "VISION.md"
    f.write_bytes(b"\xef\xbb\xbf" + VALIDO.replace("demo", "ação").encode("utf-8"))
    assert visao.main(["validate", str(f)]) == 0


def test_validate_crlf(tmp_path):
    f = tmp_path / "VISION.md"
    f.write_bytes(VALIDO.replace("\n", "\r\n").encode("utf-8"))
    assert visao.main(["validate", str(f)]) == 0


def test_validate_lista_todos_os_problemas(tmp_path, capsys):
    texto = VALIDO.replace("ui: sim", "ui: x").replace("Famílias com 2 a 5 pessoas.", "TBD")
    assert visao.main(["validate", str(_escrever(tmp_path, texto))]) == 1
    err = capsys.readouterr().err
    assert "ui" in err and "Users" in err


def test_resumo_mostra_projeto_e_criterios(tmp_path, capsys):
    assert visao.main(["resumo", str(_escrever(tmp_path, VALIDO))]) == 0
    out = capsys.readouterr().out
    assert "demo" in out and "ui: sim" in out and "2 critérios" in out and "Milestones" in out


def test_resumo_de_ficheiro_invalido_rc1(tmp_path):
    assert visao.main(["resumo", str(_escrever(tmp_path, ""))]) == 1


def test_cli_sem_argumentos_rc2():
    r = subprocess.run([sys.executable, "-I", str(AQUI / "sp-visao.py")], capture_output=True, text=True)
    assert r.returncode == 2
