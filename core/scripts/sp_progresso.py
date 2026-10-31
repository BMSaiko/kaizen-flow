"""Ficheiro do SP no /sp-handoff: resolver o SP em Doing, registar `## Progresso` e sincronizar o SP-mãe."""
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kaizen_engine  # noqa: E402
from handoff_pane import HandoffError  # noqa: E402

sp_list = kaizen_engine.load("sp-list")

UPDATED_RE = re.compile(r"^updated:.*$")
MAX_BODY_LINES = 25
SP_SECTION_RE = re.compile(r"^#{1,6}\s*(?:\d+\.\s*)?(role|context|objective|success criteria|constraints|seams|steps|done-when)", re.I)


def _agent_claims():
    """Slugs reclamados pelo agente deste worktree; None fora de worktrees (comportamento original)."""
    if not Path(__file__).with_name("sb-agent.py").is_file():
        return None
    mod = kaizen_engine.load("sb-agent")
    try:
        agent = mod.current_agent(Path.cwd())
        return set(mod.claims_of(Path.cwd(), agent)) if agent else None
    except mod.SbAgentError:
        return None


def resolve(root, slug=None, mine=None):
    sps = sp_list.collect(root, include_done=True)
    if slug:
        kids = [sp for sp in sps if sp.parent == slug]
        if kids and not any(sp.slug == slug and sp.status == "Doing" for sp in sps):
            doing = [sp for sp in kids if sp.status == "Doing"]
            if not doing:
                raise HandoffError(f"programa '{slug}': nenhum filho em Doing")
            if len(doing) > 1:
                raise HandoffError("vários filhos em Doing, indicar o slug:\n" + "\n".join(f"  {sp.slug}" for sp in doing))
            return doing[0].path.resolve()
        matches = [sp for sp in sps if sp.slug == slug]
        if not matches:
            raise HandoffError(f"SP '{slug}' não encontrado")
        doing = [sp for sp in matches if sp.status == "Doing"]
        if not doing:
            raise HandoffError(f"SP '{slug}' não está em Doing (está em {matches[0].status})")
        if len(doing) > 1:
            raise HandoffError("slug em vários projetos: " + ", ".join(f"{sp.slug} ({sp.project})" for sp in doing))
        return doing[0].path.resolve()
    doing = [sp for sp in sps if sp.status == "Doing" and (mine is None or sp.slug in mine)]
    if not doing:
        raise HandoffError("nenhum SP em Doing" + (" reclamado por este agente" if mine is not None else ""))
    if len(doing) > 1:
        opts = "\n".join(f"  {sp.slug} ({sp.project})" for sp in doing)
        raise HandoffError(f"vários SPs em Doing, indicar o slug:\n{opts}")
    return doing[0].path.resolve()


def check_delta(body):
    """O handoff só leva o delta: ≤MAX_BODY_LINES linhas e sem repetir secções 1-8 do SP."""
    lines = body.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > MAX_BODY_LINES:
        raise HandoffError(f"handoff com {len(lines)} linhas (máx {MAX_BODY_LINES}): só o delta (próximo passo, ficheiros, decisões novas)")
    dup = next((l for l in lines if SP_SECTION_RE.match(l)), None)
    if dup:
        raise HandoffError(f"handoff repete uma secção do SP ({dup.strip()!r}): apontar para o SP em vez de copiar")


def write(path, progress, today=None):
    check_delta(progress)
    path = Path(path)
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise HandoffError("SP sem frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise HandoffError("frontmatter sem fecho")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(1, end):
        if UPDATED_RE.match(lines[i]):
            lines[i] = f"updated: {stamp}{eol}"
            break
    else:
        raise HandoffError("frontmatter sem updated")

    heading = f"## Progresso (sessão {today or date.today().isoformat()})"
    body = progress.replace("\r\n", "\n").strip("\n").replace("\n", eol)
    section = [f"{heading}{eol}", eol, f"{body}{eol}"]

    start = next((i for i in range(end + 1, len(lines)) if lines[i].rstrip("\r\n") == heading), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += eol
        tail = [] if lines[-1].strip() == "" else [eol]
        lines += tail + section
    else:
        stop = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        keep_gap = [eol] if stop < len(lines) else []
        lines[start:stop] = section + keep_gap
    path.write_bytes("".join(lines).encode("utf-8"))


def sync_program(root, child_path):
    """Escreve o estado (pasta) do filho no SP-mãe e devolve a linha do próximo elegível; None se não há mãe."""
    result = sync_program_ready(root, child_path)
    return result[1] if result else None


def sync_program_ready(root, child_path):
    """Como `sync_program`, mas devolve (próximo elegível ou None, linha); None se não há mãe."""
    child_path = Path(child_path).resolve()
    sps = sp_list.collect(root, include_done=True)
    child = next((sp for sp in sps if sp.path.resolve() == child_path), None)
    if child is None or not child.parent:
        return None
    mother = next((sp for sp in sps if sp.project == child.project and sp.slug == child.parent), None)
    if mother is None:
        raise HandoffError(f"SP-mãe '{child.parent}' não encontrado em {child.project}")
    raw = mother.path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    item = next((i for i, line in enumerate(lines) if line.rstrip("\r\n").strip() == f"- slug: {child.slug}"), None)
    if item is not None:
        for i in range(item + 1, len(lines)):
            if lines[i].lstrip().startswith("- ") or not lines[i].startswith(" "):
                break
            if lines[i].strip().startswith("state:"):
                lines[i] = f"{lines[i][:len(lines[i]) - len(lines[i].lstrip())]}state: {child.status}{eol}"
                break
        mother.path.write_bytes("".join(lines).encode("utf-8"))

    groups, _ = sp_list.build_tree(sps)
    kids = next(kids for m, kids in groups if m.slug == mother.slug and m.project == mother.project)
    if kids and all(sp.status == "Done" for sp, _ in kids) and mother.status != "Done":
        return None, (f"programa completo: {mother.slug}; fechar com: "
                      f"python -I scripts/sp-move.py --project {mother.project} {mother.slug} done")
    todo = [(sp, unmet) for sp, unmet in kids if sp.status == "TODO"]
    ready = next((sp for sp, unmet in todo if not unmet), None)
    if ready:
        return ready, f"próximo elegível: {ready.slug}"
    waiting = ", ".join(f"{sp.slug} aguarda: {', '.join(unmet)}" for sp, unmet in todo)
    return None, (f"próximo elegível: nenhum ({waiting})" if waiting else "próximo elegível: nenhum")


def require_doing(path):
    status = sp_list.parse_frontmatter(Path(path).read_text(encoding="utf-8")).get("status", "")
    if status.lower() != "doing":
        raise HandoffError(f"modo automático só com SP em Doing (este está em {status or 'estado desconhecido'})")
