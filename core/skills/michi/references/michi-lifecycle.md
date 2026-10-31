# michi — Document Lifecycle

Movido de `SKILL.md`; texto integral.

## Document Lifecycle Management

DR/DP/SP vivem em `knowledge/projects/kaizen/<project>/{dr,dp,sp}/{TODO,Doing,Done}/` e movem-se TODO → Doing → Done. O campo `status`/`updated` do frontmatter acompanha a pasta.

SP (scripts em `scripts/`, correr com `python -I`):
- `sp-list.py [--project P] [--status todo|doing] [--all]` — listar SPs pendentes.
- `sp-move.py [--project P] <slug> doing` — ao iniciar a execução; `done` ao concluir.
- `sp-validate.py <ficheiro...>` — validar o contrato das 8 secções.
- `sp-new.py --project P --slug S --priority P2` — criar SP vazio em `sp/TODO`.

DR/DP: `doc-move.py <dr|dp> <slug> todo|doing|done` e `doc-list.py <dr|dp> [--all]` (acrescentam `status`/`updated` se faltarem).

| Evento | Ação |
|--------|------|
| DR/DP start | `doc-move.py <tipo> <slug> doing` |
| DR/DP complete | `doc-move.py <tipo> <slug> done` |
| SP execution start | `sp-move.py <slug> doing` |
| SP complete | `sp-move.py <slug> done` |

`/michi status` = `sp-list.py --all` + `doc-list.py dr` + `doc-list.py dp`; mostrar as pastas `Doing` com a hora da última modificação para destacar trabalho parado.
