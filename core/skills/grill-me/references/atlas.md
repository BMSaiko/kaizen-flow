# grill-me no Atlas (ping-pong assíncrono)

O grilling é ping-pong entre o worker e a UI Atlas; o pane wezterm NÃO é o canal (um loop «esperar resposta» bloqueia para sempre em headless). A skill é one-shot: cada invocação é UMA ronda, documentada numa nota; a seguinte lê-a e continua. Nunca prometer «espero e faço a Ronda 2».

## Fluxo de uma ronda

1. Ler bem a descrição do card. Placeholder (`<descreve a decisao>`, `TBD`, «O que quero grillar» vazio): não disparar às cegas; abortar para nota (ver «Semente inválida»).
2. Escrever as perguntas da Ronda 1 numa nota via API do kanban (URL no template). Tags `grilled, decision, awaiting-user, card-<cardId>` (`card-` com hífen; os matchers aceitam `card:`). Título = título do card; corpo = ronda completa com recomendações.
3. Mover o card para `review` e escrever o `result` («Round 1 gravado como nota n<id>; à espera de resposta via reply no card»).
4. Sair limpo (rc=0); o user responde pela UI.

## Formato de texto (headless)

```
? **Q1** - **<tópico curto>**: <pergunta>?
> <resposta recomendada com razão>

---

? **Q2** - **<tópico curto>**: <pergunta>?
> <resposta recomendada com razão>
```

Auto-deteção: o `viewTerminal` do Atlas faz poll do `.log` pela regex `? **Q\d+**` e abre o modal de reply; mudar o formato obriga a atualizar a regex.

## Semente inválida no Atlas

Criar nota «Grilling bloqueado: <card-id> — description vazia», tags `grilled, decision, blocked, needs-input`, corpo «Card <id> sem decisão. Worker abortou sem rounds. Ação: user cola plano/decision na description e clica Reply.»; mover o card para `review` com `result=BLOCKER` (protocolo na skill `atlas-wrapper-python`); não arquivar; sair sem polling. Foi o BUG 3h de 2026-09-01 (a skill abortava em 3 s com o card em review sem pergunta).

## Reply (UI Atlas ↔ worker, 2026-09-01)

Botão `reply` nas notas grilled (`src/views/notes.ts::replyGrill`) e `Reply` no modal do terminal (`src/views/kanban.ts::openReplyModal`, `data-act="reply-from-term"`), ambos com modal dividido (markdown à esquerda, textarea à direita):

- **Na nota:** cria um card de grilling NOVO (clona a origem, anexa a resposta à descrição, `doing`, `skills: ['grill-me']`, `launchRun`); preserva o original e dá uma Ronda 2 limpa.
- **No modal do terminal:** re-spawn do mesmo card (anexa a resposta, `runCard`), mantendo a sessão viva no pane.

A nota tem a tag `card-<id>` do card origem. Numa nova ronda ler primeiro a nota anterior; as respostas estão na descrição do card novo em `## Reply do user (<timestamp>)`.
