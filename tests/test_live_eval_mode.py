"""`run_evals.py --live` must skip the mock-only fault-injection cases instead of grading them against a real model."""
import importlib.util
import json
import sys
from pathlib import Path

from copilot.llm import MockClient

EVALS = Path(__file__).resolve().parents[1] / "evals"


def _load():
    spec = importlib.util.spec_from_file_location("run_evals", EVALS / "run_evals.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_live_mode_skips_mock_only_cases(monkeypatch, capsys):
    mod = _load()
    cases = json.loads((EVALS / "cases.json").read_text())
    mock_only = [c["id"] for c in cases if "llm" in c]
    assert mock_only, "expected some fault-injection cases"

    constructed = []
    monkeypatch.setattr(mod, "AnthropicClient", lambda: constructed.append(1) or MockClient())  # no network
    monkeypatch.setattr(sys, "argv", ["run_evals.py", "--live"])
    mod.main()
    out = capsys.readouterr().out

    assert f"skipping {len(mock_only)} mock-only" in out
    assert not any(cid in out for cid in mock_only)          # none of them were run or printed
    assert len(constructed) == len(cases) - len(mock_only)   # one live client per case that did run
