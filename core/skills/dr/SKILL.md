---
name: dr
description: Recolhe contexto do vault, do código e dos erros passados num Research Brief com fontes. Usar antes do DP ou numa tarefa complexa com contexto incompleto (fase 2 do michi).
version: 3.0.0
---
# Deep-Research (DR)

Fase 0 do DP: evidência antes de assunções. Planear sem pesquisa repete erros já pagos; o Analyze do DP lê o Brief, não repete a pesquisa. Detalhe (fases, template, erros, red flags, mapa de ferramentas): `references/dr-detalhe.md`.

## Quando

| Cenário | Aplicar? |
|---|---|
| Início de DP, tarefa COMPLEX com contexto desconhecido, «research this first» | Sim |
| Multi-passo com contexto incompleto | Recomendado |
| TRIVIAL, contexto já conhecido, pergunta rápida | Não |

## Scope Gate (dono único; o `dp` só o cita)

1. TRIVIAL ou contexto conhecido → **Skipped**.
2. Respondível com uma pesquisa → só essa (**Delta**).
3. Vários subsistemas ou dependências desconhecidas → **Full**.
4. Dúvida → Fase 1 e, se o alvo for estreito, Delta. Trabalho nas últimas 24 h no projeto → Delta (só commits e notas novas).

## Fases

1. **Alvo:** projeto, âmbito, entidades-chave (MOC do projeto → caminho do código, nunca hardcoded).
2. **Vault:** MOC, docs relacionados, links partidos. `Grep`/`Glob`.
3. **Código:** estrutura, `git log --oneline -10`, TODO/FIXME, `git status --short`.
4. **Erros:** padrões no MISTAKE_LOG por projeto, stack e tipo de tarefa (nunca bloqueia).
5. **Temporal:** daily notes de hoje e ontem, sessões dos últimos 3 dias (feito, em curso, bloqueios).
6. **Brief:** `knowledge/projects/<projeto>/dr/YYYY-MM-DD-<tópico>-brief.md`.

Fases 2-5 são independentes: chamadas paralelas na mesma resposta. Falha de uma fase = registar em Lacunas e continuar; o DR não aborta por uma fase.

## Paragem

Parar quando (a) as 3 perguntas da Síntese têm resposta com fonte ou (b) duas pesquisas seguidas não trazem nada novo. Salvaguarda: com Delta acima de ~15 leituras ou Full acima de ~50, parar e passar o resto para Lacunas, porque o âmbito provavelmente está mal escolhido. Ler a parte relevante (`offset`/`limit`) quando o ficheiro é grande; pesquisas independentes vão em paralelo. Registar no Brief `Orçamento: N leituras, M greps; parou porque…` (campo lido pelo `dr-check.py`).

## Saída (fixa)

Brief com cabeçalho `Scope Gate` + `Orçamento`, secção **`## Síntese` ≤25 linhas** e cada afirmação com fonte `ficheiro:linha`:
onde a mudança cai · o que tem de respeitar · o que é arriscado.
Depois: Padrões de erro, Contexto temporal, Perguntas abertas, Lacunas, Confiança (high ≥3 fontes concordam; medium 1-2; low sem fonte ou fase com erro) e Tool Audit. Template completo em `references/dr-detalhe.md`.

Validar: `python -I scripts/dr-check.py <brief>` (rc 0). Sem Brief gravado, «não documentado = não aconteceu».

## Handoff DR → DP

O plano cita `> Research: <caminho do Brief>`; confiança baixa vira risco; cada Lacuna é endereçada ou aceite como risco. Super Prompt de 8 secções como input: saltar fases 1-2 do michi e não repetir factos das secções 2-5.
