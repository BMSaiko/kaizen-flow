# VISION.md: entrada da factory

Um objetivo de alto nível por projeto-alvo, validável por máquina. O humano escreve-o uma vez; a factory decompõe-o em SPs (`kaizenflow-decompor`).

## Comandos
- `kaizen vision init <projeto> [--dir D] [--force]`: cria `<projeto>/VISION.md` com `TBD` em tudo (nunca sobrescreve sem `--force`).
- `kaizen vision validate <ficheiro>`: rc 0 só se tudo preenchido; rc 1 lista o que falta.
- `kaizen vision resumo <ficheiro>`: resumo de um ecrã (só de ficheiros válidos).

## Formato
Frontmatter: `projeto`, `ui` (`sim`|`nao`), `stack`, `design_system` (caminho do `DESIGN.md`; obrigatório com `ui: sim`, ver `kaizen ds init`), `orcamento` (com números: teto por SP e por dia).
Secções fixas: Goal, Users, Success criteria, Constraints, Non-goals, Milestones.

## Critérios de sucesso
Lista `- [ ] ...`. Cada critério tem um comando em `código` (ex.: `npm test`) ou começa por «Observação:» com o que se observa. Critério vago («ficar bonito») é rejeitado.

## Placeholders
`TBD`, `TODO`, `(preencher)` e `<preencher>` contam como vazio.
