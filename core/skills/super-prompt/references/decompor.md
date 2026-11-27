# Decompor: VISION.md -> programa de SPs

Sem grill humano: `kaizen vision decompor <VISION.md>` (ou `python -I scripts/sp-decompor.py <VISION.md>`) lê um `VISION.md` válido e cria em `sp/TODO` uma mãe (`<projeto>-visao-<data>`) e um filho por marco (`<projeto>-visao-m<N>-<data>`). Não executa nada: o `sp-fila` corre-os.

## Marcos
`N. título [ficheiros F, horas H] (depende: 1, 2) \`comando\``. Sem `depende:` depende do marco anterior; sem `[ficheiros, horas]` assume 4 e 2 h (`Assuncao:` no SP). Teto por filho: 6 ficheiros ou 3 h; acima disso o marco é rejeitado (parti-lo). Ciclos de dependências são rejeitados e nada é criado.

## O que cada SP leva
- 8 secções, `modo: auto`, critério e prova = comando do marco (sem comando, o 1.º critério com comando do VISION).
- Gates: o comando do marco mais `--gate CMD` (repetível) ou os de `sp-gates --sugerir` sobre `--repo`.
- `## Decisões` do VISION (Goal, Constraints, Non-goals, stack, orçamento); o que falta vira `Assuncao:`.
- `ui: sim`: `## Esboço` com `Assuncao:` a resolver no DR com o `design_system` do VISION.

## Garantias
- Idempotente: marco já existente (qualquer data) não é recriado; só os que faltam.
- Valida tudo com `sp-validate`; se algo falhar, remove o que criou (rc 1).
- `--dry-run` só lista. Revisão de qualidade: `sp-revisor` sobre cada SP antes do `sp-fila` (`/auditar`).
