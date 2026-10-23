---
name: one-shot
description: Dar one shot a uma ideia de projeto - grill de ≥25 perguntas + horas disponíveis, árvore de SPs (mãe, filhos, netos) e execução pelo michi sem perguntas
version: 1.0.0
---
# one-shot

`/one-shot <ideia>`: o user responde a um grill longo uma só vez; depois o the agent executa tudo sem supervisão e o user valida no fim. Reutiliza `/grill-me`, `sp-new.py`, `sp-validate.py` e o `michi`; não duplica nenhum.

## Fase A - Grill (única fase com perguntas)
1. Banco de perguntas por domínio: `references/one-shot-perguntas.md`. Antes de perguntar, `Grep`/`Read` o que o repo/vault já responde (nunca perguntar factos).
2. Batches de 2-3 perguntas (`AskUserQuestion`), opção recomendada primeiro, default explícito. Mínimo **25 perguntas respondidas**, contadas numa lista corrente (`Q n/25`); adaptar o banco à ideia, mas todos os domínios têm de ser cobertos.
3. **Última pergunta, sempre:** «Quantas horas de trabalho tens para este projeto até ficar uma obra-prima?» (número; default 20). Guardar como `horas_disponiveis`.
4. Resumo em ≤15 linhas e um único «avanço com a árvore e a execução sem perguntas?» (nomear: criar SPs, executar, commits locais, sem push). Só depois de «sim».

## Fase B - Árvore de SPs
- Projeto michi/vault: `python -I scripts/sp-new.py --project <P> --program <slug> --children a,b:a,c:a+b --priority P1|P2|P3` (mãe + filhos); netos com `--slug <neto> --parent <filho> --depends-on ...`.
- Mãe: §2 com as decisões do grill (Q&A condensado) e `horas_disponiveis`; §4 com critérios verificáveis; filhos/netos preenchidos nas 8 secções (um folha = uma sessão, ≤1 fase de entrega com prova).
- Cada folha leva estimativa `h:` em §2 e prioridade P1 (núcleo) / P2 / P3 (polimento). `python -I scripts/sp-validate.py <todos>` tem de dar rc=0.

## Fase C - Orçamento de horas
- Ordenar folhas por dependência, depois por prioridade; somar `h:` até `horas_disponiveis` (reservar 15 % para gates e relatório).
- O que não cabe é cortado: primeiro P3/polimento, depois P2; nunca P1 nem o que outro P1 exige. Registar o corte na mãe em `## Corte de orçamento` (folha, h, motivo) e deixar a folha em TODO.

## Fase D - Execução sem perguntas
- Para cada folha elegível: `sp-move.py <folha> doing`, depois `/michi --auto <folha>` (**modo auto**, sem pergunta de arranque) (`michi/references/michi-modo-auto.md`; decisões em `## Decisões modo auto`). Uma folha por sessão; no fim da folha, `sp-handoff` automático (`--launch --auto`) para a seguinte.
- Sem `AskUserQuestion` na execução: ambiguidade → default mais conservador, registado em `## Decisões modo auto` no SP da folha.
- Código: repo do projeto novo (`~\Documents\code\<projeto>`), **commit local por fase** (assunto ≤72, autor do user, sem atribuição a agentes), **nunca push**. Vault: fecho do modo auto (`COMMIT_*.md` gerado, executado e apagado).
- Prova por fase (`references/michi-prova.md`); sem prova possível → prova alternativa e `sem prova` registado na folha.
- Falha irrecuperável (gate vermelho após 2 tentativas): registar bloqueio na folha, passar à folha seguinte independente; nunca parar à espera do user.

## Fase E - Relatório final
Quando não há folhas elegíveis: relatório na mãe (`## Relatório one-shot`): folhas feitas/cortadas/bloqueadas, horas gastas vs `horas_disponiveis`, lista de «sem prova» e decisões por default, commits locais (hashes). Fechar a mãe só com validação do user.

## Na criação desta skill
Não executar projetos reais; testes só em seco (ver SP `one-shot-sp-gigante` §8).
