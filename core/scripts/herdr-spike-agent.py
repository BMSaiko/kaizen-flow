#!/usr/bin/env python3
"""Spike F1: ciclo start -> prompt -> wait -> list/get -> close de um agente herdr 0.9.5 numa sessão isolada.

Uso: herdr-spike-agent.py [--dry-run] [--session NOME] [--kind claude] [--prompt TEXTO] [--model M] [--timeout-ms N]
`--dry-run` imprime os comandos sem executar nada. Só stdlib + CLI `herdr`."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time


def herdr(sessao, *argv, timeout=330):
    cmd = ["herdr", "--session", sessao, *argv]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    try:
        saida = json.loads(r.stdout) if r.stdout.strip() else None
    except ValueError:
        saida = r.stdout
    return {"cmd": cmd[3:], "rc": r.returncode, "saida": saida, "stderr": r.stderr.strip()}


def plano(a):
    s = a.session
    ag = ["agent", "start", "spike", "--kind", a.kind, "--pane", "<PANE>", "--timeout", str(a.timeout_ms)]
    if a.model:
        ag += ["--", "--model", a.model]
    return [["workspace", "create", "--cwd", "<TMP>", "--label", "spike", "--no-focus"], ag,
            ["agent", "prompt", "spike", a.prompt, "--wait", "--timeout", str(a.timeout_ms)],
            ["agent", "list"], ["agent", "get", "spike"], ["pane", "close", "<PANE>"], ["server", "stop"], ["session", "delete", s]]


def correr(a):
    s = a.session
    passos = []
    srv = subprocess.Popen(["herdr", "--session", s, "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if herdr(s, "status", "server")["rc"] == 0 and "running" in str(herdr(s, "status", "server")["saida"]):
                break
            time.sleep(0.2)
        with tempfile.TemporaryDirectory() as tmp:
            w = herdr(s, "workspace", "create", "--cwd", tmp, "--label", "spike", "--no-focus")
            passos.append(w)
            pane = w["saida"]["result"]["root_pane"]["pane_id"]
            ag = ["agent", "start", "spike", "--kind", a.kind, "--pane", pane, "--timeout", str(a.timeout_ms)]
            if a.model:
                ag += ["--", "--model", a.model]
            passos.append(herdr(s, *ag))
            passos.append(herdr(s, "agent", "prompt", "spike", a.prompt, "--wait", "--timeout", str(a.timeout_ms)))
            passos.append(herdr(s, "agent", "list"))
            passos.append(herdr(s, "agent", "get", "spike"))
            passos.append(herdr(s, "agent", "explain", "spike", "--json"))
            passos.append(herdr(s, "pane", "read", pane, "--source", "visible", "--lines", "30"))
            passos.append(herdr(s, "pane", "close", pane))
    finally:
        passos.append(herdr(s, "server", "stop"))
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        passos.append(herdr(s, "session", "delete", s))  # as sessões persistem: apagar a de teste
    return passos


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--session", default=f"f1spike-{os.getpid()}")
    p.add_argument("--kind", default="claude")
    p.add_argument("--model", default="")
    p.add_argument("--prompt", default="Responde apenas: OK")
    p.add_argument("--timeout-ms", type=int, default=120000)
    a = p.parse_args(argv)
    if a.dry_run:
        for c in plano(a):
            print("herdr --session", a.session, " ".join(c))
        return 0
    passos = correr(a)
    print(json.dumps(passos, ensure_ascii=False, indent=1))
    return 0 if all(x["rc"] == 0 for x in passos) else 1


if __name__ == "__main__":
    sys.exit(main())
