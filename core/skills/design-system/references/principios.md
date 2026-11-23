# Princípios e formato dos tokens

## Formato (W3C DTCG)
Cada token: `{"$type": "...", "$value": ...}`; `$type` herda do grupo. Alias: `"{color.palette.brand.600}"`. Tipos aceites: `color` (`#rgb`/`#rrggbb`), `dimension` (`"8px"`, `"0.5rem"` ou `{value, unit}`), `fontFamily`, `fontWeight`, `duration` (`"200ms"`), `cubicBezier` (4 números), `number`, `shadow` (objeto ou lista com `color`, `offsetX`, `offsetY`, `blur`, `spread`; a cor admite alfa `#rrggbbaa`).

## Estrutura
- `color.palette.*`: valores crus (escalas `brand` e `neutral` 50..900, estados). Só os papéis a referenciam.
- `color.light.*` e `color.dark.*`: papéis (`bg`, `surface`, `text`, `text-muted`, `border`, `primary`, `on-primary`, `focus`, `success`, `warning`, `danger`, `info`). O código usa só estes.
- `space.*` (4/8: 0, 4, 8, 12, 16, 24, 32, 48, 64), `radius.*`, `shadow.*`, `font.{family,size,weight,line-height}.*`, `motion.{duration,easing}.*`, `breakpoint.*`.
- `$extensions.kaizen.contrast`: lista de `{"fg": "caminho.token", "bg": "caminho.token", "kind": "text|ui"}`.

## Princípios
1. Um valor, um sítio: o JSON manda, o CSS e o preset são gerados.
2. Papéis, não cores: trocar de marca é mudar a paleta, não os componentes.
3. Escalas fechadas: sem valores fora da escala; precisar de um novo é decisão de design, regista-se no token.
4. Tema escuro é de primeira classe: cada papel existe nos dois temas e cada par é verificado nos dois.
5. Nada decorativo que quebre contraste, foco ou movimento reduzido.
