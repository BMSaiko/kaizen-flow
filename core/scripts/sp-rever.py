#!/usr/bin/env python3
"""Painel de revisão (`/rever`): um cartão por SP fechado e por rever, veredicto só com o teclado.

Uso:
  python -I scripts/sp-rever.py                 # gera a página, serve em 127.0.0.1 (token no URL) e abre o browser
  python -I scripts/sp-rever.py --listar [--json]   # SPs por rever (slug, projeto, fecho, PR)
  python -I scripts/sp-rever.py --hook          # SessionStart: «N SPs por rever: /rever» (nada se N = 0)

Estado de revisão fora do git: ~/.claude/sp-revisao.json ({slug: {estado, texto, data}}).
Um SP em Done com `date` >= 2026-11-13 sem entrada conta como `pendente`.
O servidor só escuta em loopback, termina com `q`, após 15 min sem pedidos ou ao fim do processo,
e só lê `sp/proofs/<slug>/` e o ficheiro de estado. Stdlib apenas, sem rede.
rc: 0 (o hook nunca falha)
"""
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAIZ = REPO / "knowledge" / "projects" / "kaizen"
ESTADO = Path.home() / ".claude" / "sp-revisao.json"
DESDE = "2026-11-13"
OCIOSO = 15 * 60
MAX_CORPO = 16 * 1024
MAX_TEXTO = 4000
ESTADOS = ("pendente", "ok", "ajustar", "redirecionar")
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
IMG_OK = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMG = 4 * 1024 * 1024


def _frontmatter(path):
    try:
        with open(path, "rb") as f:
            txt = f.read(2048).decode("utf-8", "replace")
    except OSError:
        return {}
    m = re.match(r"---\r?\n(.*?)\r?\n---", txt, re.S)
    fm = {}
    for ln in (m.group(1).splitlines() if m else []):
        k, _, v = ln.partition(":")
        if _ and k.strip() and not ln.startswith((" ", "-")):
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


def _ler_estado(estado):
    try:
        d = json.loads(Path(estado).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _escrever_estado(estado, dados):
    estado = Path(estado)
    import tempfile
    estado.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(estado.parent), prefix=".sp-revisao-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(tmp, estado)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _fechados(raiz):
    """SPs em Done com date >= DESDE: [(slug, projeto, fecho, caminho)] do fecho mais antigo para o mais recente."""
    out = []
    for p in Path(raiz).glob("*/sp/Done/*.md"):
        if p.name == "MOC.md":
            continue
        sufixo = p.stem[-10:]  # data de criação no nome: evita abrir os SPs antigos
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", sufixo) and sufixo < DESDE:
            continue
        fm = _frontmatter(p)
        slug = fm.get("slug") or p.stem
        if (fm.get("date") or "") < DESDE or not SLUG.match(slug):
            continue
        out.append((slug, fm.get("project") or p.parts[-4], fm.get("updated") or fm.get("date"), p))
    out.sort(key=lambda x: (x[2], x[0]))
    return out


def _estado_de(dados, slug):
    e = dados.get(slug)
    return e.get("estado", "pendente") if isinstance(e, dict) else "pendente"


def _provas(caminho, slug):
    pasta = Path(caminho).parent.parent / "proofs" / slug
    try:
        d = json.loads((pasta / "provas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, pasta
    return (d if isinstance(d, dict) else {}), pasta


def por_rever(raiz=RAIZ, estado=ESTADO):
    dados = _ler_estado(estado)
    out = []
    for slug, proj, fecho, p in _fechados(raiz):
        if _estado_de(dados, slug) != "pendente":
            continue
        provas, pasta = _provas(p, slug)
        out.append({"slug": slug, "projeto": proj, "fecho": (fecho or "")[:10], "pr": _pr(provas),
                    "provas": provas, "pasta": str(pasta)})
    return out


def _pr(provas):
    pr = provas.get("pr") if isinstance(provas, dict) else ""
    return pr if isinstance(pr, str) and re.match(r"https?://", pr) else ""


def gravar_veredicto(slug, estado_novo, texto, estado=ESTADO, raiz=RAIZ):
    """Grava o veredicto e devolve a entrada anterior (ou None). ValueError se slug/estado/texto inválidos."""
    if estado_novo not in ESTADOS:
        raise ValueError("estado inválido")
    if not isinstance(slug, str) or not SLUG.match(slug) or slug not in {s for s, *_ in _fechados(raiz)}:
        raise ValueError("slug inválido")
    if not isinstance(texto, str) or len(texto) > MAX_TEXTO:
        raise ValueError("texto inválido")
    dados = _ler_estado(estado)
    anterior = dados.get(slug)
    dados[slug] = {"estado": estado_novo, "texto": texto, "data": date.today().isoformat()}
    _escrever_estado(estado, dados)
    return anterior


def _repor(estado, slug, anterior):
    dados = _ler_estado(estado)
    if anterior is None:
        dados.pop(slug, None)
    else:
        dados[slug] = anterior
    _escrever_estado(estado, dados)


# ---------------------------------------------------------------- página

CSS = """
:root{--bg:#f6f7f9;--fg:#15181d;--mut:#586270;--card:#fff;--bd:#cfd5dd;--ac:#1d5fd6;--ok:#0b6b3a;--bad:#a4161a;--warn:#7a4a00;--warnbg:#fff3d6;--code:#eef1f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--fg:#e8ecf1;--mut:#9aa6b5;--card:#171d25;--bd:#2d3744;--ac:#7fb0ff;--ok:#5fd596;--bad:#ff8a8d;--warn:#ffd28a;--warnbg:#2f2410;--code:#10151c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--card);border-bottom:1px solid var(--bd);padding:10px 16px;display:flex;gap:16px;align-items:center;justify-content:space-between}
main{max-width:920px;margin:0 auto;padding:16px}
article{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:16px;margin:0 0 16px}
article:focus{outline:3px solid var(--ac);outline-offset:2px}
article.atual{border-color:var(--ac)}
h2{font-size:1.1rem;margin:0 0 4px;overflow-wrap:anywhere}.meta{color:var(--mut);font-size:.9rem}
.estado{font-weight:600;border:1px solid var(--bd);border-radius:999px;padding:1px 10px;font-size:.85rem;margin-right:6px}
.auto{background:var(--warnbg);color:var(--warn);border-left:5px solid var(--warn);padding:8px 12px;margin:12px 0;border-radius:4px}
.auto strong{display:block}ul{margin:4px 0;padding-left:22px}
.det{display:none}article.aberto .det{display:block}
.imgs{display:flex;gap:12px;flex-wrap:wrap}figure{flex:1 1 280px;margin:8px 0}figure img{max-width:100%;border:1px solid var(--bd);border-radius:6px;background:#fff}
figcaption{color:var(--mut);font-size:.85rem}
.g{font-family:ui-monospace,Consolas,monospace;font-size:.85rem;overflow-wrap:anywhere}.g.p b{color:var(--ok)}.g.f b{color:var(--bad)}
pre{background:var(--code);padding:8px 10px;border-radius:6px;overflow:auto;font-size:.85rem}
dialog{border:2px solid var(--ac);border-radius:10px;background:var(--card);color:var(--fg);width:min(560px,92vw)}
textarea{width:100%;min-height:120px;background:var(--bg);color:var(--fg);border:1px solid var(--bd);border-radius:6px;padding:8px;font:inherit}
kbd{background:var(--code);border:1px solid var(--bd);border-radius:4px;padding:0 5px;font-size:.85rem}
#aviso{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--ac);padding:6px 14px;border-radius:8px;display:none}
@media (max-width:600px){main{padding:8px}article{padding:12px}figure{flex-basis:100%}header{flex-wrap:wrap}}
"""

JS = """
(function(){
var T=%TOKEN%,cs=[].slice.call(document.querySelectorAll('article')),i=0,dlg=document.getElementById('dlg'),
ta=document.getElementById('texto'),pend=document.getElementById('pend'),ajuda=document.getElementById('ajuda'),av=document.getElementById('aviso'),pa=null,ult=null;
var SIM={ok:'\\u2714 ok',ajustar:'\\u270E ajustar',redirecionar:'\\u21AA redirecionar',pendente:'\\u25CB pendente'};
function aviso(t){av.textContent=t;av.style.display='block';clearTimeout(aviso.t);aviso.t=setTimeout(function(){av.style.display='none'},2500)}
function conta(){var n=0;cs.forEach(function(c){if(c.dataset.estado==='pendente')n++});pend.textContent=n+' por rever'}
function ir(n){if(!cs.length)return;i=Math.max(0,Math.min(cs.length-1,n));cs.forEach(function(c,k){c.classList.toggle('atual',k===i)});cs[i].focus();cs[i].scrollIntoView({block:'nearest'})}
function marca(c,e){c.dataset.estado=e;c.querySelector('.estado').textContent=SIM[e];conta()}
function post(p,b,cb){var x=new XMLHttpRequest();x.open('POST',p+'?t='+encodeURIComponent(T));x.setRequestHeader('Content-Type','application/json');
x.onload=function(){var r={};try{r=JSON.parse(x.responseText)}catch(e){}cb(x.status,r)};x.onerror=function(){aviso('Servidor terminou')};x.send(JSON.stringify(b))}
function abre(e){if(!cs.length)return;pa=e;document.getElementById('dtit').textContent=SIM[e]+' \\u00B7 '+cs[i].dataset.slug;ta.value='';dlg.showModal();ta.focus()}
function envia(){var c=cs[i],e=pa;post('/veredicto',{slug:c.dataset.slug,estado:e,texto:ta.value},function(s,r){
if(s===200){ult={c:c,antes:c.dataset.estado};marca(c,e);dlg.close();aviso('Gravado: '+SIM[e]);ir(i+1)}else aviso('Erro '+s+(r.erro?': '+r.erro:''))})}
function desfaz(){post('/desfazer',{},function(s,r){if(s===200&&ult){marca(ult.c,'pendente');aviso('Desfeito');ult=null}else aviso('Nada para desfazer')})}
document.addEventListener('keydown',function(ev){
if(dlg.open){if(ev.key==='Enter'&&ev.ctrlKey){ev.preventDefault();envia()}else if(ev.key==='Escape'){ev.preventDefault();dlg.close()}return}
if(ajuda.open){if(ev.key==='Escape'||ev.key==='?'){ajuda.close()}return}
if(ev.ctrlKey||ev.altKey||ev.metaKey)return;var k=ev.key;
if(k==='j'){ir(i+1)}else if(k==='k'){ir(i-1)}else if(k==='Enter'){ev.preventDefault();if(cs[i])cs[i].classList.toggle('aberto')}
else if(k==='o'){abre('ok')}else if(k==='a'){abre('ajustar')}else if(k==='r'){abre('redirecionar')}
else if(k==='u'){desfaz()}else if(k==='?'){ajuda.showModal()}else if(k==='q'){post('/sair',{},function(){document.body.innerHTML='<main><p>Servidor terminado. Pode fechar o separador.</p></main>'})}
});
cs.forEach(function(c,k){c.addEventListener('focus',function(){i=k;cs.forEach(function(d,n){d.classList.toggle('atual',n===k)})})});
conta();ir(0)})();
"""

AJUDA = ("<dialog id=ajuda aria-label='Ajuda'><h2>Teclas</h2><ul>"
         "<li><kbd>j</kbd>/<kbd>k</kbd> cartão seguinte/anterior</li><li><kbd>Enter</kbd> expande ou recolhe</li>"
         "<li><kbd>o</kbd> ok · <kbd>a</kbd> ajustar · <kbd>r</kbd> redirecionar (abrem a caixa de texto)</li>"
         "<li><kbd>Ctrl</kbd>+<kbd>Enter</kbd> envia · <kbd>Esc</kbd> cancela</li><li><kbd>u</kbd> desfaz o último veredicto</li>"
         "<li><kbd>q</kbd> termina o servidor · <kbd>?</kbd> esta ajuda</li></ul></dialog>")


def _e(x):
    import html
    return html.escape(str(x), quote=True)


def _lista(itens):
    return "<ul>" + "".join(f"<li>{_e(i)}</li>" for i in itens) + "</ul>" if itens else ""


def _imagem(pasta, img):
    if not isinstance(img, dict) or not isinstance(img.get("ficheiro"), str):
        return ""
    nome = img["ficheiro"]
    if nome != Path(nome).name or Path(nome).suffix.lower() not in IMG_OK:
        return ""
    p = Path(pasta) / nome
    try:
        if p.stat().st_size > MAX_IMG:
            return ""
        raw = p.read_bytes()
    except OSError:
        return ""
    import base64
    mime = IMG_OK[p.suffix.lower()]
    b64 = base64.b64encode(raw).decode("ascii")
    return (f'<figure><img alt="{_e(img.get("legenda", nome))}" src="data:{mime};base64,{b64}">'
            f'<figcaption>{_e(img.get("legenda", nome))}</figcaption></figure>')


def _cartao(c):
    p = c["provas"]
    pr = f' · <a href="{_e(c["pr"])}" rel="noopener noreferrer" target="_blank">PR ↗</a>' if c["pr"] else ""
    h = [f'<article tabindex="0" data-slug="{_e(c["slug"])}" data-estado="pendente">',
         f'<h2><span class="estado">○ pendente</span>{_e(c["slug"])}</h2>',
         f'<div class="meta">{_e(c["projeto"])} · fecho {_e(c["fecho"])}{pr}</div>']
    if p.get("decisoes_auto"):
        h.append('<div class="auto"><strong>⚑ Decisões tomadas sem o user</strong>' + _lista(p["decisoes_auto"]) + "</div>")
    if p.get("objetivo"):
        h.append(f'<p><b>Objetivo.</b> {_e(p["objetivo"])}</p>')
    if not p:
        h.append("<p>Sem pacote de provas (<code>provas.json</code>) para este SP.</p>")
    h.append('<div class="det">')
    if p.get("feito"):
        h.append("<b>Feito</b>" + _lista(p["feito"]))
    imgs = "".join(_imagem(c["pasta"], i) for i in p.get("imagens") or [])
    if imgs:
        h.append(f'<div class="imgs">{imgs}</div>')
    gates = [g for g in p.get("gates") or [] if isinstance(g, dict)]
    if gates:
        h.append("<b>Gates</b>")
        for g in gates:
            ok = g.get("rc") == 0
            h.append(f'<div class="g {"p" if ok else "f"}"><b>{"✔ PASSOU" if ok else "✘ FALHOU"}</b> rc {_e(g.get("rc"))} · {_e(g.get("cmd", ""))}</div>')
    cr = p.get("criterios") if isinstance(p.get("criterios"), dict) else {}
    if cr.get("cumpridos") or cr.get("por_cumprir"):
        h.append("<b>Critérios</b><ul>" + "".join(f"<li>☑ {_e(x)}</li>" for x in cr.get("cumpridos") or [])
                 + "".join(f"<li>☐ {_e(x)}</li>" for x in cr.get("por_cumprir") or []) + "</ul>")
    for chave, tit in (("experimentar", "Experimentar"), ("reverter", "Reverter")):
        if p.get(chave):
            h.append(f"<b>{tit}</b><pre>" + _e("\n".join(map(str, p[chave]))) + "</pre>")
    h.append("</div></article>")
    return "".join(h)


def pagina(cartoes, token):
    corpo = "".join(_cartao(c) for c in cartoes) or "<p>Nada por rever.</p>"
    js = JS.replace("%TOKEN%", json.dumps(token))
    return ('<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>Rever SPs</title><style>{CSS}</style></head><body>"
            '<header><strong>/rever</strong><span id="pend" aria-live="polite"></span><span class="meta"><kbd>?</kbd> ajuda</span></header>'
            f"<main>{corpo}</main>{AJUDA}"
            '<dialog id="dlg"><form method="dialog" onsubmit="return false"><h2 id="dtit"></h2>'
            '<label for="texto">Nota (opcional)</label><textarea id="texto" maxlength="' + str(MAX_TEXTO) + '"></textarea>'
            '<p class="meta"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> envia · <kbd>Esc</kbd> cancela</p></form></dialog>'
            f'<div id="aviso" role="status"></div><script>{js}</script></body></html>')


# ---------------------------------------------------------------- servidor

def criar_servidor(porta, token, raiz=RAIZ, estado=ESTADO):
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", porta), _handler())
    srv.token, srv.raiz, srv.estado = token, Path(raiz), Path(estado)
    srv.fechar, srv.ultimo, srv.pedido = False, None, time.time()
    srv.cartoes = por_rever(srv.raiz, srv.estado)
    srv.servidos = {c["slug"] for c in srv.cartoes}
    return srv


_HANDLER = []


def _handler():
    if not _HANDLER:
        _HANDLER.append(_definir_handler())
    return _HANDLER[0]


def _definir_handler():
    import hmac
    from http.server import BaseHTTPRequestHandler

    class _Handler(BaseHTTPRequestHandler):
        timeout = 5  # uma ligação muda não pode prender o servidor single-thread

        def log_message(self, *a):
            pass

        def _resp(self, code, corpo, tipo="application/json; charset=utf-8"):
            b = corpo.encode("utf-8") if isinstance(corpo, str) else corpo
            self.send_response(code)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(b)

        def _json(self, code, obj):
            self._resp(code, json.dumps(obj, ensure_ascii=False))

        def _autorizado(self):
            s = self.server
            self.server.pedido = time.time()
            porta = s.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{porta}", f"localhost:{porta}"):
                self._json(403, {"erro": "host"})
                return False
            t = (re.search(r"[?&]t=([^&]*)", self.path) or [None, ""])[1]
            if not hmac.compare_digest(t.encode(), s.token.encode()):
                self._json(403, {"erro": "token"})
                return False
            return True

        def do_GET(self):
            if not self._autorizado():
                return
            if self.path.split("?")[0] != "/":
                return self._json(404, {"erro": "nao existe"})
            s = self.server
            s.cartoes = por_rever(s.raiz, s.estado)
            s.servidos = {c["slug"] for c in s.cartoes}
            self._resp(200, pagina(s.cartoes, s.token), "text/html; charset=utf-8")

        def _corpo(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_CORPO:
                self._json(413, {"erro": "corpo grande"})
                return None
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                d = None
            if not isinstance(d, dict):
                self._json(400, {"erro": "json"})
                return None
            return d

        def do_POST(self):
            if not self._autorizado():
                return
            s = self.server
            rota = self.path.split("?")[0]
            d = self._corpo()
            if d is None:
                return
            if rota == "/sair":
                s.fechar = True
                return self._json(200, {"ok": True})
            if rota == "/desfazer":
                if not s.ultimo:
                    return self._json(409, {"erro": "nada para desfazer"})
                slug, anterior = s.ultimo
                _repor(s.estado, slug, anterior)
                s.ultimo = None
                return self._json(200, {"slug": slug, "estado": "pendente"})
            if rota == "/veredicto":
                slug, est, texto = d.get("slug"), d.get("estado"), d.get("texto", "")
                if slug not in s.servidos or est not in ESTADOS[1:]:
                    return self._json(400, {"erro": "slug ou estado inválido"})
                try:
                    anterior = gravar_veredicto(slug, est, texto, s.estado, s.raiz)
                except ValueError as ex:
                    return self._json(400, {"erro": str(ex)})
                s.ultimo = (slug, anterior)
                return self._json(200, {"slug": slug, "estado": est})
            self._json(404, {"erro": "nao existe"})

    return _Handler


def servir(srv, ocioso=OCIOSO):
    srv.timeout = 0.2
    srv.pedido = time.time()
    while not srv.fechar and time.time() - srv.pedido < ocioso:
        srv.handle_request()


# ---------------------------------------------------------------- saídas

def diaria_linhas(dia, raiz=RAIZ, estado=ESTADO):
    """Linhas da diária: SPs fechados em `dia` com o estado de revisão."""
    dados = _ler_estado(estado)
    return [f"`{slug}` ({proj}): revisão {_estado_de(dados, slug)}"
            for slug, proj, fecho, _ in _fechados(raiz) if (fecho or "").startswith(dia)]


def listar(cartoes, como_json=False):
    if como_json:
        print(json.dumps([{k: c[k] for k in ("slug", "projeto", "fecho", "pr")} for c in cartoes], ensure_ascii=False, indent=2))
    else:
        for c in cartoes:
            print(f'{c["slug"]}  {c["projeto"]}  {c["fecho"]}  {c["pr"] or "-"}')
        print(f"{len(cartoes)} por rever")


def _hook(argv):
    """Caminho rápido do SessionStart (<200 ms): sem argparse nem http.server; nunca falha."""
    def opt(nome, defeito):
        return argv[argv.index(nome) + 1] if nome in argv and argv.index(nome) + 1 < len(argv) else defeito
    try:
        n = len(por_rever(opt("--root", RAIZ), opt("--estado", ESTADO)))
        if n:
            print(f"{n} SPs por rever: /rever")
    except Exception:  # o hook nunca bloqueia
        pass
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--hook" in argv:
        return _hook(argv)
    import argparse
    import secrets
    import webbrowser
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", action="store_true", help="SessionStart")
    ap.add_argument("--root", default=str(RAIZ), help=argparse.SUPPRESS)
    ap.add_argument("--estado", default=str(ESTADO), help=argparse.SUPPRESS)
    ap.add_argument("--porta", type=int, default=0)
    ap.add_argument("--sem-browser", action="store_true")
    a = ap.parse_args(argv)
    if a.listar:
        listar(por_rever(a.root, a.estado), a.json)
        return 0
    srv = criar_servidor(a.porta, secrets.token_urlsafe(24), a.root, a.estado)
    if not srv.cartoes:
        srv.server_close()
        print("Nada por rever.")
        return 0
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={srv.token}"
    print(f"{len(srv.cartoes)} por rever: {url}\n(tecla q ou 15 min sem pedidos termina)")
    if not a.sem_browser:
        webbrowser.open(url)
    try:
        servir(srv)
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
