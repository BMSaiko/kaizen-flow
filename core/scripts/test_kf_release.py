import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kf_release as r

CL = "# Changelog\n\n## [Unreleased]\n\n### Added\n- Coisa nova\n\n## [0.4.0] - 2026-11-23\n\n### Fixed\n- Velho\n"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def commit(repo, msg, nome="f.txt"):
    (repo / nome).write_text(msg)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", msg)


def fixture(tmp_path, changelog=CL):
    remoto = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remoto)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    (repo / "package.json").write_text(json.dumps({"name": "x", "version": "0.4.0"}, indent=2) + "\n")
    (repo / "CHANGELOG.md").write_text(changelog)
    commit(repo, "chore: base", "a.txt")
    git(repo, "tag", "v0.4.0")
    git(repo, "remote", "add", "origin", str(remoto))
    git(repo, "push", "-q", "origin", "main")
    return repo


def test_bump_por_commits():
    assert r.calcular_bump([("fix: a", "")]) == "patch"
    assert r.calcular_bump([("fix: a", ""), ("feat: b", "")]) == "minor"
    assert r.calcular_bump([("feat!: b", "")]) == "major"
    assert r.calcular_bump([("fix(x): b", "BREAKING CHANGE: sim")]) == "major"
    assert r.calcular_bump([("docs: a", ""), ("chore: b", "")]) is None
    assert r.calcular_bump([]) is None


def test_subir_versao():
    assert r.subir("0.4.0", "patch") == "0.4.1"
    assert r.subir("0.4.9", "minor") == "0.5.0"
    assert r.subir("0.4.9", "major") == "1.0.0"


def test_changelog_promove_unreleased():
    novo = r.promover_changelog(CL, "0.5.0", "2026-12-01", [])
    assert "## [Unreleased]\n\n## [0.5.0] - 2026-12-01\n\n### Added\n- Coisa nova" in novo
    assert "## [0.4.0] - 2026-11-23" in novo


def test_changelog_vazio_usa_commits():
    vazio = CL.replace("### Added\n- Coisa nova\n\n", "")
    novo = r.promover_changelog(vazio, "0.5.0", "2026-12-01", [("feat: x y", ""), ("fix(a): z", ""), ("docs: d", "")])
    lancado = novo.split("[0.5.0]")[1].split("[0.4.0]")[0]
    assert "### Added\n- x y" in lancado and "### Fixed\n- z" in lancado and "d\n" not in lancado.replace("Added", "").replace("Fixed", "")


def test_plan_sem_editar(tmp_path, capsys):
    repo = fixture(tmp_path)
    commit(repo, "feat: nova", "b.txt")
    antes = git(repo, "rev-parse", "HEAD")
    assert r.main(["plan", "--repo", str(repo)]) == 0
    assert "0.5.0" in capsys.readouterr().out
    assert git(repo, "rev-parse", "HEAD") == antes and git(repo, "status", "--porcelain") == ""


def test_plan_sem_alteracoes(tmp_path, capsys):
    repo = fixture(tmp_path)
    assert r.main(["plan", "--repo", str(repo)]) == 2


def test_prepare_cria_branch_pr_sem_merge(tmp_path, monkeypatch):
    repo = fixture(tmp_path)
    commit(repo, "fix: corrige", "b.txt")
    chamadas = []
    monkeypatch.setattr(r, "gh", lambda repo, *a: chamadas.append(a) or subprocess.CompletedProcess(a, 0, "https://x/pr/9\n", ""))
    rc = r.main(["prepare", "--repo", str(repo), "--gate", f"{sys.executable} -c pass", "--data", "2026-12-01"])
    assert rc == 0
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "agent/release-0-4-1"
    assert json.loads((repo / "package.json").read_text())["version"] == "0.4.1"
    assert "## [0.4.1] - 2026-12-01" in (repo / "CHANGELOG.md").read_text()
    assert chamadas and chamadas[0][:2] == ("pr", "create")
    assert not any("merge" in c for c in chamadas)
    assert "gate" in chamadas[0][-1].lower() or "gate" in " ".join(chamadas[0]).lower()
    assert git(repo, "tag", "--list", "v0.4.1") == ""


def test_prepare_gate_vermelho_sem_pr(tmp_path, monkeypatch):
    repo = fixture(tmp_path)
    commit(repo, "feat: nova", "b.txt")
    chamadas = []
    monkeypatch.setattr(r, "gh", lambda repo, *a: chamadas.append(a) or subprocess.CompletedProcess(a, 0, "", ""))
    rc = r.main(["prepare", "--repo", str(repo), "--gate", f"{sys.executable} -c 1/0"])
    assert rc == 1 and chamadas == []


def test_prepare_recusa_arvore_suja(tmp_path):
    repo = fixture(tmp_path)
    commit(repo, "feat: nova", "b.txt")
    (repo / "sujo.txt").write_text("x")
    assert r.main(["prepare", "--repo", str(repo), "--gate", f"{sys.executable} -c pass"]) == 4


def _release_feito(tmp_path):
    repo = fixture(tmp_path)
    (repo / "package.json").write_text(json.dumps({"name": "x", "version": "0.5.0"}) + "\n")
    (repo / "CHANGELOG.md").write_text(r.promover_changelog(CL, "0.5.0", "2026-12-01", []))
    commit(repo, "chore: release v0.5.0", "c.txt")
    git(repo, "push", "-q", "origin", "main")
    return repo


def test_publish_recusa_sem_confirmo(tmp_path, capsys):
    repo = _release_feito(tmp_path)
    assert r.main(["publish", "--repo", str(repo)]) == 3
    assert git(repo, "tag", "--list", "v0.5.0") == ""
    assert "--confirmo" in capsys.readouterr().out


def test_publish_com_confirmo_so_empurra_tag(tmp_path):
    repo = _release_feito(tmp_path)
    assert r.main(["publish", "--repo", str(repo), "--confirmo"]) == 0
    assert git(repo, "tag", "--list", "v0.5.0") == "v0.5.0"
    assert "refs/tags/v0.5.0" in git(repo, "ls-remote", "--tags", "origin")


def test_publish_nunca_reescreve_tag(tmp_path):
    repo = _release_feito(tmp_path)
    git(repo, "tag", "v0.5.0")
    assert r.main(["publish", "--repo", str(repo), "--confirmo"]) == 4
    assert git(repo, "ls-remote", "--tags", "origin").count("v0.5.0") == 0


def test_publish_recusa_versao_nao_subida(tmp_path):
    repo = fixture(tmp_path)  # package.json 0.4.0 com tag v0.4.0 já existente
    assert r.main(["publish", "--repo", str(repo), "--confirmo"]) == 4


def test_publish_recusa_fora_de_main(tmp_path):
    repo = _release_feito(tmp_path)
    git(repo, "switch", "-q", "-c", "outro")
    assert r.main(["publish", "--repo", str(repo), "--confirmo"]) == 4
