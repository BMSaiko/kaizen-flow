# super-prompt: secções de apoio

## Skills de análise suplementares

Opcionais, antes ou durante o pipeline (o funil funciona sem elas):

- **`swot`**: sistema ou processo a melhorar: mapear a situação antes do grill.

## Templates do grill-me

Lotes de 2-3 perguntas por domínio, com o default no texto (pitfall 8).

- **Código:** «Qual a linguagem/framework? Por defeito: Python + FastAPI (backend), TypeScript + React (frontend). O projeto já tem testes? Por defeito: sim, cobertura ≥80%. Constraint de performance? Por defeito: não, otimizar depois.»
- **Design:** «O output é UI (figma, CSS) ou conceptual (tokens)? Por defeito: tokens + componentes. Há design-system? Por defeito: reutilizar os tokens do projeto. Responsivo/acessibilidade? Por defeito: sim, WCAG AA.»
- **Infra:** «Âmbito: infra existente ou nova? Por defeito: provisionar na existente. Cloud provider? Por defeito: o atual do projeto. Monitorização/alerting? Por defeito: sim, básica (health + logs).»
- **Docs:** «O output é API docs, README ou tutorial? Por defeito: o que o projeto mais precisa. Há docs generator? Por defeito: sim (mkdocs, sphinx…). Audiência? Por defeito: developers internos.»

## Helpers de persistência

Sem código de referência; usar os scripts (`python -I scripts/...`):
`sp-new.py --project P --slug S --priority P2 [--parent X] [--depends-on Y]` (cria `sp/TODO/<projeto>-<slug>-<data>.md`; `--slug`/`--parent`/`--depends-on` aceitam o nome curto e completam projeto e data); `sp-validate.py <ficheiro>` (antes de entregar); `sp-move.py [--project P] <slug> todo|doing|done`; `sp-list.py`; `sp-organize.py [--project P] [--apply]` (dry-run por defeito).

## Regras de estilo (desta skill)

- Perguntas: `michi-style.md` §1 (aberta por defeito; uma lista com diretiva é a resposta).
- Sem enchimento: o SP é colável, o bloat é dívida.
- DR mini cita fontes primárias (caminhos, URLs, strings de erro), não impressões.
- Objetivo muda a meio: recomeçar na Fase 1, porque o grill-me é o gate de alinhamento.
- Pivot para outra tarefa: pitfall 7.

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

`references/super-prompt-pitfalls.md` (13 entradas).
