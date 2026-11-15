"""The public repo must not carry internal working notes (see scripts/check_public_hygiene.py)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_public_hygiene", ROOT / "scripts" / "check_public_hygiene.py")
hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hygiene)


def test_repo_has_no_internal_notes():
    assert hygiene.check(hygiene.tracked_files()) == []


def test_flags_internal_files_and_markers(tmp_path, monkeypatch):
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "x.md").write_text("draft\n", encoding="utf-8")
    (tmp_path / "STATUS.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Keep private.\nsee /workspace/foo\n", encoding="utf-8")
    (tmp_path / "clean.md").write_text("nothing internal here\n", encoding="utf-8")
    monkeypatch.setattr(hygiene, "ROOT", tmp_path)
    problems = hygiene.check(["drafts/x.md", "STATUS.md", "notes.md", "clean.md"])
    assert any(p.startswith("drafts/x.md") for p in problems)
    assert any(p.startswith("STATUS.md") for p in problems)
    assert sum(p.startswith("notes.md") for p in problems) == 2
    assert not any(p.startswith("clean.md") for p in problems)
