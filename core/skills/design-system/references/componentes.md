# Checklist de componente

Para cada componente em `DESIGN.md`:

- [ ] Finalidade numa frase; quando NÃO usar.
- [ ] Variantes (primário, secundário, fantasma, destrutivo...) e tamanhos, só com tokens.
- [ ] Estados: repouso, hover, foco visível, ativo, desativado, erro, a carregar, vazio.
- [ ] Tokens usados (papéis de cor, `space.*`, `radius.*`, `font.*`); nenhum valor solto.
- [ ] Pares de contraste novos em `$extensions.kaizen.contrast`.
- [ ] Teclado: ordem de foco, atalhos, Esc para fechar; sem armadilhas de foco.
- [ ] Semântica: elemento nativo primeiro; ARIA só onde o nativo não chega; nome acessível.
- [ ] Alvo de toque >= 24x24px (WCAG 2.2, 2.5.8).
- [ ] Movimento: `motion.duration.*`; respeitar `prefers-reduced-motion`.
- [ ] Responsivo pelos `breakpoint.*`, do mais pequeno para o maior.
