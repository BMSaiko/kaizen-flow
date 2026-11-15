# michi — fase 8: Docs

Entre a Review (7) e o PR (9): a documentação acompanha a mudança antes de ela sair. O agente decide; o gate é `sp-fechar.py` (`falta_docs`), que bloqueia o fecho do SP sem a prova (RC 1, SP fica em Doing).

## O que fazer

1. Do diff do SP, listar o que mudou de comportamento visível: scripts, skills, hooks, convenções, comandos, estrutura de pastas.
2. Atualizar o que apontar para isso, só onde existe: `README` do projeto, `MOC` da pasta (playbooks: `knowledge/infra/playbooks/MOC.md`), `CHANGELOG` (`knowledge/infra/reference/CHANGELOG.md` no vault). Nota nova = ficheiro + entrada no MOC.
3. Verificar links novos (`Grep` com `\[\[nome`) e que nenhum ficheiro tocado ficou com referência partida.
4. Registar a prova no SP, numa destas formas:
   - secção `## Docs` não vazia: ficheiros atualizados, uma linha por ficheiro;
   - linha `Docs: <resumo>` dentro de `## Prova de done`;
   - `Docs: skip — <motivo>` em `## Prova de done` (motivo obrigatório: «só código interno», «sem comportamento novo»; `Docs: skip` sozinho não conta).

## Regras

- `--sem-prova "motivo"` **não** dispensa a fase Docs: só a prova de done e o reflect. Quem não tem docs a atualizar escreve `Docs: skip — <motivo>`.
- Aplica-se a todos os SPs fechados depois deste gate; um SP já em Doing fecha com `Docs: skip — anterior à fase Docs` quando não há nada a documentar.
- `skip docs` do michi equivale a `Docs: skip — <motivo>`; o motivo fica registado, nunca omitido.
- Só vault: o repo `kaizen-flow` tem a sua própria fase (SP `kaizenflow-fase-docs`).
