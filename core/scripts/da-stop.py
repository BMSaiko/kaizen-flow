"""DA: decide tentar/parar numa falha de gate segundo o perfil do SP e imprime o relatório de paragem.

Perfis e overrides: `.claude/skills/michi/references/michi-perfis.md` (único sítio das regras).
Uso: python -I scripts/da-stop.py <SP> --passo N.M --tentativas K --causa TXT [--proximo TXT]
rc: 0 tentar de novo, 1 parar (relatório no stdout)
"""
import argparse
import re
import sys
from pathlib import Path

PERFIS = {
    "cauteloso": (1, ["gate-falha", "ambiguidade", "ficheiro-fora-de-escopo", "custo"]),
    "normal": (2, ["gate-falha", "ficheiro-fora-de-escopo"]),
    "autonomo": (2, ["gate-falha"]),
}


def _front(path):
    m = re.match(r"---\n(.*?)\n---", Path(path).read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    campos = {}
    for linha in (m.group(1) if m else "").splitlines():
        k, _, v = linha.partition(":")
        if _ and not k.startswith(" "):
            campos[k.strip()] = v.strip()
    return campos


def limites(path):
    f = _front(path)
    tentativas, parar = PERFIS.get(f.get("perfil", "normal"), PERFIS["normal"])
    if f.get("max_tentativas", "").isdigit():
        tentativas = int(f["max_tentativas"])
    if f.get("parar_se"):
        parar = [x.strip() for x in f["parar_se"].strip("[]").split(",") if x.strip()]
    return tentativas, list(parar)


def decide(path, tentativas):
    maximo, parar = limites(path)
    return "parar" if "gate-falha" in parar and tentativas >= maximo else "tentar"


def relatorio(passo, tentativas, causa, proximo):
    return "\n".join(["## Paragem DA", f"- Passo: {passo}", f"- Tentativas: {tentativas}",
                      f"- Causa: {causa}", f"- Próximo passo: {proximo}"])


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sp")
    ap.add_argument("--passo", required=True)
    ap.add_argument("--tentativas", type=int, required=True)
    ap.add_argument("--causa", required=True)
    ap.add_argument("--proximo", default="rever a causa com o user")
    a = ap.parse_args(argv)
    if decide(a.sp, a.tentativas) == "tentar":
        print(f"tentar de novo (tentativa {a.tentativas + 1})")
        return 0
    print(relatorio(a.passo, a.tentativas, a.causa, a.proximo))
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
