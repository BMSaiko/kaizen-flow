---
name: design-system
description: Gera e valida o design system de um projeto de UI (DESIGN.md e tokens DTCG, contraste WCAG, export CSS e Tailwind). Usar num SP com ui sim, ao criar uma interface ou ao rever cores, espaçamento e componentes.
version: 1.0.0
---
# design-system

O design system é do projeto-alvo: `DESIGN.md` (porquê e como) e `design/tokens.json` (valores, W3C DTCG). O kaizen-flow só gera e valida.

## Comandos (stdlib, sem rede)

| Passo | Comando |
|---|---|
| Criar | `python -I scripts/ds-init.py <projeto> [--primaria #hex] [--neutra #hex]` (nunca sobrescreve sem `--force`) |
| Validar | `python -I scripts/ds-validate.py [--dir D]`: schema DTCG, `{alias}` resolúveis, contraste, escalas; rc 1 lista as falhas |
| Exportar | `python -I scripts/ds-export.py [--dir D] [--out D]`: `tokens.css` (claro/escuro) e `tailwind.preset.js`; recusa tokens inválidos |
| Lint | `python -I scripts/ds-lint.py [--dir D]`: literais de cor/espaçamento/tipografia fora dos tokens; rc 1 |
| Verificar UI | `python -I scripts/ds-verify.py [--dir D] [--atualizar-baselines]`: axe, screenshots vs baselines; rc 3 sem browser |
| Linting | `python -I scripts/ds-lint.py [--dir D]`: literais fora dos tokens; rc 1 |
| Verificar UI | `python -I scripts/ds-verify.py [--dir D] [--atualizar-baselines]`: axe, screenshots vs baselines; rc 3 sem browser |

CLI equivalente: `kaizen ds init|validate|export|lint|verify`.

## Regras

1. Antes de desenhar ou codar UI: ler `DESIGN.md` e os papéis em `design/tokens.json`; se não existem, `ds-init`.
2. Cor só por papel semântico (`color.light|dark.*`), espaçamento só da escala `space.*` (múltiplos de 4px). Sem valores soltos no código.
3. Todo o par texto/fundo novo entra em `$extensions.kaizen.contrast` (`kind` text 4.5:1, ui 3:1); `ds-validate` tem de dar rc 0 antes de fechar o SP.
4. Mudou um token: `ds-validate`, depois `ds-export`, e commitar `tokens.css` e o preset.
5. Componente novo: documentar em `DESIGN.md` (variantes, estados, tokens, a11y) pelo checklist.

## Detalhe (ler só o que precisa)

- `references/principios.md`: princípios, escalas, formato dos tokens.
- `references/componentes.md`: checklist de componente e estados.
- `references/a11y.md`: WCAG 2.2 AA aplicado, o que o validador não apanha.
- `references/verificacao.md`: gates `ds-lint` e `ds-verify` (SPs `ui: sim`).
