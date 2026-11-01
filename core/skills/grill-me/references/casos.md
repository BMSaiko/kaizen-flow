# grill-me — casos, cenários e armadilhas

## Cenários de teste (Red/Green do SP skill-grill)

| Cenário | Entrada | Perguntas esperadas | Saída esperada |
|---|---|---|---|
| Claro | «Adiciona `--json` ao `sp-list.py`, só leitura, prova: output parseável» | 0-1 (só o que o código não diz, p.ex. nome da flag) | 2-4 decisões, paragem na 1ª ronda |
| Vago | «Melhorar o michi» | 2-3 na ronda 1 (quê, porquê, limites); 2 rondas no máximo | decisões + `Fora de âmbito` |
| Contraditório | «Sem tocar em scripts, mas o gate novo tem de correr no `sp-gates.py`» | 1 (a contradição, com as 2 leituras como opções) | decisão que resolve a contradição |
| Semente vazia | `TBD` / `<descreve o plano>` | 0 (bloqueio, nenhuma ronda) | 1 linha de bloqueio + o que colar |

Contagem = perguntas feitas ao user; factos descobertos com `Read`/`Grep` não contam.

## Fronteira de âmbito em mudanças em bloco

Num rename/refactor/rebrand em bloco a árvore tem uma raiz escondida, o **âmbito**; perguntar-lhe na Ronda 1, antes do design:

1. **O que conta como «o codebase»?** Um `grep -r` literal dá centenas de hits e só ~5% são ficheiros ativos; o resto são snapshots, backups, worktrees, notas históricas.
2. **O que é sagrado vs cosmético?** CHANGELOG, git log, versões nomeadas e notas de design históricas são append-only; strings visíveis ao utilizador são mutáveis.
3. **Só frontend ou tudo?** Default: primeiro o que o user vê, backend depois; só perguntar se o user quiser mais.

Regra prática: `grep -ri` > 100 hits e < 50 ficheiros ativos → parar e perguntar o âmbito. Receita (walk Python, exclusões, re-grep, `git diff --stat`): `vault-bulk-rename.md`. No vault, ruído típico: `.wt/<branch>/`, `data/.wt/`, `live-data/`, `data/.backup/`, `plans/<data>-*-{DR,DP,DA}.md`, `CHANGELOG.md` (nunca), `.dp_*.md`, `_draft/`.

## Armadilha da especulação de UI (YAGNI)

Não propor affordances **novas** (modais, auto-popups, wizards) que o user não pediu. Se um campo ou fluxo existente cobre o caso (Atlas: `description` já é textarea injetada no prompt; o modal de reject já tem a textarea de refine), apontá-lo e usá-lo; se falta uma feature, a ausência é a resposta. Exceção: pedido explícito → construir pequeno sobre o helper `openModal`, nunca um framework novo.

## Pitfalls

1. **Plano vazio = bloqueio imediato.** Sem decisão real, não gastar um turno a inferir nem inventar perguntas.
2. **Sem rajadas.** Sem fronteira limpa, fazer a 1 pergunta que mais desbloqueia.
3. **Recomendação obrigatória.** Nunca «o que achas?» sem palpite; o user aceita ou rejeita.
4. **Factos são teus.** Não pedir comandos que podes correr; exceção: preferência ou contexto que não observas.
5. **Guarda de recursão.** Pergunta já feita ou fechada numa nota anterior: largar; fronteira vazia após dedup = nota «0 rounds» e sair.
6. **One-shot.** Ver `atlas.md`: cada invocação é uma ronda.
