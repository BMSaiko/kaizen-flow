# michi: Skip-grill play (`skip grill` com âmbito vago)

Liga a `michi-pitfalls.md` §3. Com `skip grill` e uma instrução grande e difusa («refactor X», «corrige os bugs de Z»), não saltar para DR/DP/DA nem fazer muitas perguntas: levantar o que existe e pedir uma decisão.

`skip grill` só vale para executar um SP já aprovado; criar um SP pede pelo menos uma ronda de grill (`sp-aprovar.py --rondas`).

## Levantamento (antes de perguntar)

Um censo, não uma pesquisa: o que existe e o que partiria. Acaba quando a tabela abaixo se consegue preencher.

| Sonda | Porquê |
|---|---|
| Layout de topo (`Glob`) | tipo de repo |
| Tamanho dos ficheiros da zona | achar o monólito |
| Exports e entradas públicas (rotas, funções) | contrato a preservar |
| Testes da zona | gate mínimo a não partir |
| `git status`, ramo, `worktree list` | árvore suja ou worktree errada |

## Tabela de coragem

Uma pergunta, em que cada opção é uma forma diferente (código tocado, risco, dependências), com recomendação, porque quem salta o grill quer que alguém escolha:

```
A: <seguro>: <o quê e tamanho do diff>. <risco>.
B: <+1 eixo>: <o quê, tamanho e eixo>. <risco>.
C: <reescrita>: <o quê, tamanho e padrão>. <risco>.
Recomendo <X> porque <razão>. Diz: nível, âmbito e o eixo inevitável, se houver.
```

Não perguntar o que o levantamento já responde (ramo, caminhos, testes). Não escrever DP sobre a instrução vaga nem editar antes da resposta.

## Sem resposta

Não parar: aplicar os defaults mais conservadores que preservam o contrato do SP e listá-los no DP para revisão:

1. Worktree com trabalho por commitar de uma sessão anterior: recuperar e terminar (`michi-pitfalls.md` §6), nunca apagar.
2. Stash de outra sessão: não tocar.
3. Gate que falhou a barra: repetir uma vez no estado atual; se volta a falhar, sub-fase no DP, sem baixar a barra.

## Depois da escolha

Uma fase só de esqueleto, sem mudança de comportamento, junta-se ao primeiro movimento real (ligar o dispatcher e mover o domínio mais simples). Exceção: quando o esqueleto é o risco (auth, build, dependência de runtime), fica fase própria.

## Higiene de gates

Processos, EOL e estado antes da DA: `michi-pitfalls.md` §3 e §20.
