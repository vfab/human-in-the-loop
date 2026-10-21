"""Tests for the sample-input driven options of the approval and game workflows."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows.approval_workflow import DEFAULT_SCENARIO, EMAIL_SCENARIOS
from workflows.game_workflow import DEFAULT_MAX_NUMBER, _parse_max_number

DASHBOARD_JS = Path(__file__).parent.parent / "static" / "js" / "dashboard.js"


def test_default_scenario_exists():
    assert EMAIL_SCENARIOS[DEFAULT_SCENARIO]


def test_dashboard_approval_samples_match_scenarios():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    block = re.search(r"approval:\s*\[(.*?)\n    \],", js, re.S).group(1)
    values = re.findall(r"value:\s*'([^']+)'", block)
    assert values, "approval samples not found in dashboard.js"
    assert set(values) <= set(EMAIL_SCENARIOS)


def test_dashboard_game_samples_are_valid_ranges():
    js = DASHBOARD_JS.read_text(encoding="utf-8")
    block = re.search(r"game:\s*\[(.*?)\n    \],", js, re.S).group(1)
    values = re.findall(r"value:\s*'([^']+)'", block)
    assert values, "game samples not found in dashboard.js"
    assert all(_parse_max_number(v) == int(v) for v in values)


def test_parse_max_number():
    assert _parse_max_number("50") == 50
    assert _parse_max_number("") == DEFAULT_MAX_NUMBER
    assert _parse_max_number("abc") == DEFAULT_MAX_NUMBER
    assert _parse_max_number("1") == DEFAULT_MAX_NUMBER
    assert _parse_max_number("99999") == DEFAULT_MAX_NUMBER
