#!/usr/bin/env python3
"""Núcleo do design system por projeto: tokens DTCG (W3C Design Tokens), contraste WCAG 2.2, geração e exportação.

Formato de `design/tokens.json` (DTCG, `$type`/`$value`/`{alias}`):
  color.palette.<escala>.<passo>  cores cruas (#rgb ou #rrggbb)
  color.light.<papel> / color.dark.<papel>  papéis semânticos por tema (alias para a paleta)
  space.<n>, radius.<n>, shadow.<n>, font.*, motion.*, breakpoint.*
  $extensions.kaizen.contrast  pares [{"fg","bg","kind":"text|ui"}] verificados (texto 4.5:1, UI 3:1)

Uso: módulo (`import ds_core`); os comandos são ds-init.py, ds-validate.py e ds-export.py
rc: n/a
"""
import re
import contextlib

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
HEXA_RE = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")  # sombras admitem alfa
ALIAS_RE = re.compile(r"^\{([^{}]+)\}$")
DIM_RE = re.compile(r"^-?\d+(?:\.\d+)?(px|rem)$")
DUR_RE = re.compile(r"^\d+(?:\.\d+)?(ms|s)$")
TIPOS = {"color", "dimension", "fontFamily", "fontWeight", "duration", "cubicBezier", "number", "shadow"}
MIN_CONTRASTE = {"text": 4.5, "ui": 3.0}
TEMAS = ("light", "dark")
PASSOS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900)


# --- leitura e resolução ------------------------------------------------------

def folhas(no, caminho=(), tipo=None):
    """Gera (caminho, tipo herdado, dict do token) para cada token folha."""
    if not isinstance(no, dict):
        return
    tipo = no.get("$type", tipo)
    if "$value" in no:
        yield caminho, tipo, no
        return
    for chave, filho in no.items():
        if not chave.startswith("$"):
            yield from folhas(filho, (*caminho, chave), tipo)


def obter(raiz, caminho):
    """Token (dict com $value) em `caminho` pontuado, ou None."""
    no = raiz
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            return None
        no = no[parte]
    return no if isinstance(no, dict) and "$value" in no else None


def resolver(valor, raiz, vistos=()):
    """Resolve `{alias}` recursivamente (também dentro de listas e objetos). ValueError em alias partido ou ciclo."""
    if isinstance(valor, str):
        m = ALIAS_RE.match(valor)
        if not m:
            return valor
        ref = m.group(1)
        if ref in vistos:
            raise ValueError(f"ciclo de alias: {' -> '.join((*vistos, ref))}")
        alvo = obter(raiz, ref)
        if alvo is None:
            raise ValueError(f"alias partido: {{{ref}}}")
        return resolver(alvo["$value"], raiz, (*vistos, ref))
    if isinstance(valor, list):
        return [resolver(v, raiz, vistos) for v in valor]
    if isinstance(valor, dict):
        return {k: resolver(v, raiz, vistos) for k, v in valor.items()}
    return valor


def px(valor):
    """Valor de dimensão ('4px', '0.5rem' ou {value, unit}) em px (rem = 16px); None se inválido."""
    if isinstance(valor, dict):
        valor = f"{valor.get('value')}{valor.get('unit')}"
    if not isinstance(valor, str):
        return None
    m = DIM_RE.match(valor)
    if not m:
        return None
    n = float(valor[: -len(m.group(1))])
    return n * 16 if m.group(1) == "rem" else n


# --- contraste (WCAG 2.2, 1.4.3 e 1.4.11) -------------------------------------

def rgb(hex_):
    h = hex_.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminancia(hex_):
    def canal(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    la, lb = luminancia(a), luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


# --- validação ----------------------------------------------------------------

def _valida_valor(tipo, v):
    """Mensagem de erro para um valor já resolvido, ou None."""
    if tipo == "color":
        return None if isinstance(v, str) and HEX_RE.match(v) else f"cor inválida: {v!r}"
    if tipo == "dimension":
        return None if px(v) is not None else f"dimensão inválida: {v!r}"
    if tipo == "duration":
        return None if isinstance(v, str) and DUR_RE.match(v) else f"duração inválida: {v!r}"
    if tipo == "fontFamily":
        ok = isinstance(v, str) or (isinstance(v, list) and v and all(isinstance(x, str) for x in v))
        return None if ok else f"fontFamily inválida: {v!r}"
    if tipo == "fontWeight":
        return None if isinstance(v, (int, float)) and not isinstance(v, bool) and 1 <= v <= 1000 else f"fontWeight inválido: {v!r}"
    if tipo == "number":
        return None if isinstance(v, (int, float)) and not isinstance(v, bool) else f"número inválido: {v!r}"
    if tipo == "cubicBezier":
        ok = isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v) and 0 <= v[0] <= 1 and 0 <= v[2] <= 1
        return None if ok else f"cubicBezier inválida: {v!r}"
    if tipo == "shadow":
        for s in (v if isinstance(v, list) else [v]):
            if not isinstance(s, dict) or not {"color", "offsetX", "offsetY", "blur", "spread"} <= set(s):
                return "sombra precisa de color, offsetX, offsetY, blur e spread"
            if not (isinstance(s["color"], str) and HEXA_RE.match(s["color"])) or any(px(s[k]) is None for k in ("offsetX", "offsetY", "blur", "spread")):
                return f"sombra inválida: {s!r}"
        return None
    return f"tipo desconhecido: {tipo!r}"


def validar(raiz):
    """Lista de falhas `[categoria] caminho: mensagem`; vazia se o design system está válido."""
    falhas = []
    if not isinstance(raiz, dict):
        return ["[schema] (raiz): o JSON tem de ser um objeto"]
    n_folhas = 0
    for caminho, tipo, tok in folhas(raiz):
        n_folhas += 1
        nome = ".".join(caminho)
        if tipo is None:
            falhas.append(f"[schema] {nome}: sem $type (nem herdado)")
            continue
        if tipo not in TIPOS:
            falhas.append(f"[schema] {nome}: tipo desconhecido {tipo!r}")
            continue
        try:
            v = resolver(tok["$value"], raiz)
        except ValueError as e:
            falhas.append(f"[alias] {nome}: {e}")
            continue
        erro = _valida_valor(tipo, v)
        if erro:
            falhas.append(f"[schema] {nome}: {erro}")
    if n_folhas == 0:
        falhas.append("[schema] (raiz): sem tokens")
    falhas += _valida_contraste(raiz)
    falhas += _valida_escalas(raiz)
    return falhas


def _valida_contraste(raiz):
    ext = raiz.get("$extensions", {}).get("kaizen", {}) if isinstance(raiz.get("$extensions"), dict) else {}
    pares = ext.get("contrast") if isinstance(ext, dict) else None
    if not isinstance(pares, list) or not pares:
        return ["[contraste] $extensions.kaizen.contrast: sem pares declarados"]
    falhas = []
    for i, par in enumerate(pares):
        rot = f"$extensions.kaizen.contrast[{i}]"
        if not isinstance(par, dict) or not isinstance(par.get("fg"), str) or not isinstance(par.get("bg"), str):
            falhas.append(f"[contraste] {rot}: par precisa de fg e bg")
            continue
        kind = par.get("kind", "text")
        if kind not in MIN_CONTRASTE:
            falhas.append(f"[contraste] {rot}: kind {kind!r} (text|ui)")
            continue
        cores = []
        for lado in ("fg", "bg"):
            tok = obter(raiz, par[lado])
            if tok is None:
                falhas.append(f"[contraste] {rot}: token inexistente {par[lado]}")
                break
            try:
                c = resolver(tok["$value"], raiz)
            except ValueError as e:
                falhas.append(f"[contraste] {rot}: {e}")
                break
            if not (isinstance(c, str) and HEX_RE.match(c)):
                falhas.append(f"[contraste] {rot}: {par[lado]} não é uma cor")
                break
            cores.append(c)
        else:
            r = contraste(*cores)
            minimo = MIN_CONTRASTE[kind]
            if r < minimo:
                falhas.append(f"[contraste] {par['fg']} sobre {par['bg']}: {r:.2f}:1 < {minimo}:1 ({kind})")
    return falhas


def _valores(raiz, prefixo):
    """[(nome, valor resolvido)] dos tokens sob `prefixo` (ordem do ficheiro), ignorando os inválidos."""
    base = obter_grupo(raiz, prefixo)
    saida = []
    for caminho, _t, tok in folhas(base, tuple(prefixo.split("."))):
        with contextlib.suppress(ValueError):
            saida.append((".".join(caminho), resolver(tok["$value"], raiz)))
    return saida


def obter_grupo(raiz, caminho):
    no = raiz
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            return {}
        no = no[parte]
    return no


def _valida_escalas(raiz):
    falhas = []
    esp = [(n, px(v)) for n, v in _valores(raiz, "space")]
    for n, p in esp:
        if p is not None and p % 4:
            falhas.append(f"[escala] {n}: {p:g}px não é múltiplo de 4")
    for pref in ("space", "font.size", "breakpoint"):
        vals = [(n, px(v)) for n, v in _valores(raiz, pref)]
        vals = [(n, p) for n, p in vals if p is not None]
        for (_a, pa), (b, pb) in zip(vals, vals[1:]):
            if pb <= pa:
                falhas.append(f"[escala] {b}: {pb:g}px não é maior que o anterior ({pa:g}px)")
    return falhas


# --- geração a partir de uma cor base -------------------------------------------

def _misturar(a, b, t):
    ra, rb = rgb(a), rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


def escala(base, neutra=False):
    """Escala 50..900: claros misturados com branco, escuros com preto; o 500 é a cor base."""
    base = "#" + "".join(c * 2 for c in base.lstrip("#")) if len(base.lstrip("#")) == 3 else "#" + base.lstrip("#").lower()
    mistura = {50: ("#ffffff", .93), 100: ("#ffffff", .85), 200: ("#ffffff", .70), 300: ("#ffffff", .50), 400: ("#ffffff", .25),
               500: None, 600: ("#000000", .15), 700: ("#000000", .30), 800: ("#000000", .45), 900: ("#000000", .60)}
    return {p: (base if m is None else _misturar(base, m[0], m[1])) for p, m in mistura.items()}


def _escolhe(escala_, contra, minimo, preferidos):
    """Primeiro passo de `preferidos` com contraste >= minimo contra `contra`; senão o de maior contraste."""
    for p in preferidos:
        if contraste(escala_[p], contra) >= minimo:
            return p
    return max(preferidos, key=lambda p: contraste(escala_[p], contra))


def gerar(primaria="#2563eb", neutra="#64748b"):
    """Tokens DTCG completos (dict) a partir de uma cor primária e de uma neutra."""
    if not HEX_RE.match(primaria) or not HEX_RE.match(neutra):
        raise ValueError("cores base têm de ser #rgb ou #rrggbb")
    br, ne = escala(primaria), escala(neutra)
    branco, preto = "#ffffff", "#000000"
    cor = lambda v: {"$type": "color", "$value": v}  # noqa: E731
    al = lambda esc, p: cor(f"{{color.palette.{esc}.{p}}}")  # noqa: E731

    pal = {"brand": {str(p): cor(c) for p, c in br.items()}, "neutral": {str(p): cor(c) for p, c in ne.items()},
           "white": cor(branco), "black": cor(preto),
           "success": cor("#15803d"), "warning": cor("#b45309"), "danger": cor("#b91c1c"), "info": cor("#1d4ed8")}

    def tema(claro):
        fundo = branco if claro else ne[900]
        sup = ne[50] if claro else _misturar(ne[900], branco, .06)
        # papéis, com o passo da escala escolhido para cumprir o contraste exigido
        txt = _escolhe(ne, fundo, 7, (900, 800) if claro else (50, 100))
        mut = _escolhe(ne, fundo, 4.5, (600, 700, 800, 900) if claro else (400, 300, 200, 100))
        bor = _escolhe(ne, fundo, 3, (400, 500, 600, 700, 800) if claro else (500, 400, 300, 600, 700))
        pri = _escolhe(br, fundo, 3, (500, 600, 700, 800, 900) if claro else (500, 400, 300, 200, 100))
        sobre = branco if contraste(br[int(pri)], branco) >= contraste(br[int(pri)], preto) else preto
        papeis = {
            "bg": cor("{color.palette.white}") if claro else al("neutral", 900),
            "surface": cor(sup),
            "text": al("neutral", txt), "text-muted": al("neutral", mut),
            "border": al("neutral", bor),
            "primary": al("brand", pri),
            "on-primary": cor("{color.palette.white}" if sobre == branco else "{color.palette.black}"),
            "focus": al("brand", pri),
        }
        for estado in ("success", "warning", "danger", "info"):
            papeis[estado] = cor(f"{{color.palette.{estado}}}") if claro else cor(_misturar(pal[estado]["$value"], branco, .45))
        return papeis

    claro, escuro = tema(True), tema(False)
    # `surface` e cores de estado no escuro são valores derivados: o contraste é verificado abaixo
    pares = []
    for t in ("light", "dark"):
        pares += [{"fg": f"color.{t}.text", "bg": f"color.{t}.bg", "kind": "text"},
                  {"fg": f"color.{t}.text", "bg": f"color.{t}.surface", "kind": "text"},
                  {"fg": f"color.{t}.text-muted", "bg": f"color.{t}.bg", "kind": "text"},
                  {"fg": f"color.{t}.on-primary", "bg": f"color.{t}.primary", "kind": "text"},
                  {"fg": f"color.{t}.border", "bg": f"color.{t}.bg", "kind": "ui"},
                  {"fg": f"color.{t}.focus", "bg": f"color.{t}.bg", "kind": "ui"},
                  {"fg": f"color.{t}.primary", "bg": f"color.{t}.bg", "kind": "ui"}]
        pares += [{"fg": f"color.{t}.{e}", "bg": f"color.{t}.bg", "kind": "text"} for e in ("success", "warning", "danger", "info")]

    dim = lambda v: {"$type": "dimension", "$value": v}  # noqa: E731
    sombra = lambda y, b, a: {"$type": "shadow", "$value": {"color": a, "offsetX": "0px", "offsetY": f"{y}px", "blur": f"{b}px", "spread": "0px"}}  # noqa: E731
    return {
        "$description": "Design tokens (W3C DTCG). Gerado por ds-init.py; editar à mão e validar com ds-validate.py.",
        "color": {"palette": pal, "light": claro, "dark": escuro},
        "space": {str(i): dim(f"{p}px") for i, p in enumerate((0, 4, 8, 12, 16, 24, 32, 48, 64))},
        "radius": {"sm": dim("4px"), "md": dim("8px"), "lg": dim("16px"), "full": dim("9999px")},
        "shadow": {"sm": sombra(1, 2, "#00000026"), "md": sombra(4, 12, "#00000026"), "lg": sombra(12, 32, "#00000033")},
        "font": {
            "family": {"sans": {"$type": "fontFamily", "$value": ["Inter", "system-ui", "sans-serif"]},
                       "mono": {"$type": "fontFamily", "$value": ["ui-monospace", "Menlo", "monospace"]}},
            "size": {k: dim(v) for k, v in (("xs", "12px"), ("sm", "14px"), ("base", "16px"), ("lg", "20px"), ("xl", "24px"), ("2xl", "32px"), ("3xl", "40px"))},
            "weight": {"regular": {"$type": "fontWeight", "$value": 400}, "medium": {"$type": "fontWeight", "$value": 500}, "bold": {"$type": "fontWeight", "$value": 700}},
            "line-height": {"tight": {"$type": "number", "$value": 1.25}, "normal": {"$type": "number", "$value": 1.5}},
        },
        "motion": {"duration": {"fast": {"$type": "duration", "$value": "100ms"}, "base": {"$type": "duration", "$value": "200ms"}, "slow": {"$type": "duration", "$value": "400ms"}},
                   "easing": {"standard": {"$type": "cubicBezier", "$value": [0.2, 0, 0, 1]}}},
        "breakpoint": {"sm": dim("640px"), "md": dim("768px"), "lg": dim("1024px"), "xl": dim("1280px")},
        "$extensions": {"kaizen": {"contrast": pares}},
    }


# --- exportação -----------------------------------------------------------------

def _css_valor(tipo, v):
    if tipo == "fontFamily":
        return ", ".join(f if re.fullmatch(r"[\w-]+", f) else f'"{f}"' for f in (v if isinstance(v, list) else [v]))
    if tipo == "cubicBezier":
        return "cubic-bezier(" + ", ".join(f"{x:g}" for x in v) + ")"
    if tipo == "shadow":
        return ", ".join(f"{s['offsetX']} {s['offsetY']} {s['blur']} {s['spread']} {s['color']}" for s in (v if isinstance(v, list) else [v]))
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def variaveis(raiz):
    """({nome css: valor} sem tema, {tema: {nome: valor}}) com valores resolvidos."""
    comuns, temas = {}, {t: {} for t in TEMAS}
    for caminho, tipo, tok in folhas(raiz):
        if caminho[:2] == ("color", "palette"):
            continue
        valor = _css_valor(tipo, resolver(tok["$value"], raiz))
        if len(caminho) > 2 and caminho[0] == "color" and caminho[1] in TEMAS:
            temas[caminho[1]]["--color-" + "-".join(caminho[2:])] = valor
        else:
            comuns["--" + "-".join(caminho)] = valor
    return comuns, temas


def css(raiz):
    """tokens.css: :root com tema claro, `prefers-color-scheme: dark` e `[data-theme]` explícitos."""
    comuns, temas = variaveis(raiz)
    bloco = lambda sel, d, ind="": f"{ind}{sel} {{\n" + "".join(f"{ind}  {k}: {v};\n" for k, v in d.items()) + f"{ind}}}\n"  # noqa: E731
    return ("/* Gerado por ds-export.py a partir de design/tokens.json: não editar. */\n"
            + bloco(":root", {**comuns, **temas["light"]}) + "\n"
            + "@media (prefers-color-scheme: dark) {\n" + bloco(":root:not([data-theme=\"light\"])", temas["dark"], "  ") + "}\n\n"
            + bloco(":root[data-theme=\"dark\"]", temas["dark"]) + bloco(":root[data-theme=\"light\"]", temas["light"]))


def tailwind(raiz):
    """Preset Tailwind (CommonJS) que aponta para as variáveis CSS."""
    import json
    comuns, temas = variaveis(raiz)
    grupo = lambda pref: {k[len(pref):]: f"var({k})" for k in comuns if k.startswith(pref)}  # noqa: E731
    cores = {k[len("--color-"):]: f"var({k})" for k in temas["light"]}
    familia = {k: [x.strip().strip('"') for x in comuns[f"--font-family-{k}"].split(",")] for k in (n[len("--font-family-"):] for n in comuns if n.startswith("--font-family-"))}
    preset = {"theme": {"extend": {
        "colors": cores,
        "spacing": grupo("--space-"),
        "borderRadius": grupo("--radius-"),
        "boxShadow": grupo("--shadow-"),
        "fontFamily": familia,
        "fontSize": grupo("--font-size-"),
        "fontWeight": grupo("--font-weight-"),
        "screens": {k[len("--breakpoint-"):]: v for k, v in comuns.items() if k.startswith("--breakpoint-")},
        "transitionDuration": {k[len("--motion-duration-"):]: v for k, v in comuns.items() if k.startswith("--motion-duration-")},
    }}}
    return ("// Gerado por ds-export.py a partir de design/tokens.json: não editar.\n"
            f"module.exports = {json.dumps(preset, indent=2)};\n")
