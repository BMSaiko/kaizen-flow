# Michi: pitfalls

Regras gerais tiradas de incidentes reais. O relato de cada um (projeto, data, números) está no arquivo de incidentes do vault (`knowledge/infra/reference/michi-incidentes.md`), fora do pacote. A numeração é estável: `reflect-promocao.py` acrescenta a partir da última.

## 1. Tratar `/michi` como one-shot

- O user pode querer parar em qualquer fase; ler o pedido antes de encadear a seguinte.

## 2. Voltar a perguntar um facto já dado

- Cada pergunta sobre algo já dito gasta um turno e mostra que o contexto não foi lido.

## 3. Skip grill com âmbito vago, e gates

- Skip grill dispensa a conversa, não a rede: com âmbito vago, a primeira pergunta é o sintoma real (erro colado), depois um levantamento do que existe e uma única decisão de âmbito (`michi-skip-grill-play.md`).
- «Reescrever tudo»: extrair antes os invariantes do código atual e perguntar o que morre, fica e muda, porque a reescrita perde bugs já corrigidos.
- N cópias idênticas: extrair um módulo e chamadas finas primeiro, simplificar depois.
- Problemas de EOL: começar por `git config --show-origin --get core.autocrlf`, porque o valor efetivo pode vir do nível system.
- Nunca matar processos por nome durante gates (`taskkill /IM`): pode levar o servidor ou o IDE do user; matar por PID.
- Gate de build no repo de dev: escrever a saída num diretório à parte, para não pisar o servidor de dev.
- «Gates passed» só com o comando e o resultado; um gate que só faz parse não prova comportamento em runtime: dar uma prova em execução ou dizer que falta.
- Métricas ruidosas (Lighthouse): correr 3 vezes e decidir pela mediana, sem repetir até passar.
- Objetivos não relacionados no mesmo run: propor dividir.

## 4. Interrupção a meio da DA

- Sessão morta deixa trabalho na árvore sem commit: ver `git status` e `git diff --stat` antes de recomeçar; se o grosso está feito, recuperar e terminar em vez de apagar. Árvore e stash com trabalho são uma só decisão de recuperação.

## 5. Dividir um ficheiro grande

- Se as famílias de código se sobrepõem, preferir secções com índice num só ficheiro a dividir em muitos.
- Depois de um patch em funções longas, comparar o número de linhas antes e depois: uma descida maior que o delta indica que o patch cruzou âmbito.
- `DA` é um salto para implementar, não uma repetição das fases anteriores.

## 6. Auto-piloto e worktrees

- «Sem perguntas» cobre a execução, não as contradições do SP nem os gates irrecuperáveis: parar, citar as duas cláusulas e propor o desempate.
- Antes de editar numa worktree, confirmar `git rev-parse --show-toplevel` e, depois, que o `git status` mostra o ficheiro; escrever num caminho que o git não segue perde trabalho sem aviso.
- Worktree `prunable`: `git worktree prune` e `git worktree add <path> <ramo>` sem `-b`, nunca `remove --force`, que apaga o trabalho em disco.
- Árvore suja de outro agente: isolar o teu trabalho num ramo antes de mexer em stashes.

## 7. «X não funciona»

- A primeira resposta é uma pergunta pela mensagem de erro, porque o sintoma raramente aponta para o código certo.

## 8. Ciclo desviado por um pedido de ops

- O Reflect continua devido no fim da sessão; uma linha chega se nada surpreendeu.

## 9. Reflect é ponto de paragem

- No modo manual, o Reflect termina com a decisão do user, sem encadear a fase seguinte.

## 10. Cadência de commit por fase

- Com três ou mais fases, decidir no sign-off do plano se há um commit por fase; o commit continua a precisar de confirmação (`michi-modo-auto.md` §Autorizações).

## 11. Clusters de refactor

- Commitar cada módulo com os seus call-sites e testes, porque processos paralelos podem apagar ficheiros untracked; ficheiros em falta no `git status` estão perdidos, não escondidos.

## 14. Pós-processamento do filho

- Trabalho depois de um processo filho sair corre destacado e grava o estado em disco, para sobreviver a um reinício do orquestrador.

## 15. Ajuste a um plano aprovado

- Repetir o porquê do ajuste, propor a reordenação que o respeita e esperar confirmação; não o dobrar em silêncio na fase corrente.

## 16. Lista de correções depois da DA

- É um delta, não um recomeço: ler a lista toda, separar bugs de features e fazer um só passe com testes e gates.

## 17. Lista numerada é contrato

- Cada item é um requisito: responder primeiro com a tabela item, classificação e alteração, sem fundir itens nem alargar o âmbito.

## 20. Estado antes da DA

- Os factos do SP sobre ramo e árvore envelhecem: ver `git status`, ramo e último commit antes de editar e perguntar se divergem.

## 21. Checkout com alterações

- Ver §6.

## 22. Junctions e symlinks em worktrees

- Não passam do pai para a worktree; caminhos gitignored verificam-se com ferramentas de filesystem, não com git.

## 23. Fast-forward de uma worktree

- Com a worktree à frente e `origin/<ramo>` igual à base (depois de `git fetch`), basta mover o ref e fazer push; se divergem, merge normal ou PR.

## 25. Worktree para o ramo de dev

- `git fetch` primeiro, merge do ramo remoto dentro da worktree, gates de novo lá, só depois merge no ramo de dev.

## 26. Fecho com push e merge

- `merge --ff-only` quando a base não andou; só com autorização. No Git Bash não passar caminhos `/tmp` ao Python do Windows.

## 27. Python em modo texto no Windows

- `read`/`write` em texto convertem EOL: usar `newline=""` ou `Edit`, e confirmar com `git ls-files --eol`.

## 28. Skill «duplicada»

- Ler o corpo das duas e procurar quem carrega quem antes de remover.

## 29. MCP numa worktree nova

- `claude mcp list` não prova a ligação; usar `claude -p --mcp-config` e ler o estado do servidor.

## 30. Gates sobre repo externo

- `sp-gates.py` corre no vault: cada `cmd` sobre outro repo começa com `cd <repo> &&`.

## 31. Código com escapes

- Editar código com `Edit`/`Write`; heredoc Python só para dados sem escapes.

## 32. Comandos para o user correr com `!`

- O `!` corre em bash: caminhos com barras normais.

## 33. Endurecer um recurso

- Listar todos os pontos de entrada que o leem antes de corrigir o primeiro.

## 34. Peça nova no pacote K

- Acrescentá-la a `SCRIPT_NAMES` e à fixture de `tests/sync.test.js`, e confirmar com o `git status` do repo limpo.

## 35. Audit do kaizen-flow

- Correr `node bin/kaizen.js audit .` em cada fase que toca testes ou docs, não só no fim.

## 36. Testes do pacote K

- Chamar `main(argv)` em-processo, porque a cobertura não conta subprocessos.
