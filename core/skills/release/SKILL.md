---
name: release
description: Release assistida do repo (semver pelos commits convencionais, CHANGELOG, PR com prova dos gates) com a tag só por decisão humana. Usar com «/release», ao fechar um marco ou quando a factory pára com `release`.
version: 1.0.0
---
# release

Automatiza o reversível (versão, CHANGELOG, PR) e isola a decisão humana (a tag). Motor: `scripts/kf_release.py`.

## Fluxo

| Passo | Comando | Saída |
|---|---|---|
| 1. Plano | `python -I scripts/kf_release.py plan` | versão proposta e notas do CHANGELOG; só leitura; rc 2 = nada a lançar (parar) |
| 2. Preparar | `python -I scripts/kf_release.py prepare [--gate CMD]...` | ramo `agent/release-x-y-z`, bump do `package.json`, `[Unreleased]` → `[x.y.z]`, gates, push e PR |
| 3. Merge | skill `kf-ship` (ou `pr_fechar.py <nº>`) | merge só com CI verde e o método a permitir |
| 4. Confirmar | mostrar ao {{userName}} versão, PR mergeado e notas; pedir «sim» explícito | sem «sim» parar aqui |
| 5. Publicar | `python -I scripts/kf_release.py publish --confirmo` | tag anotada `vX.Y.Z` empurrada; o workflow `publish.yml` publica com provenance |
| 6. Retomar | factory parada com `release`: `kaizen factory run <projeto> --release-feito` | a factory segue para o marco seguinte |

## Códigos

rc 0 ok · 1 gate vermelho (corrigir e repetir o passo 2) · 2 nada a lançar · 3 sem `--confirmo` · 4 recusado (árvore suja, ramo, versão ou tag existente) · 5 git/gh falhou · 64 uso.

## Proibições

- `--confirmo` só vem do {{userName}}, mesmo em modo auto; nunca o passar por iniciativa própria.
- Nunca `npm publish` local, nunca reescrever nem apagar tags, nunca force push, nunca `--admin`.
- Nunca editar à mão versão ou CHANGELOG para contornar o `plan`.
