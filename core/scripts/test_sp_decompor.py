"""Testes de sp-decompor.py (VISION.md -> programa de SPs).

Uso: python -m pytest scripts/test_sp_decompor.py -q
rc: o do pytest
"""
from pathlib import Path

import pytest
from sp_carregar import carregar

AQUI = Path(__file__).resolve().parent
dec = carregar(AQUI / "sp-decompor.py")
valida = carregar(AQUI / "sp-validate.py")
listar = carregar(AQUI / "sp-list.py")


def vision(ui="nao", marcos=None):
    marcos = marcos or [
        "1. Modelo de dados [ficheiros 3, horas 1] `python -m pytest -k modelo`",
        "2. API de refeições (depende: 1) `python -m pytest -k api`",
        "3. Ecrã de planeamento (depende: 1, 2) [ficheiros 5, horas 3]",
    ]
    ds = "DESIGN.md" if ui == "sim" else "nenhum"
    return f"""---
projeto: demo
ui: {ui}
stack: node, python
design_system: {ds}
orcamento: 5 USD por SP, 20 USD por dia
---
# demo: visão

## Goal
Planear refeições sem desperdício.

## Users
- Famílias pequenas.

## Success criteria
- [ ] `npm test` passa
- [ ] Observação: o ecrã mostra a semana

## Constraints
- Só stdlib.

## Non-goals
- Sem contas de utilizador.

## Milestones
""" + "\n".join(marcos) + "\n"


@pytest.fixture
def ambiente(tmp_path):
    (tmp_path / "sp-root" / "demo").mkdir(parents=True)
    return tmp_path


def correr(ambiente, texto, *extra):
    v = ambiente / "VISION.md"
    v.write_text(texto, encoding="utf-8")
    return dec.main([str(v), "--root", str(ambiente / "sp-root"), "--data", "2026-11-23", "--priority", "P1", *extra])


def todos(ambiente):
    return sorted((ambiente / "sp-root" / "demo" / "sp" / "TODO").glob("*.md"))


def test_gera_mae_e_filhos_validos(ambiente):
    assert correr(ambiente, vision()) == 0
    ficheiros = todos(ambiente)
    assert [f.stem for f in ficheiros] == [
        "demo-visao-2026-11-23", "demo-visao-m1-2026-11-23", "demo-visao-m2-2026-11-23", "demo-visao-m3-2026-11-23"]
    for f in ficheiros:
        assert valida.validate(f.read_text(encoding="utf-8"), "TODO") == [], f.name
    m3 = (ambiente / "sp-root/demo/sp/TODO/demo-visao-m3-2026-11-23.md").read_text(encoding="utf-8")
    assert "depends_on: [demo-visao-m1-2026-11-23, demo-visao-m2-2026-11-23]" in m3
    assert "`npm test`" in m3
    assert "Restrição (VISION): Só stdlib." in m3
    assert "Assuncao" not in m3.split("## 6.")[1].split("## 7.")[0].replace("Assuncao: ficheiros a definir", "")


def test_listavel_pelo_sp_list(ambiente):
    correr(ambiente, vision())
    slugs = {sp.slug for sp in listar.collect(ambiente / "sp-root")}
    assert "demo-visao-m1-2026-11-23" in slugs


def test_idempotente(ambiente, capsys):
    correr(ambiente, vision())
    antes = [f.read_bytes() for f in todos(ambiente)]
    assert correr(ambiente, vision()) == 0
    assert "nada a criar" in capsys.readouterr().out
    assert [f.read_bytes() for f in todos(ambiente)] == antes


def test_ui_sim_tem_esboco(ambiente):
    assert correr(ambiente, vision(ui="sim")) == 0
    m1 = (ambiente / "sp-root/demo/sp/TODO/demo-visao-m1-2026-11-23.md").read_text(encoding="utf-8")
    assert "ui: sim" in m1 and "## Esboço" in m1


def test_ciclo_rejeitado(ambiente, capsys):
    marcos = ["1. A (depende: 2) `x`", "2. B (depende: 1) `x`"]
    assert correr(ambiente, vision(marcos=marcos)) == 1
    assert "cíclicas" in capsys.readouterr().err
    assert todos(ambiente) == []


def test_marco_grande_rejeitado(ambiente, capsys):
    assert correr(ambiente, vision(marcos=["1. Enorme [ficheiros 9, horas 2] `x`"])) == 1
    assert "dividir" in capsys.readouterr().err


def test_marco_sem_comando_usa_o_do_vision(ambiente):
    assert correr(ambiente, vision(marcos=["1. Sem comando"])) == 0
    m1 = (ambiente / "sp-root/demo/sp/TODO/demo-visao-m1-2026-11-23.md").read_text(encoding="utf-8")
    assert "prova: npm test" in m1


def test_vision_invalido(ambiente, capsys):
    assert correr(ambiente, "---\nprojeto: demo\n---\n# x\n") == 1
    assert "VISION inválido" in capsys.readouterr().err
    assert todos(ambiente) == []


def test_dry_run_nao_escreve(ambiente, capsys):
    assert correr(ambiente, vision(), "--dry-run") == 0
    assert "criaria demo-visao-m1-2026-11-23" in capsys.readouterr().out
    assert todos(ambiente) == []


def test_gate_extra_em_cada_filho(ambiente):
    assert correr(ambiente, vision(), "--gate", "python -m ruff check .") == 0
    m2 = (ambiente / "sp-root/demo/sp/TODO/demo-visao-m2-2026-11-23.md").read_text(encoding="utf-8")
    assert "  - cmd: python -m ruff check ." in m2 and "  - cmd: python -m pytest -k api" in m2
