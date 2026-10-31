# Michi — pitfalls

Movido de `SKILL.md` (## Pitfalls); condensado em 2026-10-31 (regras todas mantidas, narrativa e duplicados cortados), 26 entradas.

## 1. Tratar `/michi` como one-shot

- O user pode querer parar em qualquer fase. Ler a sala.

## 2. Voltar a perguntar um facto já dado

- «dev branch? disseste dev» gasta um turno. Multi-choice `clarify` sobre factos já ditos é o desperdício canónico (ver Style).

## 3. `/michi skip grill` + instrução vaga e grande, e armadilhas de gates

- Saltar o grill «porque é óbvio»: o plano paga o alinhamento agora ou o retrabalho depois.
- **Skip-grill + âmbito vago** («refactor do backend», «rescrever X por que funciona mal»): skip-grill dispensa a conversa, não a rede de segurança. A 1ª pergunta do DR é 1 free-text sobre o sintoma real («cola o erro / o card / a mensagem»); «não funciona» tem ≥3 significados. Gate mínimo antes de DR/DP: (1) scan de 5 min que nomeia o que existe (`ls`, linhas, símbolos exportados, rotas, testes); (2) tabela de coragem (A=refactor seguro / B=+validação / C=+framework) com 1 linha de risco; (3) **uma** decisão («qual nível, qual âmbito»), não multi-pergunta. Não repetir factos já ditos. Forma: `references/michi-skip-grill-play.md`.
- **EOL/CRLF: a primeira ação é `git config --show-origin --get core.autocrlf`** (e `core.eol`). (1) `false` local + `true` system: o system ganha no checkout, `.gitattributes eol=lf` é no-op, `git checkout HEAD -- f` escreve CRLF; corrigir reescrevendo via Python (`.read_bytes().replace(b'\r\n', b'\n')`) + `git add` + commit (sem admin não há `--system --unset`). (2) `true` local: `git config --local core.autocrlf false`. (3) `input`/ausente: `text=auto` no `.gitattributes`; normalizar, commitar, travar. Gastar 5 min em `-c core.autocrlf=false checkout`, `GIT_CONFIG_NOSYSTEM`, `git rm --cached` não resolve; o `show-origin` custa 0,5 s.
- **Nunca matar em bloco durante gates**: `taskkill /F /IM node.exe /T` mata o dev server/IDE do user. Receita: `tasklist /FI "IMAGENAME eq node.exe"`; se >1 processo, `taskkill /F /PID <pid>` após `wmic process get ProcessId,CommandLine | findstr <padrão>`; por nome só se for certo que só há o teu. Default: estreito (30 s).
- **Gate de build dentro do repo de dev** (`runCIGate`): isolar a saída num dir irmão (`--outDir .ci-gate/<ts>/`, gitignored, limpo no fim), não tocar em `dist/` (o build pisa o dev server). Sem worktree manager novo (YAGNI). Contrato BC: parâmetro opcional `wtDir` (se dado, `vite build` na raiz dele; senão `--outDir` irmão e `rm` best-effort); os chamadores existentes (`w:approve-agent`, `w:approve`) não mudam.
- Misturar objetivos não relacionados num run: sugerir dividir.
- **Skip-grill + «rescrever tudo»** (atlas wrapper, 2026-09-03): perde bugs já pagos (7+ no `atlas-wrapper-python`). Antes do plano, extrair os invariants do código atual (ex.: «Não-objetivos» da skill) e honrá-los. A pergunta pós-DR é «o que MORRE / FICA / MUDA», não «como queres o novo».
- **N cópias idênticas** (string-array/função/template, ex.: 4 spawn sites `python -c`): o DP default é extrair 1 módulo + N chamadas magras (`runCard(opts) -> Promise<{code, mergeResult}>` com heartbeat + auto-merge + log), extrair primeiro e simplificar depois; o ganho de LOC vem dos call-sites. Linha de auditoria: `phase | 4 cópias | 1 helper + 4 chamadas | redundant=no (DRY)`.
- «Gates passed» sem o output do comando: dizer comando e resultado.
- **Gate só de parse não prova runtime/UI** (wezterm, 2026-09-02): `show-keys RC=0`, `lua -p`, `tsc --noEmit` só provam que parseia; bugs em `update-right-status`, `format-tab-title`, OSC, hooks vivem no disparo do evento. Fase 5 precisa de UMA prova em runtime (recarregar, disparar, log/screenshot); se não a consegues correr, dizê-lo no report e parar.
- **esbuild minify e custom properties com hífen interno** (`--space-1`): dá `css-syntax-error` no `vite build`. Usar `--space1` ou largar o alias (YAGNI); reportar o aviso e riscar do DP, sem `eslint-disable`.
- **`npm install --save-dev` com `ETARGET`** em versões que o registry tem: cache velha; `npm cache clean --force` e repetir.
- **«Vite hang aos 240 s»** costuma ser o fim do `npm install` anterior (postinstall) ou um bg process com o lock: fazer `tail -f` do log até `transforming...`; install-tail mostra `added N packages`, esperar ≤60 s.
- **Sondas via shell bloqueadas**: com `vite preview` de pé não usar `curl`/`node -e fetch` (o user bloqueou); correr o gate (`npx lighthouse …`, `npx @axe-core/cli …`), que reporta URL inalcançável.
- **Lighthouse perf ≥ N é ruidoso** (90/95/99 no mesmo código): correr **3×**, reportar os 3 e a mediana; mediana ≥ N = PASS, senão FAIL (variância real, não azar). Correr 3× é o gate, não sonda redundante. Falhas entre corridas costumam ser artefacto de runtime (cache de fontes, perfil Chrome, rede): entregar o que a mediana diz e iterar. Não repetir até passar (p-hacking).

## 4. Interrupção a meio da DA deixa o disco a 80%, git a 0% (atlas polish-A, 2026-09-04)

- Sessão morta a meio (restart, timeout, `/stop`): o trabalho está no working tree, o HEAD igual ao pai; `git status` mostra N ficheiros e 0 commits à frente, e parece «sem trabalho» ou «sujo, recomeçar». Receita: (1) `git status --short` + `git diff --stat`; (2) se ≥80% do plano está lá, escrever um DP v2 «recuperação» por renomeação (`git mv plans/<slug>-DP plans/<slug>-DP-v1`, v2 no caminho canónico com `supersedes: plans/<slug>-DP-v1/DP.md`); (3) gates sobre a árvore recuperada; (4) commit. Anti-padrões: apagar e recomeçar (30 min, pior forma); `git stash` + recomeçar; DP v2 em `<slug>-DP-v2/` (contexto dividido). Se há trabalho parcial na árvore E num stash, é uma só decisão de recuperação; não fazer pop do stash para a árvore (mistura âmbitos de duas sessões), tratar como decisões separadas no mesmo pedido. Perda já feita: `git status` deixou de mostrar os ficheiros esperados; recuperar = refazer.

## 5. Um ficheiro com banners > split em N ficheiros quando as famílias de classes se sobrepõem (atlas polish-A, 2026-09-04)

- O SP pode pedir «split em 8 ficheiros via `@import`», mas com sobreposição forte (`.kmodal-actions`/`.modal`, `.dash-head`/`.kcard`) o bin-by-class dá 100+ fragmentos em 7 ficheiros. Para «split para navegação, não perf»: TOC no topo + 6-9 banners SECTION num só ficheiro (o SP aceita «OR sectioned with banner comments»). Custo do split: 30+ min e risco de ordem da cascata; do banner: +2,5 KB de comentários.
- **`patch` desindenta em closures aninhadas; `tsc --noEmit` não apanha** (atlas-mundo-workflow, 2026-09-05): um bloco no fim de função grande (>200 LOC) ou junto a um `}` de callback interno cai na profundidade errada, o `}` fecha a função errada e a feature nunca corre no caminho feliz (tsc rc=0, HTML em template-string parseia). Antes: imprimir as linhas com a contagem de espaços à volta do ponto e localizar o `}` pela indentação (`references/michi-patch-indent-audit.md`). Depois: `wc -l` antes/depois; se desceu mais que o delta líquido, o patch cruzou âmbito: `git checkout HEAD -- <file>` e refazer. Só a profundidade de chavetas apanha isto (mesma família do Worktree trap).
- **`DA` é um salto, não um re-run**: `/michi DA` depois de `/michi <ideia>` = implementar já com o que há; não repetir grill/DR/DP. Fase específica: `/michi dr` ou `/michi dp`.

## 6. «Sem perguntas, faz todas as fases» é auto-piloto limitado (atlas polish-A, 2026-09-04) e armadilhas de worktree/git

- **Auto-piloto**: cobre o caminho de execução, não as decisões quando os gates falham. Defaults ponytail para forks de baixo risco (worktree = recuperar+terminar, stashes = não mexer, 1 commit por fronteira de fase), mas **não decidir sozinho um constraint do SP contraditório** (ex.: §4 `Performance ≥ 95` vs §5 proíbe tocar `index.html`, e o único fix é preload em `index.html`). Contradição ou gate irrecuperável: parar e reportar (citar as duas cláusulas, os números e o fix proposto), pedir a decisão que desempata. Sem commit «PASS-WITH-CAVEAT» salvo aprovação explícita no mesmo turno. Anti-padrão: «perf=90 chega, commito» = mudança unilateral de contrato.
- **Worktree trap (canónico)**: repo com `.wt/<nome>/` pode resolver `read_file`/`search_files`/`patch` para a worktree. Antes de editar: `git rev-parse --show-toplevel` + `git status --short -- <file>`; depois: `git diff -w -- <file>`. Ficheiro todo removido+adicionado = editaste o que o Git não segue: reverter e reler da árvore de trabalho. Um patch «mínimo» que cruza caminhos pode largar linhas da versão viva: `wc -l` e contagem de CRLF (`b'\r\n'` em Python) antes e depois; se a contagem desce sem razão, reverter.
  - **`patch` numa worktree apagada «sucede» e escreve num caminho que o git já não segue** (atlas keyboard-first, 2026-09-05): `git status` não mostra nada, o ficheiro existe no disco; é perda de dados (stash/checkout/`worktree remove` destroem-no sem aviso). Receita: `git worktree list --porcelain`; caminho em falta = escritas a vazar: recriar (`git worktree add <path> <branch>`) ou aplicar no checkout pai. Antes de patch em `.wt/<nome>/`: `git -C <path> rev-parse --show-toplevel` (erro «not a git repository» = cópia velha). Depois: `git -C <pai> status --short` lista o ficheiro como `M`/`??`, senão vazou. Depois de um ciclo que remove a worktree, o 1º patch do seguinte vai para o pai.
  - **Worktree `prunable`** («gitdir file points to non-existent location»; o disco mantém trabalho, node_modules, artefactos de gate; ciclo interrompido sem commit, atlas polish-A 2026-09-04). Receita sem perder trabalho: (1) `git worktree list --porcelain`; (2) `git worktree prune` (só limpa o registo); (3) `git worktree add <path> <branch-existente>` (SEM `-b`) repõe o ponteiro `.git` sem checkout; (4) verificar com `git -C <path> status --short` e `rev-parse --abbrev-ref HEAD`. Anti-receita: `worktree remove --force` + `branch -D` + `add -b` apaga o trabalho em disco (untracked não se recupera com `fsck`). Stash + árvore suja = uma só decisão; não fazer pop até o user rever o disco.
  - **`git checkout <outro-ramo>` aborta com alterações por commitar** (master-merge, 2026-09-03): `git stash push -m "ponytail: pre-<ramo>-merge stash"` → checkout → ff-merge → push → voltar → `git stash pop`; conflitos no pop: decidir ficheiro a ficheiro, nunca pop às cegas numa worktree (nesta repo, ver também a regra do stash partilhado: preferir commit WIP).
  - **Árvore que não é tua** (agente paralelo, 2026-09-04): 20+ ficheiros sujos sem diff real de conteúdo, stashes `wip-other-agent-*`. Antes da DA: `git worktree list` + `git status --short | wc -l` + `git stash list | grep -i other-agent`. Se coincide, isolar num ramo `feature/<slug>` a partir do HEAD (`git checkout -b` leva as alterações; NÃO fazer stash antes). Stash só das alterações do *outro* agente antes do merge; ff-merge da feature; `stash pop` repõe o paralelo. Saltar isto = ciclo de recuperação («editei, o trabalho sumiu»).

## 7. «Bug report» ≠ «o que corrigir»: pedir a string de erro antes de DR/DA (Atlas, 2026-09-03)

- «Clico Aprovar, nada acontece»: assumi o handler, escrevi 5,3 KB de teste (16 asserts verdes, handler já estava certo). O bug real só surgiu com o erro colado: `CI gate falhou (typecheck): 'npm.cmd' is not recognized` (2 linhas em `server/api.ts`, cherry-pick de `f0e0e39`). Regra: perante «X não funciona» a 1ª resposta é UMA pergunta free-text pela string de erro (ou cauda do `.log`, ou comando + stdout/stderr), não «vou rastrear o código». Gatilhos: «X não funciona», «Y está partido», «Z não avança», «click faz nada», «stuck em doing/review». Saltar só se o erro já veio no mesmo turno.

## 8. Michi carregado mas o ciclo desviado por um pedido de ops: o Reflect continua devido (Atlas, 2026-09-02)

- `/michi` seguido de «roda os testes» / «faz commits dos changes» sem grill/DR/DP/DA: não saltar o Reflect no fim da *sessão*. O pedido é um dado (gotcha do stat-cache `M `, classificação de untracked-debug, `git checkout <ref> -- <file>` sem normalização de EOL). «Nothing to evolve» numa linha serve se nada surpreendeu.

## 9. Reflect é ponto de paragem, não transição (atlas backend, 2026-09-02)

- Depois do atrito, sem «próxima fase?» nem «pronto para X?». Os 3 caminhos do Reflect (patch michi / skill helper / bullet de backlog) pedem o user. Output do Reflect + uma linha «your call» / «wait for go». Refactors multi-fase = Reflect após cada fase e continuação explícita; na dúvida, parar.

## 10. Cadência de commit por fase numa DA multi-fase (atlas backend, 2026-09-02)

- Com ≥3 fases de DA, perguntar **na aprovação do plano** se commita por fase: (a) um commit por fase após gates (seguro, bisect, o user revê cada um); (b) um commit grande no fim (menos cerimónia, mas um ciclo partido = refazer tudo). Default em refactors grandes: (a). «Um commit só por fase» é teto duro: não dividir uma fase em vários. Mesmo com cadência aprovada, não auto-commitar: após gates RC=0, mostrar a mensagem e esperar; `git add` pode fazer-se, o `git commit` só com «go».

## 11. Clusters de refactor: commitar CADA ficheiro novo, não no fim da DA (atlas wrapper-replacement, 2026-09-03)

- Um refactor que cria N ficheiros (módulo `server/lib/<nome>.mjs` + `.d.mts`, M call-sites em `api.ts`, K testes) comita por «módulo + call-sites + testes que o protegem», não tudo no fim. Entre fases, qualquer processo que mexa na árvore (worker atlas com `git worktree add/remove`, auto-commit de agente paralelo, restart do Vite) pode pisar trabalho untracked: já se perdeu `run-card.mjs` + `.d.mts` + 5 call-sites + 3 testes. Receita: após o 1º ficheiro propor «módulo criado, commit?»; após o 1º call-site «1 de 5, commit?». Complementa «um commit por fase» no caso intra-fase. **Perda detetada** (voltar à sessão com menos ficheiros): (1) `git status --short`: ficheiros teus fora da lista `??` = perdidos, não escondidos; (2) linhas `M ` em ficheiros que tocaste com bloco `+N/-N` gigante = reset; (3) `git ls-files <path>`. Recuperação = refazer (`fsck`/reflog só valem para histórico commitado). Seguro mais barato: o commit por cluster.

## 14. Pós-processamento do filho desligado do event loop do orquestrador (atlas wrapper-replacement, 2026-09-03)

- Dev-server/CLI watch/daemon que lança um filho e tem de fazer algo depois (auto-merge, limpeza, push, relatório): não encadear num `.then()` do exit do filho; se o orquestrador reinicia a meio, morre o pós-processamento (card «running» para sempre, sem merge nem limpeza). Extrair para ficheiro próprio e lançar **destacado**: `spawn(process.execPath, [postProcessFile, ...args], { detached: true, stdio: 'ignore', windowsHide: true }).unref()` quando o filho sai com 0. O sub-processo escreve o seu estado em disco (`state: 'merge-failed'`); o ficheiro de estado é a fonte de verdade (sem propagação por promise). Diagnóstico: filho saiu bem + `.status` ainda `running` + commits na worktree sem merge. Gatilho: «depois de o filho sair, fazer X» com X > «logar uma linha».

## 15. «Faz um ajuste» a um plano aprovado: respeitar o porquê, não só o quê (atlas backend, 2026-09-02)

- O ajuste a meio da DA («separa em ficheiros mais cedo», «esta fase primeiro», «salta isto») é re-ponderação, não trabalho novo; não responder «mas o plano dizia X». (1) Repetir o *porquê* dado; (2) propor reordenação concreta que o respeite; (3) esperar «go». Se a fase em curso fica errada, reiniciá-la com a nova forma; as outras mantêm-se. Não dobrar em silêncio o ajuste na fase corrente (esconde a mudança de contrato).

## 16. Lista de correções pós-DA é uma fase, não um restart (atlas main-chat, 2026-09-04)

- DA entregue + report + commit, e o user responde com lista numerada (bugs + features): é sinal de *delta*, não da regra «Review restart» (qualidade). Receita: (1) ler a lista toda antes do item 1, sem clarificações intercaladas; (2) classificar: **bug** (fica na DA) vs **feature** (novo DP ou YAGNI-skip claro); (3) um só passe DA com código + testes + gates, sem commits por item salvo pedido; (4) sem re-correr grill/DR/DP; (5) report com secção «Δ» de 1 linha. Sinal de erro: o user volta com «também:» / «outra coisa:» / «mais:» = primeiro passe incompleto, repetir este padrão, não recomeçar na Fase 1.

## 17. Lista numerada de correções é contrato (atlas main-chat, 2026-09-04)

- Espelho da regra de Style «item-list». Cada item É o requisito: sem re-perguntar, sem multi-choice, sem fundir. A 1ª resposta é uma **tabela-resumo** (item | classificação | alteração), depois aplicar (sem ela: reordenar, largar ou partir «feature + teste» em dois passes). Proibido depois: «queres que também…» / «refatoro X já que estou aqui?» (scope creep); skips YAGNI vão no report, não na conversa.

## 20. Gate de estado pré-DA: `git status` + `git branch --show-current` + `git log -1` antes de editar (hermes-agent, 2026-09-04)

- Os factos do SP (ramo, último commit, worktree) derivam entre a escrita e a execução: o SP dizia «limpo, main, 5bca0e345», a realidade era `wip/main-features` com 7 ficheiros sujos de uma sessão paralela. Antes da DA: `git -C <repo> status --short | head -20`, `branch --show-current`, `log -1 --oneline`. Se QUALQUER facto diverge, UMA pergunta free-text antes de tocar a árvore (ex.: «SP diz limpo+main; está sujo+wip/main-features com 7 modificados de sessão paralela; escrevo na árvore suja?»). Free-text porque o user sabe o que tem; a resposta é uma palavra. Sem o gate: 2-5 min de confusão (diff do ficheiro inteiro, base errada).

## 21. `git checkout <outro-ramo>` aborta com alterações; árvore que não é tua

- Duplicado de §6 (sub-entradas «git checkout aborta» e «Árvore que não é tua»); ver §6.

## 22. Junctions/symlinks não se propagam do pai para a worktree (atlas strip-kanban, 2026-09-05)

- Pai com reparse point (junction/symlink) num caminho gitignored (`code/data/` → `vault/live-data/`): a worktree recebe um diretório normal vazio. Sintoma: dados reais no pai (633 KB de `kanban.json`), smoke da worktree lê `{"ver":0,"items":[]}`; `git status` não mostra nada (gitignored), invisível ao git. Antes de confiar num smoke de worktree, verificar que o dir de dados é a MESMA fonte: Windows `ctypes.windll.kernel32.GetFileAttributesW(<path>) & 0x400` ou `fsutil reparsepoint query <path>`; POSIX `path.is_symlink()`. Pai tem reparse e a worktree não: `cmd /c mklink /J <path-worktree> <alvo>` (junction sobrevive a `shutil.rmtree`, symlink não); default conservador (recriar) sem perguntar quando o SP diz «dados preservados». Invariantes do SP sobre caminhos gitignored verificam-se com ferramentas de filesystem, não com git.

## 23. Merge fast-forward quando a WT está 1 commit à frente de dev e o pai está limpo (atlas strip-kanban, 2026-09-05)

- Caso típico michi (WT com 1 commit sobre `dev`, `dev` sem commits que a WT não tenha, checkout pai limpo): mover o ref e push, sem PR nem checkout/merge/push:
  `sha=$(git -C <wt> rev-parse HEAD)` (SHA **completo**; `update-ref` rejeita abreviado, «not a valid SHA1») → `git -C <pai> update-ref refs/heads/dev "$sha"` → `git -C <pai> push origin dev`. Evita stash de untracked do pai e não toca na WT (que serve a porta de smoke). Pré-flight: `git fetch origin dev` ANTES de comparar (dev local pode estar velho); `rev-parse origin/dev HEAD`; WT à frente e origin/dev == base da WT = receita; se origin/dev tem commits que a WT não tem, é divergência real: merge normal ou PR.

## 25. Worktree → dev: puxar primeiro, merge DENTRO da worktree, resolver lá, depois dev (atlas strip-kanban-ui-2, 2026-09-05)

- Depois do commit+push da worktree não fazer «merge para dev e push»: dev pode ter andado e marcadores de conflito em dev dão páginas às 3 da manhã. (1) `git fetch origin dev` antes do merge final; (2) se origin/dev está à frente da base: `git -C <wt> merge origin/dev` e resolver na worktree (tem a feature, os testes, o output de gates; dev tem estado alheio); (3) gates de novo na worktree; (4) `git -C <pai> merge <ramo-wt>` → push. 2 comandos extra com dev velho, 0 com dev parado. Saltar só se acabou de se verificar origin/dev == dev local == base da worktree.

## 26. Fecho com push + merge: fast-forward quando `origin/<ramo>` == base (portfolio-docs-audit, 2026-10-17)

- `git fetch` → comparar `rev-parse origin/<ramo>` com a base; iguais: `git checkout <ramo> && git merge --ff-only <feature> && git push origin <ramo> <feature>`. Só com «push e merge» explícito do user. **Python no Git Bash**: não passar caminhos `/tmp` (o Python do Windows não os vê); usar o scratchpad ou ler do pipe (`git ... | python -I -c`).

## 27. Python em modo texto no Windows: CRLF e `\n` escapado (dev-workflow-escalar-programas, 2026-10-18)

- `open(p).read()` + `write()` converte LF em CRLF (diff total); usar `open(p, encoding="utf-8", newline="")` ou `Edit`. Em heredoc a gerar Python, `"\n"` chega ao ficheiro como quebra real e dá `SyntaxError: unterminated string literal`: para strings com `\n`/`\r\n` usar `Edit`, nunca script Python gerado (reincidência em sp-programa-avancar-fechar, 2026-10-18: `\n` dentro de `'''...'''` partiu o `.py` 2 vezes). Verificar com `git diff --stat` (tamanho plausível) e `git ls-files --eol <ficheiro>` (`i/lf w/lf`).

## 28. «Duplicada» num SP de inventário: ler o corpo antes de remover (dev-workflow-refactorizar-inventario, 2026-10-18)

- O SP dizia que `grilling` duplicava `grill-me` (ambas v1.2.0), mas `grill-me` era só ponto de entrada que carregava `grilling`; remover à letra deixava-o sem protocolo. Antes de mover/apagar uma skill «duplicada»: ler o corpo das duas e `Grep` pelo nome (`related_skills`, «load X»). Se uma depende da outra não são duplicadas: perguntar uma vez (fundir / manter / literal) com recomendação. `skill-version demote` recusa se a cópia primária difere da de referência; usar `archive` e copiar a primária para `inactive/`.

## 29. MCP numa worktree nova: verificar com `claude -p --mcp-config` (vault-mcp-uso-maximo, 2026-10-27)

- `claude mcp list` fica em «Pending approval» (o `.mcp.json` novo não está aprovado) e não prova nada. Repetir `echo ok | claude -p --mcp-config .mcp.json --strict-mcp-config --output-format stream-json --verbose --max-turns 1` e ler `mcp_servers[].status` (esperado `connected`). Servidor que indexa antes de `server.connect` falha o handshake aos 30 s (`CONNECT_TIMEOUT`): ligar primeiro, aquecer depois.

## 30. Gates sobre repo externo: `cd` no comando (kaizen-sync-igual-ao-vault, 2026-10-27)

- `sp-gates.py` corre cada `gates[].cmd` com o `cwd` do vault. `node K/bin/kaizen.js audit` sem `cd` analisou o vault (14214 hits falsos em `_templates/`) e travou o fecho. Todo o `cmd` que opera num repo externo ou worktree de código começa com `cd <repo> &&`, para a worktree K do SP, não o checkout principal.
