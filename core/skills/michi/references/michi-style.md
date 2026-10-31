# michi — Style (casos e regras de estilo)

Movido de `SKILL.md` (## Style); condensado em 2026-10-31 (regras todas mantidas), 16 entradas.

## 1. Por defeito, pergunta free-text, não `clarify` multi-escolha

- Lista de 4 opções é overhead quando a fase seguinte é mecânica (avançar para DR/DP): um «avanço com X, ou ajusto?» substitui 3 rondas. Multi-escolha só para forks reais em que cada opção é uma forma diferente, sempre com «Other». Caso (Atlas, 2026-09-03): 3 rondas `clarify` seguidas no grill (forma do sintoma, do chip, transições), 9 opções, quando uma mensagem («1+2+3, ambos, flow X») bastava. Se as 2-3 perguntas seguintes são do mesmo domínio, juntá-las numa pergunta free-text com bullets.
  - **«1+2+3, quero …» É a resposta** (Atlas wrapper, 2026-09-03): o user comprimiu as tuas perguntas numa lista + diretiva; parar de clarificar, aceitar cada item e passar ao DP. Voltar a perguntar em multi-escolha é re-perguntar factos dados. A resposta seguinte é evidência de DR + rascunho de DP.

## 2. Um turno visível por transição de fase

- Resumo curto do que ficou decidido, o que a fase seguinte faz, e pedir go/no-go.

## 3. Não re-perguntar factos já ditos

- «Branch dev» no turno 1 não vira «master vs dev» no turno 5. Confirmar um facto dito é acknowledgement, depois agir.

## 4. Respostas de `clarify` mudam o código/skills no mesmo turno

- Se o `clarify` fixou um default («onde fica?», «que slug?», «que ramo?»), o artefacto atualiza AGORA, na resposta que processa o resultado; não num patch seguinte, nem no report, nem «na próxima sessão». (`requirements-pdf-interpreter` saiu com `~/.hermes/...` por defeito apesar de o user ter escolhido `<SB>/knowledge/projects/<slug>/`.)

## 5. Git é do user; um «go» responde ao que a pergunta nomeou

- Commit/push: regras em `michi-modo-auto.md` §Proibições e §Autorizações do SP (a skill opina sobre o *fluxo*; o git é do user).
  - **Um «go» responde ao que a pergunta nomeou** (atlas-inbox-e-painel-sps, 2026-10-18). Se o ok já lista as ações (commit, push, PR), um «go» aprova todas. Lista vaga («avanço?»): nomear cada ação. Merge e ações destrutivas pedem ok próprio.
  - **O ok de cada fase nomeia as ações** (atlas-calendario-e-pomodoro, 2026-10-18). «Segues com a 7?» não autoriza escrever nem commitar: «escrevo, commito e passo à seguinte?». Commit sobre um «go» não associado a commit é deslize, mesmo com plano aprovado. Antes do commit, assunto ≤72 caracteres (o hook recusa).
  - **Factos herdados do SP verificam-se à hora do DP** (idem). Número da próxima decisão e «validado em X» resolvem-se com `Grep` em `DECISIONS.md` e no código (o SP dizia «decisão 24», era 26, e «validado em `write_board`», quem rejeitava era o serde). Alinha com «SP vs repo state may still fork».
  - **Script de runtime que envia teclas: conferir cada atalho em `shortcuts.ts`** (idem). Copiar de outro script não chega (`^1` escolhe o mundo, a vista Todo é `Alt+3`); ver o screenshot da primeira falha antes de reescrever o teste.

## 6. Nunca auto-patch nem auto-criar skills

- O Reflect propõe, o user aprova. Auto-edição é proposta, não execução.

## 7. «fix it» + correção destrutiva = perguntar, nunca adivinhar (hermes-agent, 2026-09-04)

- «fix it» sem contexto, com correção óbvia destrutiva (matar 6 processos do user, `drop table`, force-push), concede autonomia só para o caminho *não destrutivo*. Receita: (1) listar os PIDs; (2) nomear o custo («perdes 6 sessões em curso»); (3) propor default mais estreito (matar 1 + repetir, ou esperar que o user feche); (4) perguntar. Anti-padrão: «fix it» → kill em bloco → 6 h de trabalho alheio perdidas. Se a correção destrutiva tem ≥2 desfechos («matar o holder» vs «esperar estado limpo») e o user está na máquina: PIDs, custo, perguntar. Torna explícita a frase-gatilho para «fix it» não ser lido como luz verde.

## 8. «skip fase X» / «go to DA»: honrar

- As fases são ordem por defeito, não jaula. `/michi skip reflect` salta o Reflect e vai à proposta de commit.

## 9. Skill-fit antes de carregar (atlas main-chat, 2026-09-04)

- Pedido de «design, frontend, taste, UX/UI»: não carregar `ui-styling` + `ui-ux-pro-max` + `design-system` às cegas. Stack primeiro: `ui-styling` é shadcn/Tailwind/React, inútil em vanilla-TS Vite (Atlas). Certo: `ui-ux-pro-max` (regras agnósticas: contraste, foco, alvos de toque, comprimento de linha, motion) + `design-system` (arquitetura de tokens) limitado às primitivas do projeto (Atlas tem `tokens.css` com 3 camadas night/day/dusk + 4 estações: reutilizar). Antes de `skill_view(nome)`: «a tecnologia principal bate com o projeto?»; se não, saltar e registar no DP (o user prefere não-cargas explícitas).

## 10. O DP absorve preferências como decisões de design, não perguntas (atlas main-chat, 2026-09-04)

- «No chat vou sempre referir o mundo» a meio do DP não é «queres que pergunte por mensagem?» mas «removido; DP atualizado: o agente não tem slug default, pergunta ‹Em que mundo?› sem slug detetado, a UI deixa de inferir ação por defeito». A afirmação do user É a decisão: incorporar, não enfileirar. Idem «o chat lembra o histórico?» → decidir (cap 200 FIFO). Âmbito: preferências *simples*; forks genuínos (que forma? que stack? onde vive?) continuam em batch free-text.

## 11. Saltar o teste tautológico é decisão TDD válida; documentar (atlas main-chat, 2026-09-04)

- Código novo que é cópia-modificação byte a byte de um handler existente (só mudam paths/IDs): o teste da *classe* já cobre a instância. Um teste paralelo (`chat-output.test.mjs` espelho de `output-stream.test.mjs`) é tautologia: apanham a mesma classe de bug e um refactor que parta o novo parte o velho. Saltar e dizer no report: «skipped <nome>.test.mjs — clone de <existente>.test.mjs, mesma lógica, paths diferentes». Barra para um teste novo: «falha por uma razão que o existente NÃO apanha».

## 12. «Corre o gate» em vez de «sonda a dependência» (atlas polish-A, 2026-09-04)

- Gate que depende de serviço em execução (preview, DB, daemon): perguntar «X está up?» corre-se com o próprio gate, que reporta a ligação. Razões: (1) o gate corre de qualquer forma; (2) porta aberta ≠ endpoint a responder; (3) o user bloqueou sondas (`curl http://...`, `node -e fetch(...)`) neste perfil. Sonda separada só se o modo de falha do gate for opaco e precisares de sinal cedo, e pelo mesmo transporte do gate (`lighthouse http://...` duas vezes serve; `curl` antes de `lighthouse` é desperdício).

## 13. Plano errado a meio da DA: recomeçar na fase relevante

- Sem retroceder em silêncio.

## 14. Respostas curtas: código e output primeiro, prosa só se pedida

## 15. DP supersession por renomeação, não overwrite (atlas polish-A recovery, 2026-09-04)

- DP que evolui porque o disco mudou entre a aprovação original e a nova tentativa (a sessão anterior entregou A1+A3+A4 sem commit; o v2 é plano de recuperação): o anterior tem valor de auditoria. Receita: `git mv plans/<slug>-DP plans/<slug>-DP-v1` (ou `Path.rename` se untracked) ANTES de escrever o v2 no caminho canónico `plans/<slug>-DP/DP.md`, com `supersedes: plans/<slug>-DP-v1/DP.md` no frontmatter (linhagem grep-ável). Anti-padrões: overwrite do v1 (perde auditoria); v2 em `<slug>-DP-v2/` (contexto dividido, «onde está o plano vivo?»). O caminho canónico fica estável.

## 16. Sem resposta ao free-text na janela: defaults ponytail

- Aplicam-se defaults ponytail («versão preguiçosa, pergunta na mesma resposta») só os mais conservadores que preservam o contrato do SP, todos registados no DP em «What you should know before signing off». Os 3 defaults (worktree = recuperar+terminar, `stash@{0}` alheio = não tocar, gate falhado = repetir uma vez e confiar no novo número) e a regra «não assumir em silêncio» estão em `references/michi-skip-grill-play.md` §Sem resposta ao free-text.
