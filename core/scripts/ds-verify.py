#!/usr/bin/env python3
"""Verifica a UI contra o design system: a11y (axe, WCAG 2.2 AA), screenshots em 3 breakpoints vs baselines e orçamento Lighthouse.

Config em `kaizen.config.json` do projeto-alvo:
  "design": {"startCmd": "npm run dev", "url": "http://localhost:5173", "rotas": ["/", "/sobre"],
             "limiarDiff": 0.01, "breakpoints": {"sm": 640, "md": 768, "xl": 1280},
             "lighthouse": {"cmd": "npx lighthouse {url} --output=json --quiet --chrome-flags=--headless", "minPerformance": 0.8}}
Playwright e `@axe-core/playwright` são ferramentas de dev do projeto-alvo (nunca deste pacote). Sem browser ou sem
estas ferramentas: rc 3 com aviso, nunca verde. Baselines em `design/baselines/`; só `--atualizar-baselines` as altera
(registado no SP com `--sp`). Relatório em `design/relatorio.json`.

Uso: python -I scripts/ds-verify.py [--dir D] [--atualizar-baselines] [--sp SP.md] [--prova DIR]
rc: 0 ok · 1 violações sérias/críticas, diff acima do limiar, sem baseline ou orçamento falhado · 2 uso/config · 3 sem browser (não verificado)
"""
import argparse
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds_core  # noqa: E402
from painel_backend import run_hidden  # noqa: E402

GRAVES = ("serious", "critical")
LIMIAR_DEFEITO = 0.01
BP_FALLBACK = {"sm": 640, "md": 768, "xl": 1280}
DRIVER = Path(__file__).with_name("ds_verify_driver.js")


def slug(rota):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", rota).strip("-").lower()
    return s or "home"


# --- PNG (stdlib) -------------------------------------------------------------

def _decodificar(dados):
    """(largura, altura, bytes por pixel, linhas desfiltradas) de um PNG 8-bit sem interlace."""
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é PNG")
    pos, idat, ihdr = 8, b"", None
    while pos < len(dados):
        n, t = struct.unpack(">I4s", dados[pos:pos + 8])
        corpo = dados[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif t == b"IDAT":
            idat += corpo
        pos += 12 + n
    w, h, prof, tipo, _c, _f, inter = ihdr
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}.get(tipo)
    if prof != 8 or inter or bpp is None:
        raise ValueError("PNG não suportado (só 8-bit, sem interlace)")
    raw, stride, linhas, ant = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, cur = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = cur[i - bpp] if i >= bpp else 0
            b, c = ant[i], (ant[i - bpp] if i >= bpp else 0)
            if f == 1:
                cur[i] = (cur[i] + a) & 255
            elif f == 2:
                cur[i] = (cur[i] + b) & 255
            elif f == 3:
                cur[i] = (cur[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        linhas.append(bytes(cur))
        ant = cur
    return w, h, bpp, linhas


def diff_png(a, b, tolerancia=2):
    """Fração de pixels diferentes entre dois PNG (1.0 se os tamanhos diferem)."""
    if a == b:
        return 0.0
    wa, ha, bpa, la = _decodificar(a)
    wb, hb, bpb, lb = _decodificar(b)
    if (wa, ha, bpa) != (wb, hb, bpb):
        return 1.0
    dif = 0
    for ra, rb in zip(la, lb):
        if ra == rb:
            continue
        for x in range(0, len(ra), bpa):
            if any(abs(ra[x + k] - rb[x + k]) > tolerancia for k in range(bpa)):
                dif += 1
    return dif / (wa * ha)


# --- config e browser ---------------------------------------------------------

def carregar_config(repo):
    try:
        cfg = json.loads((Path(repo) / "kaizen.config.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    d = cfg.get("design") if isinstance(cfg, dict) else None
    if not isinstance(d, dict) or not isinstance(d.get("url"), str) or not d["url"] \
            or not isinstance(d.get("rotas"), list) or not d["rotas"] \
            or not all(isinstance(r, str) and r.startswith("/") for r in d["rotas"]):
        return None
    return d


def breakpoints(repo, cfg):
    """3 breakpoints {nome: largura px}: `design.breakpoints`, senão sm/md/xl de `design/tokens.json`, senão fallback."""
    bp = cfg.get("breakpoints")
    if isinstance(bp, dict) and bp:
        return {k: int(v) for k, v in list(bp.items())[:3] if isinstance(v, int) and v > 0}
    try:
        raiz = json.loads((Path(repo) / "design" / "tokens.json").read_text(encoding="utf-8"))
        vals = dict(ds_core._valores(raiz, "breakpoint"))
        px = {k.split(".")[-1]: int(ds_core.px(v)) for k, v in vals.items()}
        escolha = {k: px[k] for k in BP_FALLBACK if k in px}
        if len(escolha) == 3:
            return escolha
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return dict(BP_FALLBACK)


def _no_ar(url):
    try:
        urllib.request.urlopen(url, timeout=2).close()  # noqa: S310 (URL local da config do projeto)
        return True
    except (OSError, ValueError):
        return False


def _arrancar(cfg, repo):
    if _no_ar(cfg["url"]) or not cfg.get("startCmd"):
        return None
    kw = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(cfg["startCmd"], shell=True, cwd=repo, stdout=subprocess.DEVNULL,  # noqa: S602
                            stderr=subprocess.DEVNULL, **kw)
    fim = time.monotonic() + int(cfg.get("startTimeout", 60))
    while time.monotonic() < fim and proc.poll() is None:
        if _no_ar(cfg["url"]):
            return proc
        time.sleep(0.5)
    _parar(proc)
    raise RuntimeError("o app não respondeu em `design.url` a tempo")


def _parar(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM) if os.name != "nt" else subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)  # noqa: S603,S607
    except (OSError, ProcessLookupError):
        proc.terminate()


def executar_browser(cfg, repo, destino, bps):
    """Corre o driver Node/Playwright do projeto-alvo; devolve {violacoes, screenshots} ou {semBrowser: True, motivo}."""
    node = shutil.which("node")
    if not node:
        return {"semBrowser": True, "motivo": "node não encontrado"}
    try:
        proc = _arrancar(cfg, repo)
    except RuntimeError as e:
        return {"semBrowser": True, "motivo": str(e)}
    try:
        entrada = json.dumps({"url": cfg["url"], "rotas": cfg["rotas"], "breakpoints": bps, "destino": str(destino),
                              "slugs": {r: slug(r) for r in cfg["rotas"]}})
        r = subprocess.run([node, str(DRIVER)], input=entrada, cwd=repo, capture_output=True, text=True,  # noqa: S603
                           encoding="utf-8", errors="replace", timeout=int(cfg.get("timeout", 300)), check=False)
    except subprocess.TimeoutExpired:
        return {"semBrowser": True, "motivo": "driver excedeu o tempo"}
    finally:
        _parar(proc)
    try:
        saida = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"semBrowser": True, "motivo": (r.stderr or "driver sem saída").strip()[-200:]}
    return saida


def lighthouse(cfg):
    """[(rota, score)] do orçamento Lighthouse (`design.lighthouse`); [] sem config; avisos em stderr se falhar."""
    lh = cfg.get("lighthouse")
    if not isinstance(lh, dict) or not lh.get("cmd"):
        return []
    saida = []
    for rota in cfg["rotas"]:
        try:
            r = run_hidden(lh["cmd"].replace("{url}", cfg["url"].rstrip("/") + rota), shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=int(lh.get("timeout", 180)))
            score = json.loads(r.stdout)["categories"]["performance"]["score"]
            saida.append((rota, float(score)))
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            print(f"aviso: Lighthouse não correu em {rota} (orçamento não verificado)", file=sys.stderr)
    return saida


# --- verificação --------------------------------------------------------------

def verificar(repo, cfg, res, atualizar, limiar):
    """Compara `res` (saída do browser) com as baselines; devolve (problemas, relatório)."""
    base = Path(repo) / "design" / "baselines"
    problemas, diffs = [], []
    for v in res.get("violacoes", []):
        if v.get("impact") in GRAVES:
            problemas.append(f"a11y {v['impact']} {v['id']} em {v['rota']} ({v.get('nodes', '?')} nós)")
    for s in res.get("screenshots", []):
        alvo = base / f"{slug(s['rota'])}-{s['bp']}.png"
        novo = Path(s["ficheiro"]).read_bytes()
        if atualizar:
            base.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(novo)
            continue
        if not alvo.is_file():
            problemas.append(f"sem baseline para {s['rota']} @{s['bp']} (rever e usar --atualizar-baselines)")
            continue
        try:
            d = diff_png(alvo.read_bytes(), novo)
        except (ValueError, zlib.error, struct.error) as e:
            problemas.append(f"screenshot ilegível {s['rota']} @{s['bp']}: {e}")
            continue
        diffs.append({"rota": s["rota"], "bp": s["bp"], "diff": round(d, 4)})
        if d > limiar:
            problemas.append(f"diff visual {d:.2%} > {limiar:.2%} em {s['rota']} @{s['bp']}")
    minimo = (cfg.get("lighthouse") or {}).get("minPerformance", 0.8)
    perf = lighthouse(cfg)
    problemas += [f"performance {sc:.2f} < {minimo} em {r}" for r, sc in perf if sc < minimo]
    rel = {"ok": not problemas, "problemas": problemas, "violacoes": res.get("violacoes", []), "diffs": diffs,
           "screenshots": [{"rota": s["rota"], "bp": s["bp"]} for s in res.get("screenshots", [])],
           "performance": [{"rota": r, "score": sc} for r, sc in perf], "baselinesAtualizadas": atualizar}
    return problemas, rel


def _registar_sp(sp, atualizar, rel):
    linha = f"- ds-verify {time.strftime('%Y-%m-%d %H:%M')}: " + (
        f"baselines atualizadas ({len(rel['screenshots'])} screenshots) por flag explícita" if atualizar
        else ("verde" if rel["ok"] else f"vermelho ({len(rel['problemas'])} problema(s))"))
    p = Path(sp)
    texto = p.read_text(encoding="utf-8")
    if "## Design" not in texto:
        texto = texto.rstrip("\n") + "\n\n## Design\n"
    p.write_text(texto.rstrip("\n") + "\n" + linha + "\n", encoding="utf-8")


def main(argv=None, runner=None):
    ap = argparse.ArgumentParser(description="a11y + screenshots + performance contra o design system")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--atualizar-baselines", action="store_true", help="grava as screenshots atuais como baselines (explícito)")
    ap.add_argument("--sp", help="SP onde registar o resultado em `## Design`")
    ap.add_argument("--prova", help="pasta onde copiar o relatório e as screenshots (prova do SP)")
    a = ap.parse_args(argv)
    repo = Path(a.dir)
    cfg = carregar_config(repo)
    if cfg is None:
        print("erro: falta `design` {url, rotas[]} em kaizen.config.json", file=sys.stderr)
        return 2
    bps = breakpoints(repo, cfg)
    limiar = cfg.get("limiarDiff") if isinstance(cfg.get("limiarDiff"), (int, float)) else LIMIAR_DEFEITO
    destino = repo / "design" / ".verify"
    destino.mkdir(parents=True, exist_ok=True)
    res = (runner or executar_browser)(cfg, repo, destino, bps)
    if res.get("semBrowser"):
        print(f"aviso: UI não verificada ({res.get('motivo', 'sem browser/Playwright/axe')}); "
              "instalar playwright e @axe-core/playwright no projeto-alvo", file=sys.stderr)
        return 3
    problemas, rel = verificar(repo, cfg, res, a.atualizar_baselines, limiar)
    (repo / "design" / "relatorio.json").write_text(json.dumps(rel, indent=1, ensure_ascii=False), encoding="utf-8")
    if a.prova:
        Path(a.prova).mkdir(parents=True, exist_ok=True)
        shutil.copy(repo / "design" / "relatorio.json", Path(a.prova) / "relatorio.json")
        for s in res.get("screenshots", []):
            shutil.copy(s["ficheiro"], Path(a.prova) / Path(s["ficheiro"]).name)
    if a.sp:
        _registar_sp(a.sp, a.atualizar_baselines, rel)
    for p in problemas:
        print(p)
    print(("ok" if not problemas else f"{len(problemas)} problema(s)") + f": {len(rel['screenshots'])} screenshots, "
          f"{len(rel['violacoes'])} violações axe")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
