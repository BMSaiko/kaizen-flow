# michi — prova visível por fase (2026-10-20)

Fim de cada fase de entrega (DA que muda código/UI): mostrar ao user uma prova observável, como o cliente final usaria a feature. «Os testes passam» sozinho não é prova.

## Tipo de mudança → prova

| Mudança | Prova mínima | Como |
|---|---|---|
| UI / design | ≥1 screenshot do resultado (ou demonstração na app) | skill `run` lança e captura; ficheiro em `proofs/` |
| API / backend | pedido real + resposta | comando completo + output (truncar em `proofs/<fase>.txt`) |
| CLI / script | comando real + output | idem |
| Dados / migração | contagens/consulta antes e depois | comando + output |
| Infra / config | estado observável (serviço up, comando devolve o esperado) | comando + output |
| Performance (se houver requisito) | benchmark com número vs requisito | comando + output |
| Docs / vault | ler como leitor: links resolvem, instruções reproduzem | caminho + resultado |
| Regras de agente | um cenário que a regra deve mudar | cenário + output |

## Regras
- Artefactos em `proofs/` ao lado do SP (`<pasta do SP>/proofs/<slug>-faseN.<png|txt>`); screenshots nunca no contexto, só o caminho (ver ficheiro só se preciso).
- Registar no SP, secção extra `## Prova` (fora das 8; `sp-validate.py` tolera): fase, comando/ação, caminho do artefacto, resultado.
- **Mostrar sempre o caminho absoluto de cada prova na resposta** (um por linha, copiável) ao apresentá-la e no relatório final; o user não deve ter de a procurar.
- Prova fabricada é proibida: o output é o real, mesmo que falhe (reportar a falha).
- Sem prova possível: parar e perguntar ao user (`AskUserQuestion`: dar outra prova / dispensar). Dispensa explícita fica registada «sem prova (dispensada pelo user)».
- Modo auto / sem interação: tentar prova alternativa; se nenhuma, registar «sem prova» e dizê-lo no relatório.
- Captura de UI: esperar por um elemento real da página (`waitFor` no `h1`/conteúdo), nunca um tempo fixo; skeleton na imagem = prova inválida, repetir.
- Baseline de testes sem as alterações (e2e/jest): usar `git worktree`, nunca `git stash` (ficheiros versionados como `test-results/.last-run.json` fazem o `pop` abortar).
- A prova da Fase 5 (`## Prova de done`) consolida e referencia estas, não as repete.
- **SP com `gates:`/`prova:` no frontmatter:** a prova e os gates vêm do SP (`python -I scripts/sp-gates.py <SP>`), não são inferidos; sem esses campos vale a tabela acima.
