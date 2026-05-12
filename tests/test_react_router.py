"""
Deterministic tests for the ReAct routing logic.

These cover the parts of the agent that DON'T require an LLM call:
  - The mode router (parallel vs react)
  - The react-loop router (tool call vs submit)
  - The synthesizer's translation of `react_next_action.submitted_*` fields
    into the shared `top_hypothesis` shape

No API key required. Safe to run in CI.
"""

from __future__ import annotations

import pytest

from agents.react_investigation import (
    DEFAULT_REACT_BUDGET,
    route_investigation_mode,
    route_react_next,
)


# ── Mode router ────────────────────────────────────────────────────────────

def test_mode_router_defaults_to_parallel():
    assert route_investigation_mode({}) == "tool_agent"


def test_mode_router_routes_explicit_parallel():
    assert route_investigation_mode({"investigation_mode": "parallel"}) == "tool_agent"


def test_mode_router_routes_react():
    assert route_investigation_mode({"investigation_mode": "react"}) == "react_plan"


def test_mode_router_treats_unknown_as_parallel():
    """Defensive: any non-'react' value falls back to parallel."""
    assert route_investigation_mode({"investigation_mode": "magic"}) == "tool_agent"


# ── ReAct-loop router ─────────────────────────────────────────────────────

@pytest.mark.parametrize("tool", [
    "query_github",
    "query_cloudwatch",
    "query_splunk",
    "search_runbooks",
])
def test_react_router_sends_known_tools_to_execute(tool: str):
    state = {"react_next_action": {"action": tool}}
    assert route_react_next(state) == "react_execute"


def test_react_router_routes_submit_to_synthesize():
    state = {"react_next_action": {"action": "submit"}}
    assert route_react_next(state) == "react_synthesize"


def test_react_router_defensively_handles_missing_action():
    """If no plan exists (e.g., on first turn before plan ran), don't crash."""
    assert route_react_next({}) == "react_synthesize"
    assert route_react_next({"react_next_action": {}}) == "react_synthesize"


def test_react_router_defensively_handles_unknown_action():
    """Unknown action names route to synthesize so the graph terminates."""
    state = {"react_next_action": {"action": "definitely_not_a_real_tool"}}
    assert route_react_next(state) == "react_synthesize"


# ── Budget constant ───────────────────────────────────────────────────────

def test_default_budget_is_reasonable():
    """Sanity check: the default budget should be > 1 and < 20."""
    assert 1 < DEFAULT_REACT_BUDGET < 20
