# michi: detalhe das fases 1, 3 e 5

Ler a fase em que se está a entrar.

## Fase 1: Grill

1. `/grill-me <projeto> + ideia`: alinhar o que se constrói, porquê e a forma geral, até os dois lados concordarem; o resto do ciclo assenta nisto.
   - **Super Prompt de 8 secções como input:** grill e DR já estão feitos; começar no DP (ou na DA com «go to DA»). As 8 secções são contrato: não voltar a perguntar factos das secções 2-5; se for preciso, o SP estava incompleto e o user deve sabê-lo.
   - **Ordem:** o DR corre antes do grill por defeito, para as perguntas partirem do que o projeto tem. `/michi skip dr` ou `/michi grill` dá a ordem antiga; sem DR, o grill pode pedir um DR mínimo (um ficheiro lido ou um símbolo mapeado por área tocada).

## Fase 3: DP (TDD)

3. `/dp <objetivo da fase 1 + achados da fase 2>`: assunções, 3-7 fases (o quê, âmbito, done-when), riscos e fora de âmbito, até ao sign-off. Cada fase é um ciclo TDD em forma de plano:
   - **Seams:** as interfaces públicas que a fase testa, confirmadas com o user antes de escrever a fase.
   - **Red:** o teste que falha e prova a lacuna; comportamento, não implementação; valor esperado de um literal ou da spec.
   - **Green:** o código mínimo que o faz passar (YAGNI); mocks só nas fronteiras do sistema (APIs externas, tempo, FS), nunca nas próprias classes.
   - **Tautologia:** o teste tem de poder falhar por uma razão visível ao user; senão, reescrever.
   - **Tabela de auditoria:** `phase | existe hoje | muda depois | redundant?` por fase; `redundant=yes` sai do plano, porque duplica estado que já vive noutro sítio.
   - **Pattern-fit:** antes do sign-off, nomear o padrão (`references/michi-patterns.md`) com a pergunta «que padrão encaixa e porquê?».
   - **Refactor** não faz parte do ciclo: vive no review.

## Fase 5: Gates e prova de done

5. **Gates.** Correr os comandos de verificação do projeto (build, testes, lint, typecheck, e2e); cada comando e o seu RC vão para o Report. Gate falhado: corrigir a causa e repetir todos, sem `|| true`.
   **Vault/scripts (só se `scripts/test-fast.py` existir):** `python -I scripts/test-fast.py` (só o que o diff tocou) em cada fase; `... full` (suite completa) no fecho.
   **Gate `auditar`** (após DA, antes do Report): `/auditar rapido|normal` sobre o diff da DA; achados viram SPs (`--criar-sps`) executados com prova; só passa sem confirmados abertos ou com decisão do {{userName}}. `skip auditar` salta-o (modo auto: corre sempre, sem perguntar).
   **Gate `review`** (após `auditar`, antes do PR): revisor independente (`sp-revisor.py`) e ciclo corrigir → reauditar (`auditar.py ciclo`); APROVADO segue para PR, ESCALAR (3 iterações) pede decisão ao {{userName}}. `skip review` salta-o.
   **Fase `ship`** (após ciclo `/auditar` APROVADO): `/kf-ship` leva o ramo ao merge (contrato de testes, PR via `/pr-fase` respeitando `pr:`, vigia CI, merge só com verde, método e `merge:` a permitir; rc 10 = pedir merge ao {{userName}}); sem atribuição a agentes. `pr: nunca` = parar antes do PR. O ship nativo do harness só o {{userName}} o escreve.
   **Prova de done (antes de `sp-move.py ... done` e do `COMMIT_*.md`).** Agir como o cliente final da feature: executar o caminho real do
   utilizador (app/CLI/comando, skill `run` se aplicável; em docs/vault,
   ler o resultado como leitor: links resolvem, instruções reproduzem; em
   regras de agente, um cenário que a regra deve mudar). Não repetir
   testes/lint de `da`. Registar comando + output/caminho numa secção
   extra `## Prova de done` no SP (fora das 8; `sp-validate.py` tolera).
   Se a prova falhar, o SP não passa a Done: reportar a falha como é.

   **SP com `gates:` no frontmatter:** correr `python -I scripts/sp-gates.py <SP>` em vez de inferir os comandos; rc 0 = verde, 1 = gate vermelho (corrigir a causa e repetir), 2 = gate inválido/proibido (nada corre). O resumo (comando, rc, duração, últimas linhas) vai para o Report. Vermelho impede `sp-move.py ... done`. Incremental: um gate com `inputs:` (globs relativos a `cwd`, vírgulas) é saltado («cache») se comando e ficheiros não mudaram desde a última corrida verde (`.sp-gates-cache.json`, ignorado pelo git); gate sem `inputs:` corre sempre; `--full` ignora a cache, e `sp-fechar.py` corre sempre tudo. `prova:` (comando ou critério) é a prova de done. Sem `gates:`, mantém-se o comportamento acima.
   Consolida e referencia as provas por fase (`## Prova`, `references/michi-prova.md`).
   **E2E de fecho de árvore** (só quando este SP fecha uma árvore mãe+filhos+netos; não a cada filho): (a) mecânica, `python -I scripts/sp-list.py --tree-closed <slug>` (rc≠0 = filho/neto por fechar, status≠pasta, dependência por cumprir ou sem `COMMIT_*.md`); (b) código entregue em `code\<projeto>`: build/typecheck/testes e um cenário e2e dos casos de uso do SP-mãe. Resultado com output no Report; falha impede propor o commit e abre correção. Detalhe: `workflow-sp-michi.md`.
