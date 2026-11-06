"""Tests for the package scripts: the privacy gate, and refcheck.

    python -m pytest scripts/tests -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refcheck  # noqa: E402
import sanitize  # noqa: E402


def test_selftest_every_check_can_fail():
    assert sanitize.selftest() == 0


@pytest.mark.parametrize("n,dummy", [
    ("100000000001", True), ("111111111111", True), ("123456789012", True), ("00000", True),
    ("264800000012", False), ("60601", False), ("99501", False), ("387654321012", False),
])
def test_dummy_numbers(n, dummy):
    assert sanitize.is_dummy_number(n) is dummy


def test_denylist_boundaries_and_env(tmp_path):
    fake = "-".join(["PRD", "abcdef123456"])  # built at run time so secret scanners don't flag this file
    env = tmp_path / "source.env"
    env.write_text(f"EBAY_ENVIRONMENT=production\nEBAY_CLIENT_SECRET={fake}\nEMPTY=\n", encoding="utf-8")
    deny = tmp_path / "scrub.local.txt"
    deny.write_text(f"# comment\nshopname\n@env {env}\n", encoding="utf-8")
    terms, problems = sanitize.load_denylist(deny)
    assert problems == [] and fake in terms and "production" not in terms
    pattern = sanitize.deny_pattern(terms)
    assert pattern.search("seller ShopName ships")
    assert not pattern.search("myshopnames")  # needs a boundary on both sides
    assert pattern.search(f"key={fake}")


def test_denylist_missing_env_file_is_a_problem(tmp_path):
    deny = tmp_path / "scrub.local.txt"
    deny.write_text("@env does/not/exist.env\n", encoding="utf-8")
    assert sanitize.load_denylist(deny)[1]


def test_empty_credential_does_not_read_next_line(tmp_path):
    (tmp_path / ".env.example").write_text("EBAY_CLIENT_ID=\nEBAY_CLIENT_SECRET=\n", encoding="utf-8")
    assert sanitize.check_secrets(tmp_path, [tmp_path / ".env.example"]) == []


def test_missing_denylist_fails_closed(tmp_path):
    (tmp_path / "a.md").write_text("hello\n", encoding="utf-8")
    code, results = sanitize.verify(tmp_path, tmp_path / "scrub.local.txt", gitleaks=False, quiet=True)
    assert code == 2 and "not found" in results[2][0]
    code, _ = sanitize.verify(tmp_path, tmp_path / "scrub.local.txt", use_denylist=False,
                              gitleaks=False, quiet=True)
    assert code == 0


def test_refcheck_resolution(tmp_path):
    (tmp_path / "core" / "tools").mkdir(parents=True)
    (tmp_path / "core" / "tools" / "x.py").write_text("", encoding="utf-8")
    doc = tmp_path / "README.md"
    doc.write_text(
        "Run `python core/tools/x.py` and `tools/x.py`. Not paths: `USED/3000`, `@AGENTS.md`, `/sell/v1`.\n"
        "Runtime: `listings/archive/` and `.env`. [ok](core/tools/x.py) [bad](core/nope.md)\n"
        "```\npython tools/gone.py\n```\n", encoding="utf-8")
    failures = refcheck.check(tmp_path, refcheck.shipped_files(tmp_path))
    assert failures == ["README.md: link target not found: core/nope.md",
                        "README.md: path not found: tools/gone.py"]
