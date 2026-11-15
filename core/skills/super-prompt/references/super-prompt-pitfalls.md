# super-prompt: pitfalls

Regras gerais; os casos de origem estão no arquivo de incidentes do vault (`knowledge/infra/reference/michi-incidentes.md`).

1. **Objetivo vazio.** Perguntar uma vez e sair, sem inventar objetivo.
2. **Saltar fases.** Cada fase aperta a seguinte; o que se poupa no brainstorm paga-se em retrabalho no DP.
3. **Escolha múltipla sobre factos já ditos.** Um facto dado no início não volta como pergunta.
4. **Secções 4, 5 e 8 incompletas.** Sucesso sem sinal observável ou done-when sem verificação não são critérios: voltar ao grill-me nessa secção.
5. **Caminho errado.** Criar sempre com `sp-new.py` (`SKILL.md` §Onde guardar).
6. **Executar o SP na mesma sessão.** O SP existe para atravessar a fronteira de sessão; `/michi` é o executor.
7. **Pivot a meio para outra tarefa.** Abortar limpo, dizer numa frase que o SP não foi guardado e passar ao pedido real; um SP meio feito levaria a sessão seguinte a assentar em âmbito não validado.
8. **Grill-me em várias rondas.** A primeira ronda junta todas as perguntas abertas com o default à frente de cada uma; se a resposta cobre os itens, fechar. Segunda ronda só se a resposta contradiz uma secção. Com um user a aprender o domínio, os defaults vão como factos no Spec.
9. **Conteúdo hostil ao shell** (backticks, `$`, aspas, caminhos Windows). Escrever o SP com `Write`/`Edit`, nunca por heredoc ou strings geradas no shell.
10. **Forma da pergunta ao user.** Pergunta aberta por defeito, com os defaults no texto; escolha múltipla só com 2-3 opções exclusivas, recomendada primeiro.
11. **Pergunta sem resposta na janela.** Equivale a aceitar os defaults escritos na pergunta; não repetir a ronda (exceto com objetivo vazio, #1).
12. **Âncoras de patch.** Antes de cada substituição num SP que mudou entre turnos, copiar o texto exato do ficheiro e confirmar que ocorre uma só vez; uma âncora de memória falha em silêncio.
13. **DR mini só com infra viva.** Cada seam de §6 confirma-se no ramo base (`git ls-files --error-unmatch` ou `Grep`) antes de publicar, porque um seam removido dá um SP que não compila.
