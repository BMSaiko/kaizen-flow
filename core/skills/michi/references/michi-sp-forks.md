# michi: forks entre o SP e o repo (fase 1)

- **O SP pode estar coerente e não bater com o repo.** Antes do sign-off do DP, levantar o estado real (`git status`, `git worktree list`, `git branch -a`, diretórios de worktrees) e juntar numa só pergunta aberta, com o rascunho do DP, cada facto do SP que diverge (ramo sujo, caminho de worktree diferente da convenção do repo). O SP é contrato de intenção, não de caminhos que o repo decide.
- **§2 muda a stack mas §7 não lista a migração.** Nomear a lacuna como um fork em «What you should know before signing off», com três saídas: seguir §2 à letra e acrescentar o passo; seguir o espírito de §2 mantendo o ficheiro existente (defeito, por mexer menos); adiar §2 para outro SP. Decidir em silêncio leva a um rename por commitar a meio da DA ou a desvio visível só na review.
- **Sem divergência, sem pergunta.** Se ramo, árvore, último commit e dependências batem com o SP, o DP segue sem perguntar; basta um facto divergente para perguntar.
