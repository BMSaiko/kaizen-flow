---
name: grill-me
description: Relentless interview to sharpen a plan or design
version: 1.4.0
author: Matt Pocock (adapted for Hermes)
license: MIT
platforms:
- linux
- macos
- windows
triggers:
- grill me
- grill-me
- grill this
- stress test this
- stress-test this
metadata:
  hermes:
    tags:
    - interview
    - design
    - plan
    - decision
    - productivity
    category: productivity
---
# Grill-me

Protocolo de entrevista implacável. Corre-se inline; não há skill separada para carregar.

# Protocolo

Entrevistar o user sem tréguas até haver entendimento partilhado. Mapear como **árvore de decisão**: cada decisão ramifica nas que dela dependem.

Trabalhar a árvore em **rondas**. A **fronteira** é toda a decisão cujos pré-requisitos estão fechados: as perguntas que podes fazer _agora_ sem adivinhar respostas ainda não ouvidas. Perguntar a fronteira inteira numa ronda: numerar cada pergunta e dar a resposta recomendada; depois esperar as respostas antes da ronda seguinte.

```
? **Q1** - **<tópico curto>**: <pergunta>?
> <resposta recomendada com razão>

---

? **Q2** - **<tópico curto>**: <pergunta>?
> <resposta recomendada com razão>
```

As respostas remodelam a árvore: decisões fechadas empurram a fronteira e desbloqueiam as dependentes. Recalcular e perguntar a ronda seguinte; pergunta cuja resposta depende de outra ainda aberta nesta ronda pertence a uma ronda _posterior_.

Descobrir _factos_ é trabalho teu, nunca do user: usar `Bash`, `Read`, `Grep`/`Glob` ou `WebSearch`; não pedir ao user o que podes ver. Exploração em curso só atrasa as perguntas a jusante; perguntar já o resto. As _decisões_ são do user: pô-las e esperar.

Fim: fronteira vazia, todos os ramos visitados, nada assumido em silêncio. Não agir antes de o user confirmar o entendimento partilhado.

# Armadilha da especulação de modal/UI (YAGNI, com saída por pedido explícito)

No grilling não propor affordances de UI **novas** (modais, auto-popups, wizards pós-run) que o user não pediu:

- **Não** propor «modal pré-run» para escrever o plano/decisão quando a descrição do card **já é uma textarea editável** injetada no prompt do spawn (Atlas: campo `description` ligado a `cardDescription`). Ponytail degrau 1: «isto precisa de existir?» — a textarea já lá está.
- **Não** propor «auto-abrir modal de refine após o run» se o fluxo de reject já abre o mesmo modal ao clique (Atlas: o modal de reject tem a textarea de refine + submit); auto-abrir especula uma UX não pedida.
- **Regra:** se um campo ou fluxo existente cobre o caso descrito, apontá-lo e usá-lo; se falta uma feature, a ausência é a resposta.

**Exceção:** se o user pediu *explicitamente* o modal, construir pequeno sobre o helper `openModal` existente, nunca um framework novo. Em chat o grilling é inline; no Atlas o worker trata as rondas.

# Validação da entrada — ANTES da 1ª ronda (crítico)

A semente do plano/decisão (descrição do card Atlas, mensagem do user, bloco `<descreve o plano>`) é pré-requisito de todas as rondas. Se está **em falta, vazia ou é placeholder literal**, não há fronteira a construir: não improvisar uma adivinhando a intenção, não abrir rondas, nem sequer começar a escrever um bloco de perguntas (escrevê-lo É a falha).

Sementes inválidas (tratamento igual):
- String vazia / só espaços;
- Placeholders literais: `<descreve o plano>`, `<descreve a decisao>`, `<descreve o design>`, `TODO`, `TBD`, `???`, `...`, qualquer `<...>` que pareça slot de template;
- Só o esqueleto do template sem conteúdo (nome do mundo + slug + «descreve a decisão»);
- «grill this» apontado a um card Atlas cuja descrição é o template acima (falha silenciosa, ver Pitfall 1).

**Ação obrigatória (1ª resposta, mais nada):**
1. PARAR: sem «ronda 1» sobre intenção assumida nem bloco Q1/Q2/Q3.
2. Reportar numa linha o bloqueio exato (que placeholder/slot) e o que é entrada válida (2-5 linhas).
3. Próxima ação do user: onde colar (chat ou descrição do card) e o que a próxima sessão fará («DR → grill-me → DP → DA, com notas no fim»).
4. No Atlas: criar nota com tags `grilled, decision, blocked, needs-input` e mover o card para `review` com `result=BLOCKER` (protocolo e escrita da nota na skill `atlas-wrapper-python`); não arquivar o card.
5. Sair; sem polling.

**Carregada pelo user fora do Atlas** («grill me»/«grill this» no chat): plano na mesma mensagem = semente real, avançar; senão perguntar uma vez «cola o plano/decisão em 2-5 linhas aqui, ou aponta-me o card Atlas com description preenchida» e parar (mesma recusa: o chat não difere do Atlas).

Anti-padrão evitado: construir a fronteira sobre intenção **assumida** (inventar um plano e testar a invenção) é alucinação com verniz socrático.

# Fronteira de âmbito em mudanças em bloco (2026-09-02)

Num **rename/refactor/rebrand em bloco** («renomeia X para Y», «reescreve todo o Z», «depreca W em todo o lado»), a árvore tem uma raiz escondida: o **âmbito**. Três sub-perguntas pedem ronda inicial antes das de design:

1. **O que conta como «o codebase»?** Um `grep -r` literal dá 745 hits onde só 30-50 são ficheiros que o user abre; o resto são snapshots, backups, worktrees, artefactos históricos. Determina o tamanho do diff e o risco.
2. **O que é sagrado vs cosmético?** Artefactos históricos (entradas de CHANGELOG.md, git log, versões nomeadas, nomes de vendor em metadados) são append-only por contrato social; reescrevê-los mente sobre o passado. Strings visíveis ao utilizador são mutáveis.
3. **Só frontend ou tudo?** Resposta canónica do user («no UI tudo q é kanban passa para michi e futuramente mudamos o código e backend, para já só o que é mostrado ao cliente final»): renomear primeiro o que o user vê, backend para depois. É o default; só perguntar se o user quiser mais.

**Armadilha do rename no vault (Second Brain do user, 2026-09-02):** com centenas de hits de `grep -ri '<termo>'`, ~5% é código/docs ativos e ~95% é isto:
- `.wt/<branch>/` — worktrees git, cópias quase idênticas; renomear suja o histórico e parte `git log`/bisect;
- `data/.wt/`, `live-data/`, `data/.backup/` — estado de runtime e backups datados (dados, não código);
- `knowledge/projects/<X>/plans/<data>-<tópico>-{DR,DP,DA}.md` — notas de design históricas;
- `CHANGELOG.md` — append-only (reescrever mente sobre o passado): **nunca**;
- rascunhos `.dp_*.md`, `_draft/` — trabalho em curso.

**Regra prática:** `grep -ri` > 100 hits e < 50 ficheiros ativos a editar: **parar e perguntar o âmbito primeiro** («só codebase ativo, ou todos os hits incluindo worktrees/backups/histórico?»); decide o diff e se o CHANGELOG também se reescreve. É cadeira de âmbito, não de design: normalmente **Ronda 1** de um grill de mudança em bloco, antes de «o que significa o novo nome». Receita concreta (walk Python com `os.walk`, conjuntos de exclusão, verificação por re-grep e `git diff --stat`): `references/vault-bulk-rename.md`.

# Invocação no Atlas (ping-pong assíncrono)

Com a invocação a partir de um card Atlas, o template do prompt já traz nome do mundo, slug e descrição. **O grilling é ping-pong assíncrono entre o worker e a UI Atlas; o pane wezterm NÃO é o canal** (um loop «esperar resposta» bloqueia para sempre em headless):

1. Ler bem a descrição. Placeholder (`<descreve a decisao>`, `TBD`, secção «O que quero grillar» vazia): não disparar às cegas; abortar para nota (ver Validação).
2. Escrever as perguntas da Ronda 1 numa nota via API do kanban (URL no template). Tags `grilled, decision, awaiting-user, card-<cardId>` (`card-` com hífen, não `card:`; os matchers aceitam ambos). Título = título do card; corpo = Ronda 1 completa com as recomendações.
3. Mover o card para `review` e escrever o `result` («Round 1 gravado como nota n<id>; à espera de resposta via reply no card»).
4. Sair limpo (rc=0); o user responde pela UI.

**Reply (UI Atlas ↔ worker, 2026-09-01).** Botão `reply` nas notas grilled (`src/views/notes.ts::replyGrill`) e `Reply` no modal do terminal (`src/views/kanban.ts::openReplyModal`, `data-act="reply-from-term"`), ambos com modal dividido (markdown do card à esquerda, textarea à direita):
- **Na nota:** cria um card de grilling **NOVO** (clona a origem, anexa a resposta à descrição, põe em `doing` com `skills: ['grill-me']`, chama `launchRun`, navega); preserva o estado do original e dá uma Ronda 2 limpa.
- **No modal do terminal:** **re-spawn** do mesmo card (anexa a resposta, chama `runCard`), para manter a sessão viva no pane.

A nota tem a tag `card-<id>` do card **origem**. Numa nova ronda **ler primeiro a nota anterior**; as respostas do user estão na descrição do card novo em `## Reply do user (<timestamp>)`. O padrão-nota sobrevive à morte do worker; sem ele a skill abortava em 3 s com o card em review sem pergunta nenhuma (BUG 3h em `atlas-wrapper-python`).

**Auto-deteção (opcional):** o `viewTerminal` do Atlas faz poll do `.log` pela regex `? **Q\d+**` e abre o modal de reply; mudar o formato das perguntas obriga a atualizar a regex.

# Pitfalls

1. **Plano vazio = bloqueio imediato (BUG 3h, 2026-09-01).** Descrição sem decisão real (placeholder, «TBD», `<descreve...>`, «O que quero grillar» vazio): não gastar um turno a inferir. Criar nota «Grilling bloqueado: <card-id> — description vazia», tags `grilled, decision, blocked, needs-input`, corpo «Card <id> sem decisão. Worker abortou sem rounds. Ação: user cola plano/decision na description e clica Reply.»; mover para `review`; não inventar perguntas.
2. **Sem rajadas.** Sem fronteira limpa (1 facto disponível e 3 coisas dependentes), fazer a 1 pergunta que desbloqueia mais; melhor 1 do que 5 especulativas.
3. **Resposta recomendada obrigatória.** Cada pergunta leva o teu melhor palpite; o user aceita/rejeita (é o contrato). Nunca «o que achas?» sem recomendação.
4. **Factos são teus.** Não pedir ao user comandos que podes correr; exceção: preferência ou contexto que não observas («tens acesso a X?»).
5. **Guarda de recursão.** Pergunta que já apareceu na fronteira (feita, ou fechada numa nota anterior): largar; fronteira vazia após dedup = nota «0 rounds» e sair.
6. **A skill é one-shot.** Não prometer «espero a resposta e faço a Ronda 2» (não estarás vivo): cada invocação é UMA ronda, documentada numa nota; a invocação seguinte lê-a e continua.
