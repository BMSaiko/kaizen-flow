# michi: Style

Regras de conversa e de decisão. Os casos que as originaram estão no arquivo de incidentes do vault (`knowledge/infra/reference/michi-incidentes.md`).

## 1. Pergunta aberta por defeito

- Escolha múltipla só para forks reais, em que cada opção leva a uma forma diferente, sempre com «Other»; perguntas do mesmo domínio juntam-se numa só. Quando o user responde com uma lista e uma diretiva, essa é a resposta: avançar.

## 2. Um turno visível por transição de fase

- Resumo do que ficou decidido, o que a fase seguinte faz e o go/no-go.

## 3. Não re-perguntar factos já ditos

- Confirmar um facto dito é só reconhecê-lo e agir.

## 4. Uma resposta muda o artefacto no mesmo turno

- O default fixado por uma pergunta entra já no código ou no SP, não num patch posterior.

## 5. Um «go» responde ao que a pergunta nomeou

- Regras de commit e push: `michi-modo-auto.md` §Proibições e §Autorizações. O ok de cada fase nomeia as ações (escrever, commitar, avançar); merge e ações destrutivas pedem ok próprio.
- Factos herdados do SP (números de decisão, onde algo é validado) verificam-se com `Grep` antes do DP, porque envelhecem.
- Testes de UI que enviam teclas conferem cada atalho na fonte do projeto.

## 6. Sem auto-patch de skills

- O Reflect propõe e o user aprova.

## 7. «fix it» com correção destrutiva

- Só autoriza o caminho não destrutivo: listar o que se perde, propor o default mais estreito e perguntar.

## 8. «skip fase X» e «go to DA»: honrar

- As fases são ordem por defeito, não obrigação.

## 9. Skill-fit antes de carregar

- Carregar uma skill só se a tecnologia dela bate com a do projeto; a não-carga fica registada no DP.

## 10. Preferências simples são decisões, não perguntas

- O DP incorpora-as logo; só forks genuínos voltam ao user.

## 11. Teste tautológico

- Um teste que só repete outro para a mesma lógica pode saltar-se, com a razão no report; um teste novo tem de falhar por algo que os existentes não apanham.

## 12. Correr o gate em vez de sondar a dependência

- O próprio gate reporta se o serviço está de pé; sondas à parte gastam pedidos e podem estar bloqueadas.

## 13. Plano errado a meio da DA

- Recomeçar na fase relevante e dizê-lo.

## 14. Respostas curtas

- Código e output primeiro; prosa só se pedida.

## 15. DP substituído por renomeação

- O DP antigo passa a `-v1` antes de escrever o novo no caminho canónico, com `supersedes:`, para manter a auditoria.

## 16. Sem resposta a uma pergunta

- Aplicar os defaults mais conservadores que preservam o contrato do SP e registá-los no DP (`michi-skip-grill-play.md` §Sem resposta).
