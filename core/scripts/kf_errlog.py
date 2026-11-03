#!/usr/bin/env python3
"""Log estruturado (JSONL) das falhas dos scripts do kf.

Uso nos scripts (no fim do ficheiro):
    sys.path.insert(0, str(HERE)); import kf_errlog
    if __name__ == "__main__":
        sys.exit(kf_errlog.executar("sp-move", main))

Cada falha (exceção ou rc != 0) vira uma linha JSON: ts, script, args, tipo, mensagem,
branch, rc (+ contexto). Best effort: falhar a gravar nunca parte o script, e a
mensagem, o stdout e o rc do script não mudam. Nunca grava valores de segredos.

Local: $KF_ERRLOG, senão %LOCALAPPDATA%\\kaizen-flow\\errors.jsonl, senão
~/.kaizen-flow/errors.jsonl (fora do git). Rotação a 1 MiB (errors.jsonl.1).
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 1024 * 1024
MAX_MSG = 500
MAX_ARG = 200
REDACTED = "***"

_SECRET_NAME = re.compile(r"(token|secret|passw|pwd|api[-_]?key|apikey|auth|credential|cookie|private)", re.I)
_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{16,}|xox[abp]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{12,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_SENSITIVE_FILE = re.compile(r"(^|[\\/])(\.env(\..*)?|.*\.(key|pem|p12|pfx)|id_rsa.*|secrets\..*|\.secrets.*)$", re.I)


def caminho_log():
    env = os.environ.get("KF_ERRLOG")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "kaizen-flow" / "errors.jsonl"
    return Path.home() / ".kaizen-flow" / "errors.jsonl"


def _limpar_texto(texto, limite):
    texto = _SECRET_VALUE.sub(REDACTED, str(texto))
    texto = re.sub(r"(?i)\b([A-Za-z0-9_]*(?:token|secret|passw\w*|api[-_]?key|auth)[A-Za-z0-9_]*)=\S+", r"\1=" + REDACTED, texto)
    return texto if len(texto) <= limite else texto[:limite] + "…"


def filtrar_args(argv):
    """Cópia de `argv` sem valores de segredos (flags sensíveis, KEY=valor, tokens, ficheiros .env/chaves)."""
    out = []
    esconder_proximo = False
    for a in argv:
        a = str(a)
        if esconder_proximo:
            out.append(REDACTED)
            esconder_proximo = False
            continue
        if _SENSITIVE_FILE.search(a):
            out.append(REDACTED)
            continue
        if a.startswith("-") and "=" in a:
            nome, _, valor = a.partition("=")
            out.append(f"{nome}={REDACTED}" if _SECRET_NAME.search(nome) else _limpar_texto(a, MAX_ARG))
            continue
        if a.startswith("-") and _SECRET_NAME.search(a):
            out.append(a)
            esconder_proximo = True
            continue
        out.append(_limpar_texto(a, MAX_ARG))
    return out


def _branch():
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=2
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _rodar(path):
    try:
        if path.exists() and path.stat().st_size >= MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
    except Exception:
        pass


def registar(script, erro, contexto=None, rc=None, args=None):
    """Grava uma linha no log. Devolve True se gravou; nunca levanta."""
    try:
        if isinstance(erro, BaseException):
            tipo, mensagem = type(erro).__name__, str(erro)
        else:
            tipo, mensagem = "mensagem", str(erro)
        linha = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": str(script),
            "args": filtrar_args(sys.argv[1:] if args is None else args),
            "tipo": tipo,
            "mensagem": _limpar_texto(mensagem, MAX_MSG),
            "branch": _branch(),
            "rc": rc,
        }
        if contexto:
            linha["contexto"] = _limpar_texto(contexto, MAX_MSG)
        path = caminho_log()
        path.parent.mkdir(parents=True, exist_ok=True)
        _rodar(path)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


class _Tee:
    """Passa tudo ao stream real e guarda a cauda, para usar como mensagem."""

    def __init__(self, real):
        self.real = real
        self.cauda = ""

    def write(self, s):
        self.cauda = (self.cauda + str(s))[-2000:]
        return self.real.write(s)

    def __getattr__(self, nome):
        return getattr(self.real, nome)


def _ultima_linha(texto):
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    return linhas[-1] if linhas else ""


def executar(script, main, argv=None):
    """Corre `main()` (lê `sys.argv`; `argv` só serve para o log) e regista exceções e rc != 0 sem mudar o resultado (re-raise, mesmo rc)."""
    real = sys.stderr
    tee = _Tee(real)
    sys.stderr = tee
    args = sys.argv[1:] if argv is None else argv
    try:
        rc = main()
    except SystemExit as e:
        code = e.code
        if code not in (None, 0):
            msg = code if isinstance(code, str) else _ultima_linha(tee.cauda)
            registar(script, msg or f"SystemExit({code})", rc=code if isinstance(code, int) else 1, args=args)
        raise
    except Exception as e:
        registar(script, e, rc=1, args=args)
        raise
    finally:
        sys.stderr = real
    if rc not in (None, 0):
        registar(script, _ultima_linha(tee.cauda) or f"rc={rc}", rc=rc, args=args)
    return rc
