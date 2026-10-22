#!/usr/bin/env python3
"""Testes da checklist mecânica de fecho de árvore (`sp-list.py --tree-closed`). Correr: python -I scripts/test_michi_tree_close.py"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "sp-list.py"


def write_sp(root, folder, slug, parent="", depends_on="", kind="", status=None):
    d = root / "proj" / "sp" / folder
    d.mkdir(parents=True, exist_ok=True)
    fm = [f"status: {status or folder}", f"slug: {slug}", "project: proj", "priority: P2", "created: 2026-10-20"]
    if parent:
        fm.append(f"parent: {parent}")
    if depends_on:
        fm.append(f"depends_on: [{depends_on}]")
    if kind:
        fm.append(f"kind: {kind}")
    (d / f"{slug}-2026-10-20.md").write_text("---\n" + "\n".join(fm) + "\n---\n# x\n", encoding="utf-8")


def run(root, slug, repo):
    p = subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(root), "--repo", str(repo),
                        "--tree-closed", slug], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, p.stdout


class TreeClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "vault"
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        (self.repo / "COMMIT_x.md").write_text("## Mensagem\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def tree(self, neto="Done", filho="Done", mae="Done"):
        write_sp(self.root, mae, "mae", kind="program")
        write_sp(self.root, filho, "filho", parent="mae")
        write_sp(self.root, neto, "neto", parent="filho", depends_on="filho")

    def test_closed_from_any_node(self):
        self.tree()
        for slug in ("mae", "filho", "neto"):
            rc, out = run(self.root, slug, self.repo)
            self.assertEqual(rc, 0, out)
            self.assertIn("ÁRVORE FECHADA", out)

    def test_open_child_blocks(self):
        self.tree(filho="Doing")
        rc, out = run(self.root, "neto", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("filho", out)

    def test_open_grandchild_blocks(self):
        self.tree(neto="TODO")
        rc, out = run(self.root, "mae", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("neto", out)

    def test_status_folder_mismatch_blocks(self):
        write_sp(self.root, "Done", "mae", kind="program", status="Doing")
        rc, out = run(self.root, "mae", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("status≠pasta", out)

    def test_missing_commit_md_blocks(self):
        self.tree()
        (self.repo / "COMMIT_x.md").unlink()
        rc, out = run(self.root, "mae", self.repo)
        self.assertEqual(rc, 1)
        self.assertIn("COMMIT_", out)

    def test_unknown_slug(self):
        self.tree()
        rc, _ = run(self.root, "nada", self.repo)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
