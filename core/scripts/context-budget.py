#!/usr/bin/env python3
"""Mede o contexto carregado no arranque e sai com rc=1 se passar o limite (15 KB).

Fontes sempre carregadas: CLAUDE.md, AGENTS.md, MEMORY.md (memória do projeto),
descrições das skills em .claude/skills/*/SKILL.md. Limites por ficheiro avisam cedo o
crescimento silencioso de CLAUDE.md e AGENTS.md.
Uso: python -I scripts/context-budget.py
"""
import re
import sys
from pathlib import Path

TOTAL_LIMIT = 15 * 1024
FILE_LIMITS = {"CLAUDE.md": 3 * 1024, "AGENTS.md": 9 * 1024}
ROOT = Path(__file__).resolve().parent.parent
MEMORY_INDEX = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ROOT)) / "memory" / "MEMORY.md"
DESCRIPTION = re.compile(r"^description:\s*(.*)$", re.MULTILINE)


def size(path):
    try:
        return len(Path(path).read_bytes())
    except OSError:
        return 0


def skill_descriptions(skills_dir):
    """Bytes de `name + description` de cada skill (o que a lista de skills carrega)."""
    total = 0
    for skill in sorted(Path(skills_dir).glob("*/SKILL.md")):
        head = skill.read_text(encoding="utf-8", errors="replace").split("---")[1:2]
        match = DESCRIPTION.search(head[0]) if head else None
        total += len(skill.parent.name.encode()) + (len(match.group(1).encode()) if match else 0)
    return total


def collect(root=ROOT, memory_index=MEMORY_INDEX):
    root = Path(root)
    return [
        ("CLAUDE.md", size(root / "CLAUDE.md"), "sempre"),
        ("AGENTS.md", size(root / "AGENTS.md"), "sempre"),
        ("MEMORY.md", size(memory_index), "sempre"),
        ("descrições das skills", skill_descriptions(root / ".claude" / "skills"), "sempre"),
    ]


def check(rows, total_limit=TOTAL_LIMIT, file_limits=FILE_LIMITS):
    """Devolve (total, lista de falhas)."""
    total = sum(n for _, n, _ in rows)
    failures = []
    if total > total_limit:
        failures.append(f"total {total} B > limite {total_limit} B")
    for name, n, _ in rows:
        if name in file_limits and n > file_limits[name]:
            failures.append(f"{name} {n} B > limite {file_limits[name]} B")
    return total, failures


def main():
    rows = collect()
    total, failures = check(rows)
    print("fonte | bytes | carregado")
    for name, n, when in rows:
        print(f"{name} | {n} | {when}")
    print(f"TOTAL | {total} | limite {TOTAL_LIMIT}")
    for failure in failures:
        print(f"FALHA: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
