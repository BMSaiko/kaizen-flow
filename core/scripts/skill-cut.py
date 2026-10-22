#!/usr/bin/env python3
"""Move os blocos de uma secção de uma SKILL.md para references/, deixando um índice de uma linha por bloco.

Um bloco começa numa linha '- ' sem indentação, numa linha '1. ' (--numbered) ou num cabeçalho '### '.
Verifica que nº de blocos no original == nº de linhas de índice == nº de blocos na referência
e que cada bloco existe literalmente na referência. Só escreve se tudo bater certo.
"""
import argparse
import re
import sys
from pathlib import Path


def split_blocks(body, numbered):
    start = re.compile(r"^(\d+\. |### )" if numbered else r"^(- |### )")
    blocks, current = [], None
    preamble = []
    for line in body:
        if start.match(line):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append(current)
    return preamble, ["\n".join(b).rstrip("\n") for b in blocks]


def label(block):
    first = block.split("\n", 1)[0]
    if first.startswith("### "):
        return first[4:].strip()
    bold = re.search(r"\*\*(.+?)\*\*", block)
    text = bold.group(1) if bold else re.sub(r"^(- |\d+\. )", "", first)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".:")
    return text[:110]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("skill")
    ap.add_argument("heading", help="ex.: '## Pitfalls'")
    ap.add_argument("ref", help="ficheiro de referência a criar")
    ap.add_argument("--numbered", action="store_true")
    ap.add_argument("--title", required=True)
    args = ap.parse_args()

    skill, ref = Path(args.skill), Path(args.ref)
    lines = skill.read_text(encoding="utf-8").split("\n")
    level = len(args.heading.split(" ")[0])
    begin = lines.index(args.heading)
    end = next(
        (i for i in range(begin + 1, len(lines)) if re.match(r"^#{1,%d} " % level, lines[i])),
        len(lines),
    )
    preamble, blocks = split_blocks(lines[begin + 1 : end], args.numbered)
    assert blocks, "nenhum bloco encontrado"

    rel = ref.relative_to(skill.parent).as_posix()
    index = [f"{i}. {label(b)}" for i, b in enumerate(blocks, 1)]
    ref_text = [f"# {args.title}", "", f"Movido de `SKILL.md` ({args.heading}); texto integral, {len(blocks)} entradas.", ""]
    for i, b in enumerate(blocks, 1):
        ref_text += [f"## {i}. {label(b)}", "", b, ""]
    ref_out = "\n".join(ref_text)

    assert len(index) == len(blocks)
    assert all(b in ref_out for b in blocks), "bloco perdido na referência"
    total_chars = sum(len(b) for b in blocks)

    new_body = (
        ["", f"Texto integral em `{rel}` ({len(blocks)} entradas, numeradas como abaixo). Ler só a entrada relevante.", ""]
        + index
        + [""]
    )
    out = lines[:begin + 1] + new_body + lines[end:]
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(ref_out, encoding="utf-8", newline="\n")
    skill.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"blocos={len(blocks)} indice={len(index)} chars_movidos={total_chars} linhas_skill={len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
