# michi — Skip-grill play (`skip grill` + âmbito vago)

> O pitfall «skip grill + instrução vaga e grande» (`michi-pitfalls.md` §3) liga aqui. Com `skip grill` e uma instrução grande e difusa («refactor X», «limpa Y», «corrige os bugs de Z»): não saltar para DR/DP/DA nem fazer 5 perguntas. Fazer isto.

## O scan de 5 minutos (antes de perguntar)

Um scan é um censo, não pesquisa: saber o que existe e o que partiria.

| Sonda | Ferramenta | Porquê |
|---|---|---|
| Layout de topo | `Glob` `*` no repo | Tipo de repo (TS/Node, Python, Go…) |
| Tamanhos da zona suspeita | contar `b'\n'` por ficheiro (`pathlib`) | Achar o **único** monólito (vs 30 ficheiros pequenos) |
| Superfície exportada | `Grep` `^export ` / `^export default function` / `^export class` | Contrato público a preservar |
| Entradas públicas | rotas (`router.X`/`app.X`/`s.middlewares.use`) ou nomes de funções | De que dependem testes e cliente |
| Testes na zona | `Glob` `*test*` + grep das entradas | Gate mínimo a não partir |
| Estado git | `git status --short`, `branch --show-current`, `worktree list` | Worktree trap, árvore suja, ramo |

Mais de 5 min = pesquisa: parar, escrever o que há, perguntar.

## A tabela de coragem (o artefacto de alinhamento)

O user saltou o grill: responde a 1 pergunta, não a 6. Essa pergunta é uma escolha em que cada opção é uma **forma diferente** (código tocado, risco, dependências):

```
== Onde aterrar — preciso de 1 decisão tua ==

A — <seguro>: <o quê + tamanho do diff>. <risco numa linha>.
B — <+1 eixo>: <o quê + tamanho + eixo>. <risco>.
C — <reescrita>: <o quê + tamanho + framework/padrão>. <risco>.

Honestamente, <recomendação> é o que "<palavras do user>" quer dizer sem transbordar. <o que mudaria a recomendação>.

Diz: <nível A/B/C> · <âmbito sim/não> · <um eixo inevitável>
```

A recomendação é obrigatória: o user saltou o grill para não decidir tudo; quer um sénior a escolher.

## O pedido de uma decisão

Uma só pergunta com: nível (quase sempre a recomendação), âmbito (a zona ou o backend todo) e **um** eixo inevitável (ex.: «posso adicionar zod?») se o nível o exigir. Nunca incluir: ramo (está no scan), caminhos (derivam da estrutura), testes a correr (derivam da lista), «mais alguma coisa?» (scan incompleto: voltar atrás). «Faz A e B mas salta C»: honrar; o user manda na escada, tu escolhes o degrau.

## O que NÃO fazer

- `dp` sobre a instrução vaga: DP precisa de um objetivo de um ecrã; «refactor do backend» é direção.
- Lista de 30 itens: se precisas, a tabela de coragem não está acabada.
- Editar antes da resposta: o play expõe a forma; 2 min de scan + 1 decisão são mais rápidos que 3 patches revertidos.
- Parafrasear o user: a tabela tem de *nomear* o que é o backend; o scan ganha esse direito.

## Sem resposta ao free-text (atlas polish-A, 2026-09-04)

O `clarify` tem janela. Sem resposta, não parar: regra ponytail, versão preguiçosa, defaults mais conservadores que preservam o contrato do SP, e listar cada default aplicado no DP em «What you should know before signing off» para override na review. Defaults que aguentaram:

1. **Worktree** com dir+ramo e trabalho por commitar de sessão anterior: recuperar+terminar (`git worktree prune` + add sem `-b`), nunca apagar e recomeçar (receita completa: pitfalls §6).
2. **`stash@{0}` de sessão anterior**: deixar, não tocar neste épico (o pop mistura âmbitos e pode partir invariantes do SP, ex.: `server/**` idêntico byte a byte).
3. **Gate anterior que falhou a barra** (Lighthouse 91 vs ≥95): repetir uma vez no estado atual e confiar no novo número (pode ser artefacto do preview); se falha, sub-fase condicional no DP, sem baixar a barra.

Regra: não assumir em silêncio; mostrar o default, nomear a escolha conservadora e a regra de recurso (Style do SKILL.md).

## Exemplo (atlas backend refactor, 2026-09-02)

«faz refactor ao backend todo do projeto atlas, da skip ao grillme». Scan: `server/api.ts` 1500 linhas, um `export default function atlasApi(): Plugin` (Vite), ~35 handlers inline e 35 helpers; `config.ts` 75, `roadmap.ts` 81, `snapshots.ts` 155 (módulos limpos), `prompts/` já dividido; cliente usa 6 endpoints de `src/api.ts`; `test/_atlas-harness.mjs` + `test/ci-gate.test.mjs` batem no servidor real; `live-data/.wt/atlas/` tem 14 worktrees históricas.

| Nível | O quê | Risco |
|---|---|---|
| A — extrair só handlers | ~200 LoC, 35 handlers → `server/routes/*.ts`, tabela de dispatch | baixo |
| B — + erros/validação | A + `readBody<T>(schema)` + `sendError` | médio (zod = **nova dep**) |
| C — + Router real | B + `express.Router`/Hono/find-my-way | alto (middlewares do `configureServer` + router escorregadio) |

Recomendação A: «refactor do backend» é estrutural e A é o mínimo que merece o nome. O user não respondeu (interrompido): michi parou na fase 1; o Reflect continua devido (pitfalls §8).

## Depois da escolha: juntar o «wire-only» ao primeiro movimento

Tipicamente a seguir vem «extrair o esqueleto de dispatch → gates → mover handlers». **Esqueleto vazio (sem rotas, sem mudança de comportamento, testes idênticos) é meia fase, não fase**: juntar ao 1º movimento real («ligar o dispatcher E mover o domínio mais simples, 3 handlers, depois gates»). O user aprovou a tabela, não um gate entre «esqueleto compila» e «primeira feature move». Padrão: (1) `done-when` da fase seguinte em termos visíveis («X rotas fora de `api.ts`, gates RC=0, `api.ts` −N linhas»); (2) dentro dela, wire + 1º movimento (wire = pré-requisito, movimento = entrega); (3) wire no report como sub-secção, não como «fase concluída».

Exceção: quando o wire É o risco (novo modelo de auth, passo de build, dependência de runtime): a fase wire-only guarda o risco. Refactors estruturais puros não entram. Contra-exemplo (atlas, 2026-09-02): «2A wire dispatch, 0 handlers» + «2B mover `terms/*`»; 2A deu report vazio e parei a pedir confirmação do plano por domínio, um gate de aprovação que a tabela não pedia; devia ser uma fase («wire + 3 handlers `terms`, gates verdes»).

## Higiene de gates

Estas regras estão em `michi-pitfalls.md`: não matar processos em bloco (`taskkill /PID` ou filtro por `CommandLine`, ex. `killWtLockers` em `server/api.ts:206-211`; confirmar com `tasklist /FI "IMAGENAME eq <interpreter>"` antes de dizer «limpei») e EOL começa por `git config --show-origin --get-all core.autocrlf`/`core.eol` + `git check-attr -a -- <file>` (§3; atlas EOL 2026-09-04: 3 `git checkout` falhados até ver o autocrlf de sistema; um `Path.write_bytes` + `git add` + commit resolveu). Gate de estado pré-DA: §20.

### Perfil Windows do hermes-agent: `patch`/`read_file`/`search_files` falham com erros genéricos

No perfil Windows do user (hermes), `terminal()` corre numa sandbox MSYS sem `git`/`uv`/`python` no PATH e as ferramentas `read_file`/`search_files`/`patch` têm resolução de caminhos partida («Failed to read file», «search requires rg»); `write_file` com aspas simples falha com `unexpected EOF`. Sem esta regra: 3-5 min por ficheiro. **Default para qualquer FS:** `execute_code` + `pathlib`.

```python
from pathlib import Path
content = Path(r"~\Documents\hermes-agent\file.py").read_text(encoding="utf-8", errors="replace")
Path(r"C:\...").write_text(content, encoding="utf-8")   # cria pais se preciso
Path(r"C:\...").unlink(missing_ok=True)
for p in Path(r"C:\...").rglob("*.py"):
    if "needle" in p.read_text(encoding="utf-8", errors="replace"): ...
```

Shell: sempre exe absoluto (PATH vazio) e decodificar `tasklist` em cp1252.

```python
import subprocess
GIT = r"C:\Program Files\Git\bin\git.exe"
UV = r"~\.local\bin\uv.exe"
PY = r"~\Documents\hermes-agent\.venv\Scripts\python.exe"
r = subprocess.run([GIT, "status", "--short"], cwd=str(repo), capture_output=True, text=True, timeout=15)
t = subprocess.run([r"C:\Windows\System32\tasklist.exe"], capture_output=True, timeout=10).stdout.decode("cp1252", errors="replace")
```

Deteção: `read_file` dá `Failed to read file` para um caminho que `ls`/`Path.exists()` vê; não repetir, mudar para `execute_code` (a 1ª chamada da DA, não a 3ª). Origem: hermes-agent windows-notify, 2026-09-04 (3-5 min perdidos).
