# super-prompt — secções movidas (2026-10-20; condensado 2026-10-31)

## Skills de análise suplementares

Opcionais, antes ou durante o pipeline (o funil funciona sem elas):

- **`five-whys`** — objetivo vago ou problema pouco claro: causa raiz antes do brainstorm.
- **`swot`** — sistema/processo a melhorar: mapear a situação antes do grill.
- **`ooda-loop`** — ambiente volátil: manter o SP alinhado com a realidade.
- **`eisenhower-matrix`** — com o SP guardado, priorizar os Steps (§7) num kanban.

## Templates do grill-me

Lotes de 2-3 perguntas por domínio, com defaults no texto (padrão bake-defaults, Pitfall #8).

- **Código:** «Qual a linguagem/framework? Por defeito: Python + FastAPI (backend), TypeScript + React (frontend). O projeto já tem testes? Por defeito: sim, cobertura ≥80%. Constraint de performance? Por defeito: não, otimizar depois.»
- **Design:** «O output é UI (figma, CSS) ou conceptual (tokens)? Por defeito: tokens + componentes. Há design-system? Por defeito: reutilizar os tokens do projeto. Responsivo/acessibilidade? Por defeito: sim, WCAG AA.»
- **Infra:** «Âmbito: infra existente ou nova? Por defeito: provisionar na existente. Cloud provider? Por defeito: o atual do projeto. Monitorização/alerting? Por defeito: sim, básica (health + logs).»
- **Docs:** «O output é API docs, README ou tutorial? Por defeito: o que o projeto mais precisa. Há docs generator? Por defeito: sim (mkdocs, sphinx…). Audiência? Por defeito: developers internos.»

## Helpers de persistência

Sem código de referência; usar os scripts (`python -I scripts/...`):
`sp-new.py --project P --slug S --priority P2 [--parent X] [--depends-on Y]` (cria `sp/TODO/<slug>-<data>.md`); `sp-validate.py <ficheiro>` (obrigatório antes de entregar); `sp-move.py [--project P] <slug> todo|doing|done`; `sp-list.py`; `sp-organize.py [--project P] [--apply]` (dry-run por defeito).

## Regras de estilo (desta skill)

- Free-text por defeito, não `clarify` multi-escolha; no grill-me juntar 2-3 perguntas do mesmo domínio numa só (Style do michi).
- «1+2+3, quero X» é a resposta: parar de clarificar (michi 2026-09-03).
- Sem enchimento: o SP é colável, o bloat é dívida.
- DR mini cita fontes primárias (caminhos, URLs, strings de erro), não impressões.
- Objetivo muda a meio: recomeçar na Fase 1 (grill-me é o gate de alinhamento); não dobrar em silêncio nas fases seguintes («faz um ajuste» a um plano assinado = respeitar o porquê, michi 2026-09-02).
- Pivot a meio para tarefa meta não relacionada («revê a conversa e atualiza skills», «esquece, faz X», housekeeping): **abortar limpo**, sem inventar SP para a nova tarefa nem saltar às Fases 4/5; reconhecer o pivot numa linha e passar o trabalho. O user volta a invocar `/super-prompt` quando quiser (Pitfall #7).

## Checklist de verificação (depois de guardar)

- [ ] Ficheiro existe no caminho resolvido.
- [ ] 8 secções presentes e não vazias; §3 é exatamente uma frase; §4 só com itens observáveis.
- [ ] §5 nomeia pelo menos um «must keep» e um «must avoid»; §8 nomeia um único sinal concreto.
- [ ] DR mini (se aplicável) cita pelo menos um caminho ou URL.
- [ ] Caminho impresso ao user com a dica «Reuse».
- [ ] `python -I scripts/sp-validate.py <ficheiro>` devolve ok (rc=0).
- [ ] Com `--quick`: 8 secções, cada ≤3 linhas.
- [ ] Com template de grill: as perguntas aparecem no Spec ou os defaults ficam anotados.

## Pitfalls

Texto em `references/super-prompt-pitfalls.md` (13 entradas): 1 objetivo vazio · 2 saltar fases · 3 `clarify` multi-escolha sobre factos ditos · 4 secções 4/5/8 incompletas · 5 caminho errado · 6 auto-executar o SP na mesma sessão · 7 pivot a meio · 8 grill-me em várias rondas · 9 conteúdo hostil ao shell · 10 forma frágil do `clarify` · 11 time-out do `clarify` · 12 âncoras de patch assumidas · 13 DR mini só com infra viva.
