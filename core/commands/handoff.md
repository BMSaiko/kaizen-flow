---
description: Passar uma conversa livre (sem SP) para uma sessão nova: escreve um handoff efémero no vault, faz /clear e a sessão nova lê-o e apaga-o
version: 1.1.0
---
Para conversas sem SP (para um SP, usar `/sp-handoff`). Passos, por esta ordem (português europeu). Núcleo comum (corpo, `--launch`, modo automático): `knowledge/infra/reference/handoff-launch.md`.

1. Escrever o corpo conforme o núcleo comum (campos: Estado, Último passo, Próximo passo, Ficheiros tocados, Gates por correr, Decisões). `$ARGUMENTS` = nome curto opcional da conversa (slug).
2. `python -I scripts/sb.py ctx handoff --write --slug <slug> --file <corpo.md>`. Imprime o caminho `knowledge/projects/kaizen/handoffs/<data>-<HHMM>-<slug>.md` (limpa também `handoffs/*.md` com mais de 7 dias).
3. Imprimir sempre este bloco, com o caminho absoluto do passo 2:

   ```
   Continua a conversa anterior: corre `python -I scripts/handoff.py --consume "<caminho>"` e segue o Próximo passo.
   ```

4. Lançar: núcleo comum com `<script>` = `python -I scripts/handoff.py` e `<alvo>` = o caminho. O script escreve `/clear` e depois o prompt acima.

A sessão nova corre `handoff.py --consume <caminho>`, que imprime o handoff e só depois o apaga, e a seguir `python -I scripts/tab-title.py <slug>` (slug do ficheiro, sem data/hora). Nunca apagar o ficheiro à mão antes disso; o ficheiro é efémero: não o incluir em commits.
