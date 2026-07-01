"""
bug_analysis_agent.py
------------------------
AGENT 2: Bug Analysis Agent

ROLE: Acts like a senior QA lead triaging a bug report.
INPUT: A plain-English bug description (e.g. "Login button not responding
       after entering credentials").
OUTPUT: Structured triage containing:
        - Severity (how bad is the impact)
        - Priority (how urgently it should be fixed)
        - Possible root causes (technical hypotheses)
        - Reproduction steps (how to recreate the bug reliably)

This demonstrates multi-agent specialization: this agent's prompt and
purpose are completely different from the Requirement Agent's, even
though both share the same underlying Gemini connection.
"""

from utils.gemini_client import ask_gemini


def build_prompt(bug_description: str) -> str:
    """Builds the instruction prompt sent to Gemini for this agent's task."""
    return f"""You are a senior QA Lead responsible for triaging incoming
bug reports before they reach the development team. A tester has reported
the following bug:

BUG REPORT:
\"\"\"{bug_description}\"\"\"

Your job: analyze this bug professionally and return your triage using
EXACTLY this markdown structure (no extra preamble):

### 🔥 Severity
(State: Critical / High / Medium / Low, with a one-line justification)

### 📌 Priority
(State: P1 / P2 / P3 / P4, with a one-line justification)

### 🔍 Possible Root Causes
1. ...
2. ...
3. ...

### 🪜 Reproduction Steps
1. ...
2. ...
3. ...

Rules:
- Base severity/priority on realistic software QA standards.
- Root causes should be plausible technical hypotheses (frontend, backend,
  network, validation logic, etc.) — not vague guesses.
- Reproduction steps should be a clean, numbered, step-by-step sequence
  a developer could follow to see the bug themselves.
- Do not repeat the bug report back to me verbatim. Only output the analysis.
"""


def run_bug_analysis_agent(bug_description: str) -> str:
    """
    Main entry point for Agent 2.
    Takes a raw bug description string and returns Gemini's structured
    triage output as markdown text.
    """
    if not bug_description or not bug_description.strip():
        return "⚠️ Please enter a bug description first."

    prompt = build_prompt(bug_description)
    result = ask_gemini(prompt)
    return result
