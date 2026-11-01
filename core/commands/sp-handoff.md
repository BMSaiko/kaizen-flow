---
description: Registar o progresso no SP atual (Doing), imprimir o /michi pronto a copiar e, se o user quiser, fazer /clear e continuar o michi neste painel do WezTerm
version: 1.1.0
---
Passos, por esta ordem (português europeu). Núcleo comum (corpo, `--launch`, modo automático): `knowledge/infra/reference/handoff-launch.md`.

1. `python -I scripts/sp-handoff.py --resolve $ARGUMENTS` (`$ARGUMENTS` = slug opcional). Devolve o caminho absoluto do SP em Doing (se o slug for de um programa, o filho em Doing). Se falhar por haver vários Doing, usar AskUserQuestion com os slugs listados e repetir com o escolhido.
2. `python -I scripts/sp-estado.py <caminho>` (passos, gates e ficheiros alterados numa só leitura: base de **Último passo/Gates por correr/Ficheiros tocados**, sem reler SP nem git). Escrever o corpo conforme o núcleo comum (campos: Estado, Último passo, Próximo passo, Ficheiros tocados, Gates por correr, Decisões).
3. `python -I scripts/sp-handoff.py --write <caminho> --file <progresso.md>` (acrescenta ou substitui `## Progresso (sessão <data>)` e atualiza `updated`). Se o SP tem `parent:`, atualiza também o `state` desse filho no SP-mãe e imprime o próximo filho elegível: dizer-o ao user. Se imprimir `programa completo: <mãe>`, fazer AskUserQuestion sim/não "Programa completo, fechar o mãe?"; só com "sim" correr o comando impresso (`sp-move.py --project <P> <mãe> done`). Para fechar o filho e abrir o próximo: `sp-move.py <filho> done --next` (só com ordem do user).
4. Imprimir sempre este bloco, com o caminho absoluto do passo 1:

   ```
   /michi <caminho absoluto do SP>
   ```

5. Lançar: núcleo comum com `<script>` = `python -I scripts/sp-handoff.py` e `<alvo>` = o caminho; `--auto` recusa SP fora de Doing. O script escreve `/clear` e depois `/michi <caminho>`.

A sessão nova arranca com `/michi`, que renomeia a tab (`scripts/tab-title.py`). Nunca mover o SP de pasta nem mudar o `status` (para isso, `scripts/sp-move.py`), nunca editar as secções 1-8 do SP.
