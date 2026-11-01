---
description: Listar os Super Prompts pendentes (TODO e Doing) agrupados por programa, com estado, prioridade e idade
version: 1.1.0
---
Corre `python -I scripts/sb.py sp list $ARGUMENTS` (sem argumentos = Doing antes de TODO, P1→P3, mais antigo primeiro; aceita `--sort priority|created|status`, `--reverse`, `--project <nome>`, `--status todo|doing`, `--all`, `--flat`, `--tudo`) e mostra a saída tal como vem, em português europeu, destacando as linhas com `⚠ status≠pasta`.

A saída abre com `Próximo: <slug>` (primeiro SP elegível: Doing antes de TODO, P1→P3, sem dependências por cumprir, mãe `kind: program` nunca conta) e `Bloqueados (N)` com `slug ← dependência em falta` (máx. 5). Tem no máximo 40 linhas, com `… +N linhas (--tudo)` no corte; `--tudo` mostra tudo.

Por omissão a vista é agrupada: cada SP-mãe (`kind: program`) com o progresso (`2/3 feitos`, `pronto para fechar`) e os filhos (`parent:`) por baixo, com `├─`/`└─`, estado (`▶ Doing`, `○ TODO`, `✔ Done`), prioridade, data de criação com idade (`2026-10-16 (2d)`) e `aguarda: <dependências por cumprir>` (só aviso, nunca bloqueia); os SPs sem mãe vêm a seguir. `--flat` dá a tabela plana antiga (com `#`); `--tree` é sinónimo do predefinido.

## Seletor (depois da listagem)

Se houver SPs listados, a seguir à saída abrir um seletor com AskUserQuestion (uma pergunta, `multiSelect: false`), para o user escolher um SP e arrancá-lo:

1. Ordenar os SPs elegíveis (TODO e Doing, filhos e avulsos; SPs-mãe `kind: program` só como agrupador, não selecionáveis) pela ordem da listagem.
2. Dois passos (AskUserQuestion aceita no máximo 4 opções):
   - **Passo 1, projeto**: opções = projetos com SPs elegíveis, `description` = nº de SPs (e quantos Doing). Se houver mais de 4 projetos: 3 projetos + `Mais →`. Se houver só 1 projeto, saltar este passo.
   - **Passo 2, SP**: SPs elegíveis desse projeto, pela ordem da listagem. Cada opção: `label` = slug, `description` = `▶ Doing`/`○ TODO`, prioridade, idade (e `aguarda: …` se houver). Até 4 SPs numa página; com mais de 4: 3 SPs + `Mais →` (página seguinte; na última volta ao início).
3. `Mais →` (em qualquer passo): repetir o AskUserQuestion com a página seguinte, sem voltar a listar. "Other" já existe por omissão para escrever um slug.
4. SP escolhido: obter o caminho absoluto (o mesmo que a listagem usa) e seguir os passos 4 e 5 do `/sp-handoff` (bloco `/michi <caminho>` + pergunta sim/não + `sp-handoff.py --launch`), **sem escrever progresso** (a sessão atual não trabalhou nele).
5. Se o SP escolhido estiver em TODO, avisar que o `/michi` o começa a trabalhar mas não o move para Doing (isso é `scripts/sp-move.py`, só com ordem do user).

A listagem em si é só leitura: nunca mover nem editar SPs, nunca `git commit`.
