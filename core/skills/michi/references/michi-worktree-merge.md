# michi: merge da worktree para dev

O ramo de dev pode ter andado desde que a worktree foi criada, e resolver conflitos lá é resolver sem o contexto da alteração. Por isso:

1. `git -C <pai> fetch origin dev`.
2. Se `origin/dev` está à frente da base da worktree: `git -C <wt> merge origin/dev` e resolver os conflitos na worktree, onde estão a alteração, os testes e o output dos gates.
3. Correr os gates de novo na worktree, porque o estado depois do merge é o que segue.
4. Só então `git -C <pai> merge <ramo-wt>` e push (fast-forward se possível, senão `--no-ff`).

Com mais de um ramo longo candidato a destino, perguntar qual. Autorizações: `michi-modo-auto.md` §Autorizações.
