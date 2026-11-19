"""Portão de criação de SPs: regra «por aprovar» e escrita de campos no frontmatter (em bytes, mantém CRLF).

Uso: módulo importado por sp-aprovar.py, sp-validate.py e sp_fila_plano.py; sem execução direta
rc: n/a

Exceções (único sítio): SPs com `origem:` (correção nascida de um veredicto `ajustar`, SP de `pentest`)
ficam aprovados pela origem, sem grill. SPs de `date` anterior a DESDE não precisam de `aprovado`.
"""
from datetime import datetime, timezone

DESDE = "2026-11-13"
RONDAS_MINIMAS = 1


def por_aprovar(fm):
    """True se o SP é novo (date ≥ DESDE), não tem `aprovado:` nem `origem:`."""
    data = str(fm.get("date", ""))
    if not data or data < DESDE:
        return False
    return not (fm.get("aprovado") or fm.get("origem"))


def agora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gravar_campos(path, campos):
    """Grava `campos` (dict chave -> valor) no frontmatter e atualiza `updated:`; idempotente (sem mudança, não reescreve)."""
    original = path.read_bytes()
    linhas = original.decode("utf-8").splitlines(keepends=True)
    fim = next(i for i in range(1, len(linhas)) if linhas[i].strip() == "---")
    eol = linhas[0][len(linhas[0].rstrip("\r\n")):] or "\n"
    for chave, valor in campos.items():
        nova = f"{chave}: {valor}{eol}"
        for i in range(1, fim):
            if linhas[i].startswith(f"{chave}:"):
                linhas[i] = nova
                break
        else:
            linhas.insert(fim, nova)
            fim += 1
    if "".join(linhas).encode("utf-8") == original:
        return False
    for i in range(1, fim):
        if linhas[i].startswith("updated:"):
            linhas[i] = f"updated: {agora()}{eol}"
    path.write_bytes("".join(linhas).encode("utf-8"))
    return True
