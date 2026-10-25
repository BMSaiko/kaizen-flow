# Perfis de execução do SP (único sítio)
Frontmatter `perfil: cauteloso|normal|autonomo` (defeito `normal`) e overrides `max_tentativas`, `max_requests`, `parar_se: [...]`; gravados pelo `/super-prompt` (`sp-new.py --perfil/--max-tentativas/--max-requests/--parar-se`) e validados por `sp-validate.py` (`autonomo` exige `gates:`). O michi lê-os no arranque e na paragem. O perfil só afina; nunca relaxa as proibições do michi nem as «Autorizações do SP» (`michi-modo-auto.md`).

| Perfil | Tentativas por gate | `parar_se` por defeito | Em ambiguidade | Antes de apagar |
|---|---|---|---|---|
| `cauteloso` | 1 | gate-falha, ambiguidade, ficheiro-fora-de-escopo, custo | pergunta (`AskUserQuestion`) | pergunta |
| `normal` | 2 | gate-falha, ficheiro-fora-de-escopo | pergunta se for material | segue as regras do michi |
| `autonomo` | 2 | gate-falha | escolhe o default conservador e regista no Report | segue as regras do michi |

Overrides: `max_tentativas` substitui a coluna das tentativas; `max_requests` limita pedidos na sessão (parar e registar ao atingi-lo); `parar_se` substitui a lista por defeito. Valores de `parar_se`: `gate-falha`, `ambiguidade`, `ficheiro-fora-de-escopo`, `custo`. Paragem = `michi-modo-auto.md` §Paragem. Sem `perfil:` o SP comporta-se como `normal`.
