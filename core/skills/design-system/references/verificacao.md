# Verificação da UI (SPs `ui: sim`)

1. `ds-lint` (`kaizen ds lint`): zero literais de cor, espaçamento e tipografia fora dos tokens; `ds-lint-ignore` só com justificação.
2. `ds-verify` (`kaizen ds verify`): axe WCAG 2.2 AA, screenshots em 3 breakpoints vs `design/baselines/`, orçamento Lighthouse opcional; relatório em `design/relatorio.json` (anexar à prova do SP com `--prova`).
3. rc 3 = sem browser: instalar `playwright` e `@axe-core/playwright` no projeto-alvo; nunca dar como verde.
4. Baselines só com `--atualizar-baselines` e depois de rever o diff; fica registado em `## Design` do SP. Nunca atualizar para fazer passar o gate.
5. Config `design` em `kaizen.config.json`: ver `docs/config.md`.
