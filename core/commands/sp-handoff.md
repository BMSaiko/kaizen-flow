---
description: Registar o progresso no SP atual (Doing), imprimir o /michi pronto a copiar e, se o user quiser, fazer /clear e continuar o michi neste painel do WezTerm
---
Passos, por esta ordem (português europeu):

1. `python -I scripts/sp-handoff.py --resolve $ARGUMENTS` (`$ARGUMENTS` = slug opcional). Devolve o caminho absoluto do SP em Doing (se o slug for de um programa, o filho em Doing). Se falhar por haver vários Doing, usar AskUserQuestion com os slugs listados e repetir com o escolhido.
2. `python -I scripts/sp-estado.py <caminho>` para ver passos, gates e ficheiros alterados numa só leitura (base de **Feito/Por fazer/Ficheiros tocados**, sem reler SP nem git). Escrever o progresso desta sessão num ficheiro temporário (scratchpad), só o corpo, sem título, com: **Feito**, **Por fazer**, **Decisões**, **Ficheiros tocados**, **Próximo passo**. Só o delta, ≤25 linhas, sem copiar secções do SP (o script recusa; apontar para o SP). Curto e factual, a partir da conversa.
3. `python -I scripts/sp-handoff.py --write <caminho> --file <progresso.md>` (acrescenta ou substitui `## Progresso (sessão <data>)` e atualiza `updated`). Se o SP tem `parent:`, atualiza também o `state` desse filho no SP-mãe e imprime o próximo filho elegível: dizer-o ao user. Se imprimir `programa completo: <mãe>`, fazer AskUserQuestion sim/não "Programa completo, fechar o mãe?"; só com "sim" correr o comando impresso (`sp-move.py --project <P> <mãe> done`). Para fechar o filho e abrir o próximo: `sp-move.py <filho> done --next` (só com ordem do user).
4. Imprimir sempre este bloco, com o caminho absoluto do passo 1:

   ```
   /michi <caminho absoluto do SP>
   ```

5. **Modo automático** (acionado pelo aviso `[context-guard]`): saltar a pergunta; correr `python -I scripts/sp-handoff.py --launch <caminho> --auto` (recusa SP fora de Doing) e terminar o turno como abaixo. Modo manual: AskUserQuestion sim/não: "Continuar o michi numa sessão nova neste painel (/clear + /michi)?". Se sim: `python -I scripts/sp-handoff.py --launch <caminho>` e **terminar o turno logo a seguir, sem mais chamadas a ferramentas**: em segundo plano, passados ~5 s, o script escreve `/clear` e depois `/michi <caminho>` no painel do WezTerm onde o Claude Code já corre (`$WEZTERM_PANE`). Se não: não fazer mais nada.

A sessão nova arranca com `/michi`, que renomeia a tab (`scripts/tab-title.py`). Não abre janelas novas. Nunca mover o SP de pasta nem mudar o `status` (para isso, `scripts/sp-move.py`), nunca editar as secções 1-8 do SP, nunca lançar sem o "sim" do user (exceto no modo automático), nunca `git commit`.
