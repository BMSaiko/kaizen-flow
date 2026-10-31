# Receita de rename em bloco

Renomear um termo num vault de notas ou repo misto em que o código ativo é pequeno mas `grep -ri` dá centenas de hits. Usar depois de a ronda de âmbito do grill-me fechar «só codebase ativo, ou todos os hits?» (default: só ativo). Aplica-se a «renomear X para Y», «trocar X por Y em todo o lado», rebrand ou deprecação em bloco, quando o repo mistura **código** (mutável, poucos ficheiros) com **artefactos históricos**; um `rg -l X | xargs sed -i` cego daria um diff de vários MB.

## Exclusões por defeito (adaptar ao projeto; nunca incluir sem override do user)

| Caminho | Categoria | Porquê |
|---|---|---|
| `.wt/` | cópias de worktrees | histórico git; duplica a mudança N vezes |
| `.backup/`, `backups/` | backups datados | trabalho inútil |
| `data/`, `live-data/` | estado de runtime | dados, não código |
| `CHANGELOG.md` | histórico append-only | mentir sobre o passado |
| `plans/`, `_draft/`, `.dp_*.md` | notas de design / trabalho em curso | escritas com o nome ANTIGO ou reescritas depois |
| `node_modules/`, `.venv/`, `dist/`, `build/`, `*.lock`, `package-lock.json`, `uv.lock` | gerado/vendored | nunca |

## Walk em Python (Windows, sem problemas de quoting)

Quando `rg`/`sed` falham no host (tradução de caminhos MSYS, binários em falta, BOM/CRLF). Correr na raiz: `python rename.py OLD NEW` (dry-run) ou `... --apply`.

```python
import os, re, sys
from pathlib import Path

root = Path.cwd()
old, new = sys.argv[1], sys.argv[2]
apply = "--apply" in sys.argv[3:]
SKIP_DIRS = {".git", ".obsidian", ".venv", "venv", "node_modules", "dist", "build", ".next",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".wt", ".backup",
             "data", "live-data"}
SKIP_NAMES = {"CHANGELOG.md"}
KEEP_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".md", ".yaml", ".yml", ".toml", ".json",
            ".sh", ".cmd", ".bat", ".html", ".css", ".vue"}
pattern = re.compile(re.escape(old), re.IGNORECASE)

def smart_replace(text):  # preserva maiúsculas: old->new, Old->New, OLD->NEW
    def repl(m):
        s = m.group(0)
        if s.isupper():
            return new.upper()
        return new[:1].upper() + new[1:] if s[0].isupper() else new
    return pattern.sub(repl, text)

hits = []
for dirpath, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        p = Path(dirpath) / f
        if p.name in SKIP_NAMES or "lock" in p.name.lower() or p.suffix.lower() not in KEEP_EXT:
            continue
        try:
            if pattern.search(p.read_text(encoding="utf-8")):
                hits.append(p)
        except (OSError, UnicodeDecodeError):
            pass
for h in hits:
    if apply:
        h.write_text(smart_replace(h.read_text(encoding="utf-8")), encoding="utf-8")
    print(("patched: " if apply else "would patch: ") + str(h.relative_to(root)))
```

## Verificação (depois do patch)

1. Re-pesquisar o termo antigo com as mesmas exclusões (o dry-run): deve dar **zero**; sobras = caso falhado (tipicamente extensão em falta em `KEEP_EXT`).
2. `git diff --stat`: < 100 ficheiros e < 1 MB. Diff de 5+ MB = exclusão furada (`.wt/` ou `.backup/` entrou): abortar, reset, apertar o filtro.
3. Verificar 2-3 ficheiros representativos (código, doc, config) por falsos positivos (palavra de domínio, nome de vendor, conceito alheio): o closure trata maiúsculas, não semântica.

## Smoke do runtime

A superfície afetada (verbo de CLI, vista de dashboard) precisa de uma corrida ponta a ponta: o nome novo aparece onde se espera, o antigo não, a feature funciona (`tool old list` → `tool new list` devolve o mesmo). Env vars, tabelas SQL e nomes de schema de tools que ficaram de propósito têm de continuar a bater com o que a UI renomeada lhes passa; «UI primeiro, backend depois» pede um alias temporário.

## Gotchas

- **MSYS** corrompe caminhos Windows no shell: usar `pathlib.Path("C:/...")` (barras normais servem).
- **BOM + CRLF** do `Out-File` do PowerShell parte parsers TOML/YAML estritos: ler com `encoding="utf-8-sig"` ou escrever via `pathlib`.
- Config que referencia caminhos `.wt/...` deixa-se em paz: aponta o caminho *histórico* («vê a worktree de agosto»).
- Nomes de schema de tools chegam ao modelo como identificadores: com «só frontend», não os mexer, ou o modelo continua a chamar o nome antigo; anotar no plano se vem um passe de backend.
