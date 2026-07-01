"""
agents/test_generator_agent.py
--------------------------------
Agent 5: Playwright POM Test Generator.

Takes a screenshot + DOM + plain-English test cases and returns
professional Playwright POM test code (JavaScript or TypeScript,
ES modules) using the Gemini API.

This is the same generation logic as the standalone "AI Playwright POM
Generator" app, ported to run as another QA Copilot agent. It reuses
QA Copilot's shared per-session API key (utils.gemini_client) instead of
asking for a second key, so it fits the existing "bring your own key"
sidebar flow.

If your utils/gemini_client.py already has a generic call_gemini(...)
helper with quota tracking, swap the call_gemini() function below to use
it instead of calling google-genai directly, for consistent quota
handling across all 5 agents.
"""

import json

from utils.gemini_client import (
    DailyQuotaExceededError,
    NoApiKeyConfiguredError,
    get_user_session_key,
)

DEFAULT_MODEL = "gemini-2.5-flash"


def build_prompt(language: str, dom_text: str, test_cases_input: str) -> str:
    ext = "ts" if language == "TypeScript" else "js"
    ts_hint = (
        "Use TypeScript: strict types, interfaces for data-driven fixtures, "
        "typed Page/Locator parameters, and `.ts` file extensions."
        if language == "TypeScript"
        else "Use modern JavaScript (ES2022+) with `.js` file extensions and JSDoc "
             "type hints on public POM methods."
    )

    return f"""
You are a senior SDET generating a production-quality Playwright automation
suite using the Page Object Model (POM) pattern.

LANGUAGE: {language}
{ts_hint}

STRICT REQUIREMENTS:
- Use ES MODULES only (import/export), never CommonJS (no require/module.exports).
- Import style must look like real relative imports, e.g.:
  import {{ LoginPage }} from "../pages/LoginPage.{ext}";
  import {{ loginData }} from "../data/login.{ext}";
- Use @playwright/test (`import {{ test, expect }} from "@playwright/test";`).
- One Page Object class per distinct screen/component you infer from the
  screenshot, placed in pages/<PageName>.{ext}. Locators must be private
  readonly fields initialized in the constructor from a Playwright `Page`.
  Prefer resilient selectors in this priority order when present in the DOM:
  data-testid > id > name > role/text > css.
- One or more spec files in tests/<feature>.spec.{ext} using
  test.describe / test.beforeEach (for navigation) / test blocks per test case.
- If the test cases imply multiple data sets (e.g. valid/invalid credentials,
  multiple users, form variations), create a data file in
  data/<feature>.{ext} exporting the fixtures, and import it into the spec.
  If no data-driven need exists, do not create a data file.
- Use async/await throughout, meaningful `expect` assertions, and clear
  test titles that map to the requested test cases.
- Code must be clean, commented where non-obvious, and ready to drop into a
  standard Playwright project (tests/, pages/, data/ folders).

CRITICAL — DO NOT MERGE OR SKIP TEST CASES:
- The "Test cases requested" section below is a numbered list. You MUST
  generate exactly ONE `test(...)` block per numbered line, in the same
  order, with NO merging, NO skipping, and NO combining two requirements
  into one test — even if two lines look related (e.g. "minimum length"
  and "maximum length" are two SEPARATE tests, not one).
- Before writing the JSON, silently count the numbered test case lines
  given below. Your final "test_cases" array and your spec file's `test(...)`
  blocks must both contain exactly that many entries, in the same order,
  each with an id TC01, TC02, TC03... matching the input line it came from.
- If a requested case needs a data value not explicitly given (e.g. "minimum
  allowed username length"), make a reasonable assumption, note it in
  "notes", and still implement the test — do not drop it.

INPUTS:
- A screenshot image is attached: use it to understand the visual layout,
  the screens/components involved, and the user flow (what actions are
  possible, what the happy path looks like, what elements exist visually).
- DOM / HTML of the app (use this as the source of truth for real selectors
  and element attributes):
-----
{dom_text if dom_text.strip() else "(no DOM provided — infer reasonable selectors from the screenshot and add TODO comments where selectors are guessed)"}
-----
- Test cases requested by the QA engineer:
-----
{test_cases_input if test_cases_input.strip() else "(no explicit test cases provided — derive sensible core test cases from the screenshot and DOM)"}
-----

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown fences, no prose outside the JSON) matching
exactly this schema:

{{
  "files": [
    {{"path": "pages/LoginPage.{ext}", "content": "..."}},
    {{"path": "tests/login.spec.{ext}", "content": "..."}},
    {{"path": "data/login.{ext}", "content": "..."}}
  ],
  "test_cases": [
    {{
      "id": "TC01",
      "title": "short title",
      "description": "what is being verified",
      "priority": "High | Medium | Low",
      "data_driven": true
    }}
  ],
  "notes": "any assumptions made (e.g. guessed selectors, inferred flows)"
}}

Only include a data file entry in "files" if it is actually needed.
Every test case in "test_cases" must correspond to an actual `test(...)`
block generated in the spec file(s).
""".strip()


def call_gemini(api_key: str, model_name: str, prompt: str, screenshot_bytes: bytes, mime_type: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    contents = [prompt]
    if screenshot_bytes:
        contents.append(types.Part.from_bytes(data=screenshot_bytes, mime_type=mime_type))

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.4,
        max_output_tokens=16384,
    )
    try:
        response = client.models.generate_content(
            model=model_name, contents=contents, config=config
        )
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            raise DailyQuotaExceededError(
                "Your Gemini API key has hit its rate/quota limit. Wait a bit "
                "and try again, or check your plan at https://ai.dev/rate-limit."
            ) from e
        raise
    return response.text


def fallback_result(language: str, test_cases_input: str) -> dict:
    """Structural skeleton used when no API key is available."""
    ext = "ts" if language == "TypeScript" else "js"
    lines = [l.strip("-• ").strip() for l in test_cases_input.splitlines() if l.strip()]
    if not lines:
        lines = ["Verify the primary user flow works as expected"]

    test_cases = []
    test_blocks = []
    for i, line in enumerate(lines, start=1):
        tc_id = f"TC{i:02d}"
        title = line[:80]
        test_cases.append(
            {
                "id": tc_id,
                "title": title,
                "description": line,
                "priority": "Medium",
                "data_driven": False,
            }
        )
        test_blocks.append(
            f'  test("{tc_id}: {title}", async ({{ page }}) => {{\n'
            f'    // TODO: implement steps for: {line}\n'
            f'    const app = new AppPage(page);\n'
            f'    await app.goto();\n'
            f'    // await expect(...).toBeVisible();\n'
            f'  }});'
        )

    page_object = f"""// pages/AppPage.{ext}
export class AppPage {{
  constructor(page) {{
    this.page = page;
    // TODO: replace with real selectors once a DOM is provided
    this.primaryAction = page.locator('[data-testid="primary-action"]');
  }}

  async goto() {{
    await this.page.goto("/");
  }}
}}
"""

    spec = f"""// tests/app.spec.{ext}
import {{ test, expect }} from "@playwright/test";
import {{ AppPage }} from "../pages/AppPage.{ext}";

test.describe("Generated suite (fallback skeleton — add a Gemini API key for full generation)", () => {{
{chr(10).join(test_blocks)}
}});
"""

    return {
        "files": [
            {"path": f"pages/AppPage.{ext}", "content": page_object},
            {"path": f"tests/app.spec.{ext}", "content": spec},
        ],
        "test_cases": test_cases,
        "notes": (
            "No Gemini API key was found for this session, so this is a "
            "structural skeleton only. Add your key in the sidebar and "
            "re-generate for real selectors and fully implemented steps."
        ),
    }


def run_test_generation_agent(
    language: str,
    dom_text: str,
    test_cases_input: str,
    screenshot_bytes: bytes,
    screenshot_mime: str,
    model_name: str = DEFAULT_MODEL,
) -> dict:
    """
    Main entry point for the tab. Returns a dict:
    {"files": [...], "test_cases": [...], "notes": "..."}

    Raises DailyQuotaExceededError if the shared session key is rate-limited,
    matching the behavior of the other 4 agents in this app.
    """
    prompt = build_prompt(language, dom_text, test_cases_input)

    api_key = get_user_session_key()
    if not api_key:
        # Should not normally happen since app.py gates on a key before
        # showing tabs, but fall back gracefully if it does.
        return fallback_result(language, test_cases_input)

    raw = call_gemini(api_key, model_name, prompt, screenshot_bytes, screenshot_mime)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            "The model didn't return valid JSON. Try again, or switch models."
        ) from e


# ---------------------------------------------------------------------------
# Phase 2: incremental "Add Requirements" flow for an existing saved project.
# Does NOT regenerate the whole suite — asks Gemini for only the new/modified
# files and the new test cases, given the existing project as context.
# ---------------------------------------------------------------------------

def next_test_case_number(previous_test_cases: list) -> int:
    """Given existing test cases like TC01, TC02..., return the next free number."""
    max_n = 0
    for tc in previous_test_cases:
        digits = "".join(ch for ch in str(tc.get("id", "")) if ch.isdigit())
        if digits:
            max_n = max(max_n, int(digits))
    return max_n + 1


def build_add_requirements_prompt(
    language: str,
    previous_files: list,
    previous_test_cases: list,
    new_dom_text: str,
    requirements_description: str,
    additional_test_cases_input: str,
    next_tc_number: int,
) -> str:
    ext = "ts" if language == "TypeScript" else "js"

    prev_files_block = "\n\n".join(
        f'--- FILE: {f.get("path")} ---\n{f.get("content", "")}'
        for f in previous_files
    ) or "(no previous files)"

    prev_cases_block = "\n".join(
        f'{tc.get("id", "")}: {tc.get("title", "")}' for tc in previous_test_cases
    ) or "(no previous test cases)"

    return f"""
You are extending an EXISTING Playwright POM automation suite with new
requirements. Do NOT regenerate the whole suite from scratch — only produce
what is new or needs to change.

LANGUAGE: {language} (.{ext} files, ES modules, same conventions as before)

EXISTING PROJECT FILES (context — reuse existing classes/selectors/imports
where still valid; do not duplicate logic that already exists):
=====
{prev_files_block}
=====

EXISTING TEST CASES ALREADY IMPLEMENTED (do not repeat or renumber these):
=====
{prev_cases_block}
=====

NEW INPUTS:
- An updated screenshot is attached, showing the new/changed UI.
- Updated DOM / HTML (source of truth for new selectors):
-----
{new_dom_text if new_dom_text.strip() else "(no DOM provided — infer from the screenshot)"}
-----
- Additional requirement described by the QA engineer:
-----
{requirements_description if requirements_description.strip() else "(no description given — infer the new requirement from the screenshot/DOM)"}
-----
- Additional test cases requested (positive / negative / edge cases), one
  per numbered line. Same rule as before: one test per line, no merging,
  no skipping:
-----
{additional_test_cases_input if additional_test_cases_input.strip() else "(no explicit list — derive sensible positive/negative/edge cases for the new requirement)"}
-----

STRICT REQUIREMENTS:
- Return ONLY the NEW or MODIFIED files needed for this additional
  requirement. Do not re-emit files that don't need any change.
- If an existing Page Object needs new locators/methods, return the FULL
  updated content of that file (not a diff), so it can directly replace
  the old one on disk.
- New test case IDs must continue numbering from TC{next_tc_number:02d}
  onward, in the same order as the additional test cases listed above.
- Follow the same ES module, POM, and selector-priority conventions
  (data-testid > id > name > role/text > css) as the existing project.
- Use async/await and meaningful `expect` assertions, as before.

OUTPUT FORMAT — return ONLY valid JSON, no markdown fences, no prose:
{{
  "files": [
    {{"path": "pages/SomePage.{ext}", "content": "... FULL file content ..."}}
  ],
  "test_cases": [
    {{"id": "TC{next_tc_number:02d}", "title": "...", "description": "...", "priority": "High | Medium | Low", "data_driven": false}}
  ],
  "notes": "assumptions made, and which files were newly created vs modified"
}}
""".strip()


def add_requirements_fallback(language: str, additional_test_cases_input: str, next_tc_number: int) -> dict:
    """Structural skeleton used when no API key is available."""
    ext = "ts" if language == "TypeScript" else "js"
    lines = [l.strip("-• ").strip() for l in additional_test_cases_input.splitlines() if l.strip()]
    if not lines:
        lines = ["Verify the additional requirement works as expected"]

    test_cases = []
    test_blocks = []
    for offset, line in enumerate(lines):
        n = next_tc_number + offset
        tc_id = f"TC{n:02d}"
        title = line[:80]
        test_cases.append(
            {
                "id": tc_id,
                "title": title,
                "description": line,
                "priority": "Medium",
                "data_driven": False,
            }
        )
        test_blocks.append(
            f'  test("{tc_id}: {title}", async ({{ page }}) => {{\n'
            f'    // TODO: implement steps for: {line}\n'
            f'  }});'
        )

    spec = f"""// tests/additional.spec.{ext}
import {{ test, expect }} from "@playwright/test";

test.describe("Additional requirements (fallback skeleton — add a Gemini API key for full generation)", () => {{
{chr(10).join(test_blocks)}
}});
"""
    return {
        "files": [{"path": f"tests/additional.spec.{ext}", "content": spec}],
        "test_cases": test_cases,
        "notes": "No Gemini API key found for this session — fallback skeleton only.",
    }


def run_add_requirements_agent(
    language: str,
    previous_files: list,
    previous_test_cases: list,
    new_dom_text: str,
    requirements_description: str,
    additional_test_cases_input: str,
    screenshot_bytes: bytes,
    screenshot_mime: str,
    model_name: str = DEFAULT_MODEL,
) -> dict:
    """
    Returns ONLY the new/modified files + new test cases for the additional
    requirement — the caller is responsible for merging this into the
    saved project (replace files by path, append test cases).
    """
    next_tc_number = next_test_case_number(previous_test_cases)
    prompt = build_add_requirements_prompt(
        language,
        previous_files,
        previous_test_cases,
        new_dom_text,
        requirements_description,
        additional_test_cases_input,
        next_tc_number,
    )

    api_key = get_user_session_key()
    if not api_key:
        return add_requirements_fallback(language, additional_test_cases_input, next_tc_number)

    raw = call_gemini(api_key, model_name, prompt, screenshot_bytes, screenshot_mime)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            "The model didn't return valid JSON. Try again, or switch models."
        ) from e