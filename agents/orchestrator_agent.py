"""
orchestrator_agent.py
------------------------
AGENT 4: Orchestrator Agent (Coordinator)

ROLE: This is the "manager" agent. It does NOT call Gemini directly itself —
instead, it intelligently calls the other 3 specialist agents in sequence
and merges their outputs into one unified report.

INPUT: A single bug/issue report from the tester (one text box, one click).
OUTPUT: A combined report containing:
    1. Bug triage (from Bug Analysis Agent)
    2. Suggested regression test cases (from Requirement Agent, derived
       from the bug so the same bug doesn't slip through again)
    3. Evidence checklist (from Evidence Agent)

WHY THIS MATTERS (for the hackathon rubric):
This is what makes QA Copilot an actual *multi-agent system* rather than
3 separate single-purpose tools living in the same UI. The Orchestrator
demonstrates agent-to-agent coordination: one entry point, multiple
specialist agents invoked automatically, results synthesized together.

This mirrors a real QA workflow: a tester finds a bug -> files it ->
needs test cases to prevent regression -> needs evidence attached.
Today that's 3 manual steps. The Orchestrator turns it into 1 step.
"""

from agents.bug_analysis_agent import run_bug_analysis_agent
from agents.requirement_agent import run_requirement_agent
from agents.evidence_agent import run_evidence_agent
from utils.gemini_client import ask_gemini


def build_regression_requirement(bug_description: str) -> str:
    """
    The Requirement Agent normally takes a *feature* requirement, not a bug.
    To reuse it inside the orchestrator, we first reframe the bug as a
    'requirement' so the Requirement Agent generates regression-focused
    test cases that specifically guard against this bug happening again.
    """
    reframe_prompt = f"""A bug was reported:
\"\"\"{bug_description}\"\"\"

In ONE sentence, rewrite this as the underlying feature/functional
requirement that this bug violates. For example, if the bug is
"Login button not responding after entering credentials", the
requirement is "User must be able to log in successfully using valid
username and password." Output ONLY the single requirement sentence,
nothing else."""
    return ask_gemini(reframe_prompt).strip()


def run_orchestrator_agent(bug_description: str) -> dict:
    """
    Main entry point for the Orchestrator Agent.

    Runs all 3 specialist agents in sequence and returns a dictionary
    with each section, so the UI can render them as one cohesive report.

    Returns:
        dict with keys: 'triage', 'requirement_used', 'regression_tests',
        'evidence'
    """
    if not bug_description or not bug_description.strip():
        return {
            "error": "⚠️ Please enter a bug or issue description first."
        }

    # Step 1: Triage the bug (severity, priority, root cause, repro steps)
    triage = run_bug_analysis_agent(bug_description)

    # Step 2: Reframe the bug as a requirement, then generate regression
    # test cases so this bug class doesn't slip through again
    requirement_used = build_regression_requirement(bug_description)
    regression_tests = run_requirement_agent(requirement_used)

    # Step 3: Generate the evidence checklist for the original bug
    evidence = run_evidence_agent(bug_description)

    return {
        "triage": triage,
        "requirement_used": requirement_used,
        "regression_tests": regression_tests,
        "evidence": evidence,
    }
