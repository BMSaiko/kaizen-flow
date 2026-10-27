---
description: Passar uma conversa livre (sem SP) para uma sessão nova: escreve um handoff efémero no vault, faz /clear e a sessão nova lê-o e apaga-o
---
Para conversas sem SP (para um SP, usar `/sp-handoff`). Passos, por esta ordem (português europeu):

1. Escrever o estado desta conversa num ficheiro temporário (scratchpad), só o corpo, sem título, com: **Feito**, **Por fazer**, **Decisões**, **Ficheiros tocados**, **Próximo passo**. Curto e factual, a partir da conversa. `$ARGUMENTS` = nome curto opcional da conversa (slug).
2. Corpo só com o delta, ≤25 linhas (o script recusa mais). `python -I scripts/sb.py ctx handoff --write --slug <slug> --file <corpo.md>`. Imprime o caminho `knowledge/projects/kaizen/handoffs/<data>-<HHMM>-<slug>.md` (limpa também `handoffs/*.md` com mais de 7 dias).
3. Imprimir sempre este bloco, com o caminho absoluto do passo 2:

   ```
   Continua a conversa anterior: corre `python -I scripts/handoff.py --consume "<caminho>"` e segue o Próximo passo.
   ```

4. **Modo automático** (acionado pelo aviso `[context-guard]`): saltar a pergunta; correr `python -I scripts/handoff.py --launch <caminho> --auto` e terminar o turno como abaixo. Modo manual: AskUserQuestion sim/não: "Continuar numa sessão nova neste painel (/clear + ler o handoff)?". Se sim: `python -I scripts/handoff.py --launch <caminho>` e **terminar o turno logo a seguir, sem mais chamadas a ferramentas**: em segundo plano, passados ~5 s, o script escreve `/clear` e depois o prompt acima no painel do WezTerm onde o Claude Code já corre (`$WEZTERM_PANE`). Se não: não fazer mais nada.

A sessão nova corre `handoff.py --consume <caminho>`, que imprime o handoff e só depois o apaga, e a seguir `python -I scripts/tab-title.py <slug>` (slug do ficheiro, sem data/hora; renomeia a tab e imprime `/rename <slug>`). Nunca apagar o ficheiro à mão antes disso, não abre janelas novas, nunca `git commit` (o ficheiro é efémero: não o incluir em commits).
