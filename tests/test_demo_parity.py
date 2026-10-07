"""The browser demo carries a JavaScript port of the guardrails and Critic. This test runs that port in node
against the Python originals so the two cannot silently drift apart.

Skips when node is missing. Set REQUIRE_NODE=1 (CI does) to fail instead.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from copilot import guardrails as g

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo" / "index.html"
CASES = json.loads(Path(__file__).with_name("parity_cases.json").read_text(encoding="utf-8"))

RUNNER = r"""
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify({
  families: Object.fromEntries(Object.entries(INFLATION_FAMILIES).map(([k, v]) => [k, [...v].sort()])),
  patterns: INJECTION_PATTERNS,
  pii: cases.pii.map(redactPII),
  jd: cases.jd.map(checkJob),
  bullets: cases.bullets.map(c => provenance(c.bullet, c.sources).supported),
  summaries: cases.summaries.map(c => summaryIssues(
    c.summary, { summary: c.source_summary, bullets: c.bullets, skills: c.skills }, c.title).length),
}));
"""


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        if os.environ.get("REQUIRE_NODE"):
            pytest.fail("node is required for the demo parity test but was not found")
        pytest.skip("node not installed")
    html = DEMO.read_text(encoding="utf-8")
    m = re.search(r"// <parity:begin>(.*?)// <parity:end>", html, re.S)
    assert m, "parity markers missing from demo/index.html"
    script = tmp_path_factory.mktemp("parity") / "run.js"
    script.write_text(m.group(1) + RUNNER, encoding="utf-8")
    out = subprocess.run([node, str(script)], input=json.dumps(CASES), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _same(name, inputs, py, js_out):
    bad = [(i, p, j) for i, p, j in zip(inputs, py, js_out) if p != j]
    assert not bad, f"{name}: demo and Python disagree on {len(bad)} case(s): {bad[:3]}"


def test_inflation_word_lists_match(js):
    py = {fam: sorted(words) for fam, words in g._INFLATION_FAMILIES.items()}
    assert js["families"] == py


def test_injection_pattern_lists_match(js):
    assert js["patterns"] == g.INJECTION_PATTERNS


def test_pii_redaction_matches(js):
    _same("redact_pii", CASES["pii"], [g.redact_pii(t) for t in CASES["pii"]], js["pii"])


def test_job_description_check_matches(js):
    py = []
    for t in CASES["jd"]:
        c = g.check_job_description(t)
        py.append({"ok": c.ok, "cleaned": c.cleaned_jd, "flags": c.flags})
    got = [{"ok": r["ok"], "cleaned": r["cleaned"], "flags": r["flags"]} for r in js["jd"]]
    _same("check_job_description", CASES["jd"], py, got)


def test_bullet_verdicts_match(js):
    py = [g._bullet_problem(c["bullet"], c["sources"]) is None for c in CASES["bullets"]]
    _same("bullet supported", [c["bullet"] for c in CASES["bullets"]], py, js["bullets"])


def test_summary_verdicts_match(js):
    py = [len(g.check_summary(c["summary"], c["source_summary"], c["bullets"], c["skills"], c["title"]))
          for c in CASES["summaries"]]
    _same("summary issue count", [c["summary"] for c in CASES["summaries"]], py, js["summaries"])
