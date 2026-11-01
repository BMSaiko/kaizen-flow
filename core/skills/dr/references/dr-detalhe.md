---
name: dr-detalhe
description: Detalhe do dr - fases, template do Brief, erros, red flags, adaptação Claude Code
---
# DR — detalhe (movido do SKILL.md v2.1.0)

Fase de pesquisa estruturada que alimenta o Deep-Planning. Evidência antes de assunções.

## Visão geral

DR é a **Fase 0**: corre antes do «Analyze» do DP. Pesquisar antes de analisar, analisar antes de desenhar, desenhar antes de codar. **Lei de ferro: sem planeamento sem pesquisa**; sem o Research Brief completo o Analyze do DP não arranca.

| Cenário | Aplicar? |
|---|---|
| Início de Deep-Planning | **OBRIGATÓRIO** |
| Tarefa COMPLEX com contexto desconhecido | **OBRIGATÓRIO** |
| User diz «research this first» | **OBRIGATÓRIO** |
| Multi-passo com contexto incompleto | Recomendado |
| Tarefa TRIVIAL ou contexto já conhecido | Saltar |
| Pergunta rápida / one-liner | Nunca |

Session Start dá o contexto da **sessão** (inbox, erros, nota diária; horizontal); DR dá o do **projeto/tarefa** (vault + código + padrões; vertical); Brainstorming explora o design depois do DR.

## Scope Gate (Fase 0.5)

Antes do DR completo, confirmar que a tarefa o justifica: (1) TRIVIAL ou contexto conhecido → **saltar DR**; (2) pergunta respondível com uma `sb_search` → **só essa**; (3) várias subsistemas ou dependências desconhecidas → **DR completo**; (4) dúvida → só a Fase 1, e se o alvo for claro e estreito, reduzir a delta. Registar no Brief em `## Executive Summary` como `Scope Gate: Full/Delta/Skipped`.

## Fases

Sequencial Fase 1 → Fase 2; as Fases 2-5 são independentes (em paralelo se possível); a Fase 6 consolida. Cada fase: entrada → ferramentas → saída → verificar. Orçamento: F1 2 min, F2 5, F3 5, F4 3, F5 3, F6 3 (~21 min; `/dr <tópico> --deep` alarga).

1. **Identificar o alvo.** Projeto, âmbito, entidades-chave. Fast-path: trabalhou-se neste projeto nas últimas 24 h (`sb_list` de sessões recentes) → **Delta-Only** (commits, ficheiros e notas novas), senão **Full**. Ferramentas: `sb_resolve` (wikilink do projeto → caminho de código), `sb_search` (o projeto existe?), `project_detect` (cwd). Saída: declaração do alvo.
2. **Pesquisa no vault.** Ler o MOC do projeto (`knowledge/projects/<projeto>/MOC.md`), pesquisar conteúdo relacionado, verificar saúde dos links, estatísticas do vault. Ferramentas: `sb_read`, `sb_search`, `sb_list`, `sb_resolve`, `maintenance_link_audit` (links partidos), `dashboard_status`. Pré-requisito: vault sincronizado (`sync_daily_notes(dryRun=true)`; se houver mudanças relevantes, `sync_daily_notes()`). Saída: caminho/estado do MOC (found/new/missing), docs relacionados, saúde dos links, stats.
3. **Pesquisa no código.** Estrutura, padrões, commits recentes, TODOs. Ferramentas: `bash` (`ls`, `rg`, `git log`), `win_git` (repos Windows, fallback de caminho), `git_status`. Caminho resolvido dinamicamente via `sb_resolve` a partir do MOC (**nunca hardcoded**; fallback `sb_search`). Verificações: `ls` de `src/ lib/ config/ docs/`; `git log --oneline -10`; `rg "TODO|FIXME|HACK|XXX"`; `git status --short`. Sem git: «not checked» nos Research Gaps; caminho não resolvido: «path unresolved» e saltar para a Fase 6.
4. **Padrões de erro.** Procurar no MISTAKE_LOG (`sb_search` em escopo de projeto e `knowledge/infra/`; fallback `find`) padrões do domínio, stack e tipo de tarefa, filtrando por nome do projeto (substring ≥3 chars), stack («Next.js», «Supabase», «Python») e tipo de tarefa («deployment», «RLS», «migration»). Saída: padrões com passos de prevenção, ou `_None relevant_`; MISTAKE_LOG ausente: `_MISTAKE_LOG not found_` nos Gaps. Nunca bloqueia o DR.
5. **Contexto temporal.** Daily notes de hoje e ontem e sessões dos últimos 3 dias: feito, em curso, bloqueado. Pré-requisito: `sync_daily_notes(dryRun=true)` e, se houver pendentes, `sync_daily_notes()`. Ferramentas: `sync_sessions`, `sb_read` (`knowledge/YYYY-MM-DD.md`), `sb_list`. Extrair itens de hoje, concluído/em curso de ontem, bloqueios e decisões pendentes, flags (WIP, abandonado, escalado).
6. **Compilar o Brief.** Escrever em `knowledge/projects/<projeto>/research/YYYY-MM-DD-<tópico>-brief.md` com todas as secções; fases saltadas ou com erro preenchem a secção com a lacuna/razão.

## Template do Research Brief

```markdown
# Research Brief — {Topic}

> **Date:** YYYY-MM-DD
> **Project:** {project}
> **Scope:** {scope}
> **Fast-Path Applied:** {Full/Delta/Skipped}
> **Scope Gate:** {Full/Delta/Skipped}
> **Orçamento:** {N leituras, M greps; parou porque…}
> **Duration:** {total minutes}

## Síntese
{≤25 linhas: onde a mudança cai, o que respeitar, o que é arriscado; cada afirmação com fonte `ficheiro:linha`; validar com `python -I scripts/dr-check.py <brief>`}

## Executive Summary
{2-3 frases: o que se pesquisou, achados, confiança global}

## Vault Findings
- **MOC:** {path} — {found/new/missing}
- **Related Docs:** {list}
- **Link Health:** {healthy / N broken links}
- **Vault Stats:** {files, size, active skills}

## Codebase State
- **Location:** {abs path}
- **Structure:** {key dirs}
- **Recent Changes:** {last N commits or "no git"}
- **Open TODOs:** {count + key items}

## Mistake Patterns
- **[{category}]** {pattern} → Prevention: {step}   (ou _None relevant_ / _MISTAKE_LOG not found_)

## Temporal Context
- **Today:** · **Yesterday:** · **Blockers:**

## Open Questions
1. {question}

## Research Gaps
- {o que não se determinou; fases com erro ou saltadas, com razão}

## Confidence Assessment
| Section | Confidence | Basis |
|---|---|---|
| Vault / Codebase / Mistakes / Temporal | high/medium/low | {razão} |
| **Overall** | **high/medium/low** | |

## Tool Audit
| Phase | Tools Used | Status |
|---|---|---|
| Phase 2..5 | {tools} | ✓/⚠/✗ |
```

**Confiança:** *High* = ≥3 fontes independentes concordam ou a fonte primária bate diretamente; *Medium* = 1-2 fontes ou uma única autoritativa; *Low* = sem fonte, evidência contraditória ou fase com erro.

## Integrações

`grounded-citations` (Fase 2 precisa de afirmações web verificáveis); `link-audit` (Fase 2 encontra wikilinks partidos, após `sb_resolve`); `sb-sync` (`sync_daily_notes` antes de ler notas temporais); `project-setup` (Fase 1 não acha o projeto no vault: sinalizar «project not initialized»).

## Handoff DR → DP

1. O Brief fica gravado. 2. O «Analyze» do DP **lê o Brief**, não repete a pesquisa. 3. O plano cita-o: `> Research: knowledge/projects/<projeto>/research/YYYY-MM-DD-<tópico>-brief.md`. 4. Secções de baixa confiança viram riscos no plano. 5. O Scope Gate (Full/Delta/Skipped) ajusta a profundidade do plano. 6. Cada Research Gap é endereçado ou aceite explicitamente como risco.

## Erros

| Falha | Ação |
|---|---|
| Fase 1 | Reportar; saltar DR; escalar ao user |
| Fase 2 (vault) | Continuar F3-5; vault «unverified» nos Gaps |
| Fase 3 (código) | Continuar; «not checked» nos Gaps |
| Fase 4 (erros) | Continuar; `_MISTAKE_LOG not found_` nos Gaps |
| Fase 5 (temporal) | Continuar; «temporal context unavailable» |
| Fase 6 (escrita) | Brief para o terminal; avisar o user |

**Nunca abortar o DR inteiro por falha de uma fase: registar a lacuna e continuar.**

## Red flags

Saltar fases «para poupar tempo» (pesquisa rasa = planos maus); viés de confirmação; pesquisar sem escrever o Brief («não documentado = não aconteceu»); ignorar secções de baixa confiança (são riscos); re-pesquisar no DP o que o DR já cobriu; caminhos hardcoded (resolver com `sb_resolve`); saltar o Scope Gate (over-research de tarefas triviais); correr F2-5 em sequência quando são independentes.

## Observabilidade

- [ ] Scope Gate e fast-path documentados
- [ ] Brief com todas as secções, Tool Audit completo e confiança com base objetiva por secção
- [ ] MISTAKE_LOG verificado (padrões ou «not found»); notas temporais sincronizadas antes de ler
- [ ] Brief referenciado no plano DP
- [ ] Nenhuma fase saltada sem justificação; Research Gaps preenchido com as falhas

## Adaptação Claude Code (the agent)

Ferramentas Pi → Claude Code. Sem sub-agentes (sequencial; ver CLAUDE.md).

| Pi | Claude Code |
|----|-------------|
| `sb_search` | `Grep` (conteúdo) / `Glob` (nomes) |
| `sb_read` | `Read` (usar `offset`/`limit`) |
| `sb_list` | `Glob` (ordenar por data) |
| `sb_resolve` | `Glob` por `**/<nome>.md` (wikilink → caminho) |
| `bash` + `find`/`grep` | Proibido; usar `Glob`/`Grep` |
| `subagents` / paralelo | Chamadas de ferramentas paralelas na mesma resposta; nunca `Agent` salvo pedido do user |
| `sync_daily_notes` | Ler/editar a daily note à mão |
