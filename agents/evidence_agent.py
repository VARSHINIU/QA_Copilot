"""
evidence_agent.py
--------------------
AGENT 3: Evidence Agent

ROLE: Acts like a QA engineer preparing a bug report for developers and
      figuring out exactly what proof/evidence should be attached.
INPUT: A bug or issue description (can reuse the same input as Agent 2,
       or be a standalone description).
OUTPUT: A checklist of evidence to collect:
        - Logs required
        - Screenshots required
        - Browser/environment info needed
        - Console errors to check for

This agent completes the workflow: Requirement Agent designs tests ->
Bug Analysis Agent triages a found bug -> Evidence Agent tells the tester
exactly what to attach to the bug ticket so developers can act on it fast.

MULTIMODAL UPGRADE:
This agent can also directly ANALYZE an uploaded screenshot. Instead of
only suggesting "take a screenshot of the error," the tester can upload
the screenshot they already have, and Gemini will look at it and point
out visible errors, broken UI elements, or anything notable — turning
the Evidence Agent from "tells you what to collect" into "actively
inspects what you collected."
"""

from utils.gemini_client import ask_gemini, ask_gemini_with_image


def build_prompt(issue_description: str) -> str:
    """Builds the instruction prompt sent to Gemini for this agent's task."""
    return f"""You are a meticulous QA engineer who specializes in writing
high-quality, developer-friendly bug tickets. You know that the right
evidence attached to a bug ticket can save developers hours of back-and-forth.

A tester is filing a ticket for this issue:

ISSUE:
\"\"\"{issue_description}\"\"\"

Your job: tell the tester exactly what evidence they should collect and
attach to the ticket. Return your answer using EXACTLY this markdown
structure (no extra preamble):

### 🧾 Logs Required
1. ...
2. ...

### 📸 Screenshots Required
1. ...
2. ...

### 🌐 Browser / Environment Info
1. ...
2. ...

### 🖥️ Console Errors to Check
1. ...
2. ...

Rules:
- Be specific to the type of issue described (e.g. UI bug vs API bug vs
  performance issue may need different evidence).
- Keep each point short, practical, and actionable for a tester who may
  not be highly technical.
- Do not repeat the issue description back to me. Only output the checklist.
"""


def run_evidence_agent(issue_description: str) -> str:
    """
    Main entry point for Agent 3.
    Takes a raw issue description string and returns Gemini's structured
    evidence checklist as markdown text.
    """
    if not issue_description or not issue_description.strip():
        return "⚠️ Please enter an issue description first."

    prompt = build_prompt(issue_description)
    result = ask_gemini(prompt)
    return result


def build_screenshot_prompt(issue_description: str) -> str:
    """
    Builds the instruction prompt for analyzing an uploaded screenshot,
    optionally with the tester's text description of the issue for context.
    """
    context_line = (
        f'The tester described the issue as: "{issue_description.strip()}"\n\n'
        if issue_description and issue_description.strip()
        else ""
    )
    return f"""You are a meticulous QA engineer reviewing a screenshot
attached to a bug ticket.

{context_line}Look carefully at the attached screenshot and report what
you observe. Return your answer using EXACTLY this markdown structure
(no extra preamble):

### 👀 What's Visible in the Screenshot
(Describe what the screenshot shows — page/screen, key UI elements, state)

### 🚩 Issues Spotted
1. ...
2. ...
(List any visible errors, broken layout, missing elements, error messages,
console warnings if shown, or anything that looks wrong. If nothing looks
wrong, say so clearly instead of inventing issues.)

### 📌 Suggested Next Step for the Tester
(One or two sentences on what additional evidence, if any, would still
help developers — e.g. "also capture the Network tab" or "this looks
sufficient on its own.")

Rules:
- Only describe what is actually visible. Do not guess at backend causes
  you cannot see in the image.
- Be specific (e.g. name the exact error text if readable, not just
  "there's an error message").
"""


def run_screenshot_analysis(image_bytes: bytes, mime_type: str, issue_description: str = "") -> str:
    """
    Multimodal entry point for Agent 3.
    Takes the raw bytes of an uploaded screenshot (plus optional text
    context from the tester) and returns Gemini's visual analysis as
    markdown text.

    image_bytes: raw bytes from Streamlit's uploaded_file.getvalue()
    mime_type:   e.g. 'image/png' or 'image/jpeg'
    issue_description: optional free-text context from the tester
    """
    if not image_bytes:
        return "⚠️ Please upload a screenshot first."

    prompt = build_screenshot_prompt(issue_description)
    result = ask_gemini_with_image(prompt, image_bytes, mime_type)
    return result
