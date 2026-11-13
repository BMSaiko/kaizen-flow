"""Testes de scripts/sp-resumo.py: resumo de 1 ecrã de um SP (simples, mãe, com esboço)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402

sp_resumo = kaizen_engine.load("sp-resumo")

CORPO = """# Super Prompt - x

## 1. Role
Dono do processo de criação.

## 2. Context
- contexto

## 3. Objective (single sentence)
Fazer do nascimento do SP o único portão humano.

## 4. Success criteria (verifiable)
1. algo verificável

## 5. Constraints / invariants
- Trabalhar numa worktree.
- Stdlib apenas.

## 6. Seams (public interfaces to test / change)
- scripts/x.py

## 7. Steps (numbered, ordered)
1. Testes vermelhos.
2. Implementar.

## 8. Done-when
Critérios verificados.

## Decisões
- Sem grill não há SP.
- Fora de âmbito: mudar as 8 secções.
"""


def escrever(root, slug, extra="", corpo=CORPO, folder="TODO", parent=None, kind=None):
    p = root / "proj" / "sp" / folder / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"status: {folder}", "created: 2026-11-13T00:00:00Z", "updated: 2026-11-13T00:00:00Z", "phase: SP",
          f"slug: {slug}", "date: 2026-11-13", "project: proj", "priority: P1", "modo: auto",
          "commit: auto", "push: auto", "pr: auto", "gates:", "  - cmd: python -m pytest -q"]
    if parent:
        fm.append(f"parent: {parent}")
    if kind:
        fm.append(f"kind: {kind}")
    p.write_text("\n".join(fm) + ("\n" + extra if extra else "") + "\n---\n" + corpo, encoding="utf-8")
    return p


def test_resumo_simples_tem_seccoes_fixas(tmp_path):
    escrever(tmp_path, "x")
    rc, texto = sp_resumo.resumo(tmp_path, "x")
    assert rc == 0
    for titulo in ("Quê", "Porquê", "Forma", "Limites", "Prova", "Destino e autorizações"):
        assert titulo in texto
    assert "único portão humano" in texto
    assert "Fora de âmbito: mudar as 8 secções" in texto
    assert "python -m pytest -q" in texto
    assert "commit auto" in texto
    assert len(texto.splitlines()) <= 40
    assert max(len(linha) for linha in texto.splitlines()) <= 100


def test_resumo_rc1_sem_materia(tmp_path):
    escrever(tmp_path, "x", corpo=CORPO.replace("Fazer do nascimento do SP o único portão humano.", ""))
    rc, texto = sp_resumo.resumo(tmp_path, "x")
    assert rc == 1
    assert "Quê" in texto


def test_resumo_mae_acrescenta_filhos(tmp_path):
    escrever(tmp_path, "mae", kind="program")
    escrever(tmp_path, "a", parent="mae", folder="Done")
    escrever(tmp_path, "b", parent="mae", extra="depends_on: [a]")
    rc, texto = sp_resumo.resumo(tmp_path, "mae")
    assert rc == 0
    assert "Filhos" in texto
    assert "b" in texto and "depende de a" in texto
    assert len(texto.splitlines()) <= 40


def test_resumo_ui_mostra_esboco(tmp_path):
    escrever(tmp_path, "x", extra="ui: sim", corpo=CORPO + "\n## Esboço\n+------+\n| ecrã |\n+------+\n")
    rc, texto = sp_resumo.resumo(tmp_path, "x")
    assert rc == 0
    assert "Esboço" in texto and "| ecrã |" in texto


def test_resumo_ui_sem_esboco_rc1(tmp_path):
    escrever(tmp_path, "x", extra="ui: sim")
    rc, texto = sp_resumo.resumo(tmp_path, "x")
    assert rc == 1
    assert "Esboço" in texto


def test_resumo_limita_a_40_linhas(tmp_path):
    esboco = "\n".join(f"linha {i}" for i in range(60))
    escrever(tmp_path, "x", extra="ui: sim", corpo=CORPO + "\n## Esboço\n" + esboco + "\n")
    rc, texto = sp_resumo.resumo(tmp_path, "x")
    assert rc == 0
    assert len(texto.splitlines()) <= 40
