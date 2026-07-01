"""
requirement_agent.py
----------------------
AGENT 1: Requirement Agent

ROLE: Acts like a QA engineer reading a feature requirement.
INPUT: A plain-English requirement/feature description (e.g. "User login page
       with username and password").
OUTPUT: Structured test cases split into:
        - Positive test cases (happy path / expected behavior)
        - Negative test cases (invalid input, error handling)
        - Edge cases (boundary conditions, unusual scenarios)

This demonstrates the "Agent skill" concept: a focused, single-purpose
agent with a well-engineered prompt that reliably returns structured,
parseable output.
"""

from utils.gemini_client import ask_gemini


def build_prompt(requirement: str) -> str:
    """Builds the instruction prompt sent to Gemini for this agent's task."""
    return f"""You are an expert QA / Software Testing Engineer with 10+ years
of experience in manual and automation testing. A developer has given you
the following feature requirement:

REQUIREMENT:
\"\"\"{requirement}\"\"\"

Your job: generate a thorough test case suite for this requirement.

Return your answer using EXACTLY this markdown structure (no extra preamble):

### ✅ Positive Test Cases
1. ...
2. ...

### ❌ Negative Test Cases
1. ...
2. ...

### ⚠️ Edge Cases
1. ...
2. ...

Rules:
- Each test case must be a single, clear, actionable sentence.
- Cover realistic real-world QA scenarios (UI, validation, security basics,
  performance-related edge cases where relevant).
- Provide at least 4 test cases per section.
- Do not repeat the requirement back to me. Only output the test cases.
"""


def run_requirement_agent(requirement: str) -> str:
    """
    Main entry point for Agent 1.
    Takes a raw requirement string and returns Gemini's structured
    test case output as markdown text.
    """
    if not requirement or not requirement.strip():
        return "⚠️ Please enter a requirement first."

    prompt = build_prompt(requirement)
    result = ask_gemini(prompt)
    return result
