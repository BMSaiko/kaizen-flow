"""Fixtures e auxiliares partilhados pelos test_sp_fila_*.py (carrega sp-fila.py como `sp_fila`).

Uso: importado pelos test_sp_fila_*.py; sem execução direta
rc: n/a
"""
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location("sp_fila", Path(__file__).with_name("sp-fila.py"))
sp_fila = importlib.util.module_from_spec(_spec)
sys.modules["sp_fila"] = sp_fila
_spec.loader.exec_module(sp_fila)


def make_sp(root, slug, folder="TODO", project="p", priority="P2", created="2026-10-01T10:00:00Z", modo="auto",
            gates=True, depends_on=None, kind=None, extra=None):
    path = root / project / "sp" / folder / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"status: {folder}", f"created: {created}", f"updated: {created}", f"slug: {slug}", f"project: {project}",
             f"priority: {priority}"]
    if modo:
        lines.append(f"modo: {modo}")
    if depends_on:
        lines.append(f"depends_on: [{', '.join(depends_on)}]")
    if kind:
        lines.append(f"kind: {kind}")
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    if gates:
        lines += ["gates:", "  - cmd: echo ok"]
    lines += ["---", "# corpo"]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def plan(root, **kw):
    return sp_fila.plan(sp_fila.load(root, kw.pop("project", None)), **kw)


def slugs(result):
    return [sp.slug for sp in result[0]]


def reasons(result):
    return {slug: why for slug, why in result[1]}


def _runner(calls):
    def run(argv, **_):
        calls.append(argv)
        saida = f"/wt/sb-{argv[-1]}\n" if "ensure" in argv else ""  # sb-worktree ensure imprime o caminho

        class R:
            returncode = 0
            stdout = saida
            stderr = ""
        return R()
    return run


def _estado(tmp_path, **over):
    base = {"max": 3, "ate": None, "orcamento": 200, "usados": 0, "feitos": [], "falhados": [], "saltados": [],
            "sessoes": {}, "projeto": None, "inicio": "2026-10-25T10:00:00", "commits": []}
    base.update(over)
    f = tmp_path / "estado.json"
    f.write_text(json.dumps(base), encoding="utf-8")
    return f


def _arvore(root, mae_extra):
    make_sp(root, "mae", kind="program", modo="manual", extra=mae_extra)
    for s in ("f1", "f2", "f3"):
        make_sp(root, s, extra={"parent": "mae"})
    make_sp(root, "fora")


def _pid_morto():
    import subprocess
    p = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    p.wait()
    return p.pid


def _runner_worktree(calls, wt):
    """Runner cujo `git worktree list --porcelain` devolve uma worktree `agent/<nome>` em `wt`."""
    def run(argv, **_):
        calls.append(argv)

        class R:
            returncode = 0
            stderr = ""
            stdout = f"worktree {wt}\nHEAD abc\nbranch refs/heads/agent/{wt.name}\n\n" if "worktree" in argv else ""
        return R()
    return run


class PainelFalso:
    """Backend de painéis falso (interface de `painel_backend.Backend` + `titulo`/`titulos`), sem WezTerm real."""
    nome = "falso"

    def __init__(self, titulos=None, falha_abrir=None, falha_enviar=False, interativo=True):
        self.interativo = interativo
        self.abertos, self.abertos_ids, self.enviados, self.fechados = [], [], [], []
        self.titulos_postos = {}
        self._titulos = dict(titulos or {})
        self.falha_abrir, self.falha_enviar = falha_abrir, falha_enviar

    def abrir(self, cmd, cwd):
        if self.falha_abrir:
            raise OSError(self.falha_abrir)
        pid = str(100 + len(self.abertos))
        self.abertos.append((list(cmd), str(cwd)))
        self.abertos_ids.append(pid)
        return pid

    def listar(self):
        return {p: None for p in self.abertos_ids if p not in self.fechados}

    def fechar(self, id):
        self.fechados.append(str(id))
        return True

    def ecra(self, id):
        return "❯ "

    def enviar(self, id, texto):
        if self.falha_enviar:
            return False
        self.enviados.append((str(id), texto))
        return True

    def estado(self, id):
        return "vivo" if str(id) in self.listar() else "morto"

    def titulo(self, id, texto):
        self.titulos_postos[str(id)] = texto
        self._titulos[str(id)] = texto
        return True

    def titulos(self):
        return dict(self._titulos)


def _relatorio_com(tmp_path, **estado_over):
    root = tmp_path / "sps"
    make_sp(root, "a", folder="Done")
    st = _estado(tmp_path, sessoes={"a": {}}, feitos=["a"], **estado_over)
    out = sp_fila.seguinte(root, st, tmp_path / "rel", _runner([]), datetime(2026, 11, 6, 12, 0))
    return Path(out["relatorio"]).read_text(encoding="utf-8")
