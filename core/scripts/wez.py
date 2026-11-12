"""wez: CLI do vault sobre `wezterm cli` (painéis pelo nome, envio, layouts, config).

Uso: python -I scripts/wez.py <subcomando> [args...]
rc: 0 ok, 1 erro do subcomando
Base comum: run_cli() corre `wezterm cli ...`; list_panes() devolve os painéis.
Programa: wezterm-cli-2026-11-10.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

TIMEOUT_S = 10

# subcomando -> (ajuda, SP que o implementa)
SUBCOMANDOS = {
    "pane": ("Painéis pelo nome: ls, open, focus, kill", "wezterm-wez-pane-2026-11-10"),
    "send": ("Mandar texto a um painel pelo nome", "wezterm-wez-send-2026-11-10"),
    "read": ("Ler o texto de um painel pelo nome", "wezterm-wez-send-2026-11-10"),
    "layout": ("Layouts guardados: ls, open", "wezterm-wez-layout-2026-11-10"),
    "cfg": ("Config: check, diff, sync com wezterm-config", "wezterm-wez-cfg-2026-11-10"),
}

# subcomando -> função(args) -> rc; os SPs filhos registam aqui o seu handler
_HANDLERS = {}


class WezError(RuntimeError):
    """Falha ao falar com o WezTerm (binário, rc, timeout ou output)."""


def _binary():
    return shutil.which("wezterm") or "wezterm"


def run_cli(args):
    """Corre `wezterm cli <args>` e devolve o stdout; WezError se falhar."""
    cmd = [_binary(), "cli", *args]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=TIMEOUT_S)
    except FileNotFoundError:
        raise WezError("wezterm não encontrado no PATH") from None
    except subprocess.TimeoutExpired:
        raise WezError(f"wezterm cli {' '.join(args)}: sem resposta (tempo > {TIMEOUT_S}s)") from None
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip()
        raise WezError(f"wezterm cli {' '.join(args)} (rc {res.returncode}): {msg}")
    return res.stdout


def list_panes():
    """Lista os painéis (`wezterm cli list --format json`) como dicts."""
    out = run_cli(["list", "--format", "json"])
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        raise WezError(f"output de list não é JSON válido: {e}") from None
    if not isinstance(data, list):
        raise WezError("output de list não é uma lista JSON")
    return data


# --- pane: painéis pelo nome (wezterm-wez-pane-2026-11-10) ---

def norm(nome):
    """Normaliza um nome de painel: sem ícone inicial, minúsculas, espaços/_ -> '-'."""
    s = str(nome).strip()
    while s and not s[0].isalnum():
        s = s[1:]
    s = re.sub(r"[\s_]+", "-", s.casefold())
    return s.strip("-")


def resolve_pane(nome, panes=None):
    """Resolve nome ou id para pane_id: id > igual > prefixo > contém; ambíguo ou ausente = WezError."""
    panes = list_panes() if panes is None else panes
    alvo = str(nome).strip()
    if alvo.isdigit():
        for p in panes:
            if p.get("pane_id") == int(alvo):
                return p["pane_id"]
        raise WezError(f"painel {alvo} não encontrado")
    n = norm(alvo)
    if not n:
        raise WezError("nome de painel vazio")
    # por nível (igual > prefixo > contém): título do painel antes do separador,
    # porque painéis divididos partilham o tab_title
    for teste in (lambda x: x == n, lambda x: x.startswith(n), lambda x: n in x):
        for campo in ("title", "tab_title"):
            hits = [p["pane_id"] for p in panes if (v := norm(p.get(campo, "") or "")) and teste(v)]
            if len(hits) == 1:
                return hits[0]
            if hits:
                cand = ", ".join(f"{p['pane_id']}={p.get(campo, '')}"
                                 for p in panes if p["pane_id"] in hits)
                raise WezError(f"nome '{alvo}' ambíguo: {cand}")
    raise WezError(f"painel '{alvo}' não encontrado (ver `wez pane ls`)")


def _cwd(p):
    c = p.get("cwd", "") or ""
    c = c[len("file://"):] if c.startswith("file://") else c
    return c[1:] if re.match(r"^/[A-Za-z]:/", c) else c


def _pane_ls(a):
    rows = [{"id": p.get("pane_id"), "tab": p.get("tab_title", "") or "",
             "titulo": p.get("title", "") or "", "cwd": _cwd(p), "ativo": bool(p.get("is_active"))}
            for p in list_panes()]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    print(f"{'id':>4}  {'*':1}  {'separador':22}  {'título':36}  cwd")
    for r in rows:
        print(f"{r['id']:>4}  {'*' if r['ativo'] else ' '}  {r['tab'][:22]:22}  "
              f"{r['titulo'][:36]:36}  {r['cwd']}")
    return 0


def _pane_open(a):
    cmd = ["spawn"]
    if a.new_window:
        cmd.append("--new-window")
    if a.cwd:
        cmd += ["--cwd", a.cwd]
    if a.prog:
        cmd += ["--", *a.prog]
    pid = run_cli(cmd).strip()
    if not pid.isdigit():
        raise WezError(f"spawn não devolveu um id: {pid!r}")
    run_cli(["set-tab-title", "--pane-id", pid, a.nome])
    print(pid)
    return 0


def _pane_focus(a):
    run_cli(["activate-pane", "--pane-id", str(resolve_pane(a.nome))])
    return 0


def _pane_kill(a):
    pid = resolve_pane(a.nome)
    if str(pid) == os.environ.get("WEZTERM_PANE", "") and not a.force:
        raise WezError(f"o painel {pid} é este; usar --force para o fechar")
    run_cli(["kill-pane", "--pane-id", str(pid)])
    return 0


def _pane(args):
    p = argparse.ArgumentParser(prog="wez pane", description=SUBCOMANDOS["pane"][0])
    sub = p.add_subparsers(dest="acao", metavar="<ação>", required=True)
    ls = sub.add_parser("ls", help="listar painéis")
    ls.add_argument("--json", action="store_true")
    ls.set_defaults(fn=_pane_ls)
    op = sub.add_parser("open", help="abrir painel com nome; programa opcional depois de --")
    op.add_argument("nome")
    op.add_argument("--cwd")
    op.add_argument("--new-window", action="store_true")
    op.set_defaults(fn=_pane_open)
    fo = sub.add_parser("focus", help="focar painel pelo nome")
    fo.add_argument("nome")
    fo.set_defaults(fn=_pane_focus)
    ki = sub.add_parser("kill", help="fechar painel pelo nome")
    ki.add_argument("nome")
    ki.add_argument("--force", action="store_true", help="permite fechar o próprio painel")
    ki.set_defaults(fn=_pane_kill)
    resto, prog = list(args.resto), []
    if "--" in resto:
        i = resto.index("--")
        resto, prog = resto[:i], resto[i + 1:]
    a = p.parse_args(resto)
    a.prog = prog
    return a.fn(a)


_HANDLERS["pane"] = _pane


# --- send/read: texto para e de um painel (wezterm-wez-send-2026-11-10) ---

def send_text(pane, texto, enter=False):
    """Envia texto ao painel sem bracketed paste; enter=True acrescenta \\r."""
    if enter:
        texto += "\r"
    run_cli(["send-text", "--no-paste", "--pane-id", str(pane), texto])


def read_text(pane, lines=50):
    """Devolve as últimas `lines` linhas não vazias no fim do painel (get-text)."""
    if lines < 1:
        raise WezError("--lines tem de ser >= 1")
    out = run_cli(["get-text", "--pane-id", str(pane), "--start-line", str(-lines)])
    linhas = [ln.rstrip() for ln in out.splitlines()]
    while linhas and not linhas[-1]:
        linhas.pop()
    return "\n".join(linhas[-lines:])


def _send(args):
    p = argparse.ArgumentParser(prog="wez send", description=SUBCOMANDOS["send"][0])
    p.add_argument("nome")
    p.add_argument("--enter", action="store_true", help="carregar Enter no fim")
    p.add_argument("texto", nargs="+", help="texto a enviar; '-' lê do stdin")
    a = p.parse_args(list(args.resto))
    texto = sys.stdin.read() if a.texto == ["-"] else " ".join(a.texto)
    send_text(resolve_pane(a.nome), texto, enter=a.enter)
    return 0


def _read(args):
    p = argparse.ArgumentParser(prog="wez read", description=SUBCOMANDOS["read"][0])
    p.add_argument("nome")
    p.add_argument("--lines", type=int, default=50)
    a = p.parse_args(list(args.resto))
    print(read_text(resolve_pane(a.nome), a.lines))
    return 0


_HANDLERS["send"] = _send
_HANDLERS["read"] = _read


# --- cfg: validar e sincronizar a config (wezterm-wez-cfg-2026-11-10) ---

CFG_IGNORAR = {".git"}


def cfg_dir():
    """Pasta da config ativa: $WEZ_CFG_DIR ou ~/.config/wezterm."""
    return os.path.abspath(os.environ.get("WEZ_CFG_DIR")
                           or os.path.join(os.path.expanduser("~"), ".config", "wezterm"))


def config_errors(config_file):
    """Erros ao carregar a config. show-keys cai nos defaults sem erro; ls-fonts
    devolve rc 0 mas escreve 'ERROR ...' no stderr, por isso procura-se essa linha."""
    if not os.path.isfile(config_file):
        return [f"config não existe: {config_file}"]
    cmd = [_binary(), "--config-file", config_file, "ls-fonts"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=TIMEOUT_S * 3)
    except FileNotFoundError:
        raise WezError("wezterm não encontrado no PATH") from None
    except subprocess.TimeoutExpired:
        raise WezError("wezterm ls-fonts: sem resposta") from None
    erros = [ln.strip() for ln in (res.stderr or "").splitlines() if re.search(r"\bERROR\b", ln)]
    if res.returncode != 0 and not erros:
        erros.append(f"wezterm ls-fonts rc {res.returncode}: {(res.stderr or res.stdout or '').strip()}")
    return erros


def _ficheiros(raiz):
    out = set()
    for d, dirs, files in os.walk(raiz):
        dirs[:] = [x for x in dirs if x not in CFG_IGNORAR]
        for f in files:
            out.add(os.path.relpath(os.path.join(d, f), raiz).replace(os.sep, "/"))
    return out


def files_diff(src, dst):
    """Compara em bytes duas pastas: (só em src, só em dst, diferentes), listas ordenadas."""
    a, b = _ficheiros(src), _ficheiros(dst)
    dif = []
    for rel in sorted(a & b):
        with open(os.path.join(src, rel), "rb") as fa, open(os.path.join(dst, rel), "rb") as fb:
            if fa.read() != fb.read():
                dif.append(rel)
    return sorted(a - b), sorted(b - a), dif


def sync_copy(src, dst):
    """Copia em bytes (CRLF intacto) de src para dst o que falta ou difere; devolve a lista."""
    so_src, _so_dst, dif = files_diff(src, dst)
    copiados = sorted(so_src + dif)
    for rel in copiados:
        alvo = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        shutil.copyfile(os.path.join(src, rel), alvo)
    return copiados


def _git(repo, *args):
    try:
        res = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=TIMEOUT_S * 6)
    except FileNotFoundError:
        raise WezError("git não encontrado no PATH") from None
    except subprocess.TimeoutExpired:
        raise WezError(f"git {' '.join(args)}: sem resposta") from None
    if res.returncode != 0:
        raise WezError(f"git {' '.join(args)} (rc {res.returncode}): {(res.stderr or res.stdout or '').strip()}")
    return res.stdout


def git_state(repo):
    """{'sujos': [linhas porcelain], 'frente': n, 'atras': n} face ao upstream."""
    sujos = [ln for ln in _git(repo, "status", "--porcelain").splitlines() if ln.strip()]
    frente = atras = 0
    try:
        f, t = _git(repo, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        frente, atras = int(f), int(t)
    except (WezError, ValueError):
        pass
    return {"sujos": sujos, "frente": frente, "atras": atras}


def _confirm(pergunta):
    try:
        return input(f"{pergunta} [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:
        return False


def _mesma(a):
    return os.path.normcase(a.config_dir) == os.path.normcase(a.repo)


def _print_state(st):
    for ln in st["sujos"]:
        print(f"  {ln}")
    print(f"git: {len(st['sujos'])} alterado(s), {st['frente']} commit(s) à frente, "
          f"{st['atras']} atrás da origem")


def _cfg_check(a):
    f = a.config_file or os.path.join(a.config_dir, "wezterm.lua")
    erros = config_errors(f)
    if erros:
        print(f"config partida: {f}")
        for e in erros:
            print(f"  {e}")
        return 1
    print(f"config ok: {f}")
    return 0


def _cfg_diff(a):
    if _mesma(a):
        st = git_state(a.repo)
        _print_state(st)
        return 1 if (st["sujos"] or st["frente"] or st["atras"]) else 0
    so_cfg, so_repo, dif = files_diff(a.config_dir, a.repo)
    for marca, lista in (("+", so_cfg), ("-", so_repo), ("~", dif)):
        for rel in lista:
            print(f"{marca} {rel}")
    if not (so_cfg or so_repo or dif):
        print("config e repo iguais")
        return 0
    return 1


def _cfg_sync(a):
    if not _mesma(a):
        copiados = sync_copy(a.config_dir, a.repo)
        for rel in copiados:
            print(f"copiado {rel}")
        print(f"{len(copiados)} ficheiro(s) copiado(s) para {a.repo}")
    st = git_state(a.repo)
    _print_state(st)
    if not a.push:
        return 0
    if st["sujos"]:
        print("há alterações por commitar: commit no repo antes do push", file=sys.stderr)
        return 1
    if not st["frente"]:
        print("nada para enviar")
        return 0
    print(_git(a.repo, "log", "--oneline", "@{u}..HEAD").rstrip())
    if not _confirm(f"git push de {st['frente']} commit(s) em {a.repo}?"):
        print("push cancelado")
        return 1
    _git(a.repo, "push")
    print("push feito")
    return 0


def _cfg(args):
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--config-dir", help="pasta da config ativa ($WEZ_CFG_DIR)")
    comum.add_argument("--repo", help="clone do wezterm-config ($WEZ_CFG_REPO; defeito: a config)")
    p = argparse.ArgumentParser(prog="wez cfg", description=SUBCOMANDOS["cfg"][0])
    sub = p.add_subparsers(dest="acao", metavar="<ação>", required=True)
    ch = sub.add_parser("check", parents=[comum], help="validar a config com wezterm ls-fonts")
    ch.add_argument("--config-file")
    ch.set_defaults(fn=_cfg_check)
    sub.add_parser("diff", parents=[comum], help="comparar config e repo").set_defaults(fn=_cfg_diff)
    sy = sub.add_parser("sync", parents=[comum], help="copiar config para o repo; --push pede confirmação")
    sy.add_argument("--push", action="store_true")
    sy.set_defaults(fn=_cfg_sync)
    a = p.parse_args(list(args.resto))
    a.config_dir = os.path.abspath(a.config_dir) if a.config_dir else cfg_dir()
    a.repo = os.path.abspath(a.repo or os.environ.get("WEZ_CFG_REPO") or a.config_dir)
    return a.fn(a)


_HANDLERS["cfg"] = _cfg


# --- layout: layouts guardados em JSON (wezterm-wez-layout-2026-11-10) ---

LAYOUT_DIRS = ("right", "left", "top", "bottom")


def layouts_dir():
    """Pasta dos layouts: $WEZ_LAYOUTS_DIR ou scripts/wez-layouts/."""
    return os.path.abspath(os.environ.get("WEZ_LAYOUTS_DIR")
                           or os.path.join(os.path.dirname(os.path.abspath(__file__)), "wez-layouts"))


def validate_layout(data, nome="layout"):
    """Valida e normaliza um layout; devolve o dict com 'paineis' completos."""
    if not isinstance(data, dict):
        raise WezError(f"{nome}: o layout tem de ser um objeto JSON")
    paineis = data.get("paineis")
    if not isinstance(paineis, list) or not paineis:
        raise WezError(f"{nome}: 'paineis' tem de ser uma lista não vazia")
    vistos, out = [], []
    for i, p in enumerate(paineis):
        onde = f"{nome}: painel {i + 1}"
        if not isinstance(p, dict) or not isinstance(p.get("nome"), str) or not p["nome"].strip():
            raise WezError(f"{onde}: falta 'nome'")
        pn = p["nome"].strip()
        if pn in vistos:
            raise WezError(f"{onde}: nome repetido '{pn}'")
        cmd = p.get("cmd") or []
        if isinstance(cmd, str):
            cmd = [cmd]
        if not isinstance(cmd, list) or not all(isinstance(c, str) for c in cmd):
            raise WezError(f"{onde}: 'cmd' tem de ser texto ou lista de textos")
        cwd = p.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise WezError(f"{onde}: 'cwd' tem de ser texto")
        split = p.get("split")
        if i == 0:
            if split:
                raise WezError(f"{onde}: o primeiro painel não leva 'split'")
        else:
            split = dict(split or {})
            de = split.get("de", vistos[-1])
            if de not in vistos:
                raise WezError(f"{onde}: 'de' = '{de}' não é um painel anterior")
            d = split.get("dir", "right")
            if d not in LAYOUT_DIRS:
                raise WezError(f"{onde}: 'dir' tem de ser um de {', '.join(LAYOUT_DIRS)}")
            pc = split.get("percent", 50)
            if not isinstance(pc, int) or isinstance(pc, bool) or not 1 <= pc <= 99:
                raise WezError(f"{onde}: 'percent' tem de ser inteiro entre 1 e 99")
            split = {"de": de, "dir": d, "percent": pc}
        vistos.append(pn)
        out.append({"nome": pn, "cwd": cwd, "cmd": cmd, "split": split})
    return {"titulo": data.get("titulo") or nome, "descricao": data.get("descricao", ""),
            "janela_nova": bool(data.get("janela_nova")), "paineis": out}


def load_layout(nome, pasta=None):
    pasta = pasta or layouts_dir()
    if not re.fullmatch(r"[\w.-]+", nome):
        raise WezError(f"nome de layout inválido: {nome!r}")
    f = os.path.join(pasta, nome + ".json")
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise WezError(f"layout '{nome}' não existe em {pasta} (ver `wez layout ls`)") from None
    except json.JSONDecodeError as e:
        raise WezError(f"{f}: JSON inválido: {e}") from None
    return validate_layout(data, nome)


def list_layouts(pasta=None):
    pasta = pasta or layouts_dir()
    if not os.path.isdir(pasta):
        return []
    return sorted(f[:-5] for f in os.listdir(pasta) if f.endswith(".json"))


def _expand(c):
    return os.path.expandvars(os.path.expanduser(c)) if c else c


def _pid(out, acao):
    pid = out.strip()
    if not pid.isdigit():
        raise WezError(f"{acao} não devolveu um id: {pid!r}")
    return pid


def open_layout(lay):
    """Abre o layout já validado; devolve {nome do painel: pane id}."""
    ids = {}
    for p in lay["paineis"]:
        extra = (["--cwd", _expand(p["cwd"])] if p["cwd"] else []) + (["--", *p["cmd"]] if p["cmd"] else [])
        if p["split"] is None:
            cmd = ["spawn"] + (["--new-window"] if lay["janela_nova"] else []) + extra
            ids[p["nome"]] = _pid(run_cli(cmd), "spawn")
            run_cli(["set-tab-title", "--pane-id", ids[p["nome"]], lay["titulo"]])
        else:
            s = p["split"]
            cmd = ["split-pane", "--pane-id", ids[s["de"]], f"--{s['dir']}",
                   "--percent", str(s["percent"])] + extra
            ids[p["nome"]] = _pid(run_cli(cmd), "split-pane")
    return ids


def _layout_ls(a):
    nomes = list_layouts()
    if not nomes:
        print(f"sem layouts em {layouts_dir()}")
    for n in nomes:
        try:
            lay = load_layout(n)
            print(f"{n:16}  {len(lay['paineis'])} painéis  {lay['descricao']}")
        except WezError as e:
            print(f"{n:16}  INVÁLIDO: {e}")
    return 0


def _layout_open(a):
    ids = open_layout(load_layout(a.nome))
    for n, pid in ids.items():
        print(f"{pid:>4}  {n}")
    return 0


def _layout(args):
    p = argparse.ArgumentParser(prog="wez layout", description=SUBCOMANDOS["layout"][0])
    sub = p.add_subparsers(dest="acao", metavar="<ação>", required=True)
    sub.add_parser("ls", help="listar layouts").set_defaults(fn=_layout_ls)
    op = sub.add_parser("open", help="abrir um layout pelo nome")
    op.add_argument("nome")
    op.set_defaults(fn=_layout_open)
    a = p.parse_args(list(args.resto))
    return a.fn(a)


_HANDLERS["layout"] = _layout


def build_parser():
    p = argparse.ArgumentParser(prog="wez", description="CLI do vault sobre `wezterm cli`.")
    sub = p.add_subparsers(dest="cmd", metavar="<subcomando>")
    for name, (helptxt, _sp) in SUBCOMANDOS.items():
        sp = sub.add_parser(name, help=helptxt, description=helptxt)
        sp.add_argument("resto", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    handler = _HANDLERS.get(args.cmd)
    if handler is None:
        print(f"wez {args.cmd}: por implementar ({SUBCOMANDOS[args.cmd][1]})", file=sys.stderr)
        return 2
    try:
        return handler(args)
    except WezError as e:
        print(f"wez {args.cmd}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
