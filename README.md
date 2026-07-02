# 🐞 QA Copilot — AI Agent Suite for Testers

**Track:** Agents for Business
**Built for:** Kaggle's 5-Day AI Agents Intensive Vibe Coding Capstone (with Google)

🔗 Live Demo: _[https://testflowai-copilot-builtbyvarshini.streamlit.app/]_<br>
🎥 Video Demo: _[https://youtu.be/AcbMTLvERZc]_

> An AI agent suite for testers that turns a single bug report into full
> triage, regression test cases, and an evidence checklist automatically —
> and turns a screenshot + DOM into ready-to-run Playwright POM automation
> code.

---

## 1. Problem

Manual QA and software testing teams spend a large share of their time on
repetitive, low-creativity tasks:

1. **Writing test cases** from a feature requirement (positive, negative, edge cases)
2. **Triaging bug reports** — deciding severity, priority, likely root cause, and how to reproduce the issue
3. **Figuring out what evidence** (logs, screenshots, browser info, console errors) to attach to a bug ticket so developers can act on it without back-and-forth
4. **Writing automation code** — translating a screenshot/DOM and a list of test cases into working Playwright Page Object Model (POM) test scripts, by hand
5. **Repeatedly updating code and test cases based on additional requirements** updates the previously stored project with the latest test cases and test code.

These tasks are essential but slow, and inconsistent quality between testers
often leads to weak bug tickets, missed edge cases, and automation suites
that take days to scaffold. This directly costs businesses time and money —
every vague bug report, missed test case, or hand-written boilerplate test
file is a delay in the software delivery pipeline.

## 2. Solution

**QA Copilot** is a multi-agent AI assistant that automates these tasks
using five agents, each powered by the Google Gemini API:

| Agent | Input | Output |
|---|---|---|
| **Orchestrator Agent** | A bug report (one input) | Automatically runs the Bug Analysis, Requirement, and Evidence agents and combines their output into one report |
| **Requirement Agent** | A feature requirement (plain English) | Positive, negative, and edge-case test cases |
| **Bug Analysis Agent** | A bug description | Severity, priority, root causes, reproduction steps |
| **Evidence Agent** | An issue description, **or an uploaded screenshot** | Checklist of logs, screenshots, browser info, console errors to collect — **or, if a screenshot is uploaded, a direct visual analysis pointing out what's actually wrong in the image** |
| **Test Generator Agent** | A screenshot + DOM/HTML + plain-English test cases | A production-ready Playwright POM automation suite (JavaScript or TypeScript, ES modules) — Page Objects, spec files, and data fixtures |

The Orchestrator Agent is the centerpiece of the triage side of the system:
it demonstrates true **agent-to-agent coordination**, not just independent
tools sharing a UI. When a tester pastes one bug report, the Orchestrator:
1. Calls the **Bug Analysis Agent** to triage the bug
2. Reframes the bug as a functional requirement, then calls the
   **Requirement Agent** to generate regression test cases that guard
   against the bug recurring
3. Calls the **Evidence Agent** to produce the evidence checklist
4. Merges all three outputs into a single, downloadable bug ticket

The **Test Generator Agent** rounds out the suite by turning the tester's
input directly into runnable code:
- Upload a screenshot + paste the page's DOM/HTML + list out test cases in
  plain English → Gemini (multimodal) returns Page Object classes, spec
  files, and (when needed) data-driven fixture files, all in one JSON payload
  that's rendered as downloadable, ready-to-drop-in project files.
- Projects can be **saved** in-session and revisited later.
- An **"Add Requirements"** flow lets a tester extend a saved project with a
  new screenshot/DOM/requirement — Gemini returns *only* the new or modified
  files, which are merged into the existing project instead of regenerating
  everything from scratch.
- If no Gemini key is available, a structural code **skeleton** (with TODOs)
  is generated instead, so the feature degrades gracefully rather than
  failing outright.

Each agent has its own carefully engineered prompt that constrains Gemini's
output into a consistent, structured, ready-to-use format — so a tester gets
professional, ticket-ready content or working code in seconds instead of
hours.

**📥 Every result is downloadable.** The Orchestrator, Requirement, Bug
Analysis, and Evidence tabs (including the screenshot analysis) each offer
a "Download as Markdown" button, exporting a clean, timestamped bug-ticket
file ready to paste straight into Jira, GitHub Issues, or any tracker. The
Test Generator tab instead offers per-file downloads plus a one-click
"Download Project" `.zip` of the full generated suite — turning AI output
into an actual deliverable, not just on-screen text.

## 3. Architecture

```
qa-copilot/
├── app.py                           # Streamlit UI — sidebar key entry + 5 tabs
├── agents/
│   ├── orchestrator_agent.py        # Agent 0: chains Bug Analysis, Requirement, Evidence agents
│   ├── requirement_agent.py         # Agent 1: requirement -> test cases
│   ├── bug_analysis_agent.py        # Agent 2: bug report -> triage
│   ├── evidence_agent.py            # Agent 3: issue/screenshot -> evidence
│   └── test_generator_agent.py      # Agent 4: screenshot + DOM + test cases -> Playwright POM code
├── utils/
│   ├── gemini_client.py             # Gemini API connection, BYOK key handling, retry logic
│   └── export_utils.py              # Builds downloadable Markdown bug tickets
├── screenshots/
│   ├── Architectural Diagrams/
│   │   ├── Orchestrator_Workflow.png        # shows the Orchestrator and 3 agents workflow
│   │   ├── TestGenerator_Workflow.png       # shows the Test Generator and handling additional Requirements workflow
│   ├── TICKET_DOWNLOADABLE_OUTPUT.png       # Downloadable ticket generated by QA Copilot
│   ├── EVIDENCE_AGENT_IMG_OUTPUT2.png       # Evidence Agent analysis using image input
│   ├── EVIDENCE_AGENT_OUTPUT1.png           # Evidence Agent analysis output
│   ├── HOMEPAGE.png                         # QA Copilot application homepage
│   ├── ORCHESTRATOR_OUTPUT.png              # Orchestrator Agent execution results
│   ├── REQUIREMENT_AGENT_OUTPUT.png         # Requirement Analysis Agent results
│   ├── BUG_ANALYSIS_AGENT.png               # Bug Analysis Agent results
│   ├── TEST_CODE_GENERATOR_OUTPUT.png       # Test Generator Agent — generated Playwright POM code
│   ├── TEST_CASE_GENERATOR_OUTPUT.png       # Test Generator Agent — shows the Test cases for the generated Test code
│   ├── ADD_REQUIREMENTS_TESTCODE_OUTPUT.png # Shows the updated codde and test cases after adding the additional requirements
├── requirements.txt                 # Python dependencies
└── .gitignore                       # Excludes .env so any local key is never committed
```

**Flow (single agent tabs):** User types input → the relevant agent module
builds a structured prompt → `gemini_client.py` sends it to the Gemini API →
the response is rendered back as formatted markdown in the UI, with a
download button to export it as a ticket.

**Flow (Orchestrator tab):** User pastes one bug report → Orchestrator calls
Bug Analysis Agent → reframes the bug as a requirement and calls Requirement
Agent → calls Evidence Agent → all three outputs are merged into one
downloadable bug ticket. Session memory (`st.session_state`) also carries
the bug text into the other tabs via an explicit "Use shared context"
button, so the tester doesn't have to retype it if they don't want to.

**Flow (Test Generator tab):** User picks a language (JavaScript/TypeScript)
and Gemini model, uploads a screenshot, pastes/uploads the DOM, and lists
test cases → `test_generator_agent.py` sends the screenshot + prompt to
Gemini with a strict JSON response schema → the returned Page Objects, spec
files, and data fixtures are rendered as code with per-file and full-project
downloads. Projects can be saved to session memory and later extended
through the **Add Requirements** flow, which sends the existing project as
context and merges back only the new/changed files.

### Key concepts demonstrated (per hackathon rubric)

- **Multi-agent system** — five agents total: four specialists (Requirement,
  Bug Analysis, Evidence, Test Generator) plus an Orchestrator that calls
  three of them in sequence and merges their output
  (`agents/orchestrator_agent.py` calling into the other agent modules)
- **Agent skills** — each agent is a self-contained "skill": a single
  responsibility, a structured prompt, and a parser-friendly output format
- **Agent coordination / session memory** — the Orchestrator's bug context
  can be pulled into other tabs on demand via a "Use shared context" button;
  the Test Generator keeps its own saved-projects memory in
  `st.session_state`, so a tester can run the full workflow once, generate
  automation code, and revisit or extend either without retyping
- **Multimodal input (vision)** — both the Evidence Agent and the Test
  Generator Agent use Gemini's vision capabilities. The Evidence Agent can
  directly analyze an uploaded screenshot
  (`utils/gemini_client.py: ask_gemini_with_image`,
  `agents/evidence_agent.py: run_screenshot_analysis`), pointing out visible
  errors instead of only suggesting what to capture. The Test Generator
  Agent reads a screenshot alongside the DOM to infer page structure and
  generate accurate Playwright selectors and code
  (`agents/test_generator_agent.py: call_gemini`)
- **Structured JSON output for code generation** — the Test Generator Agent
  constrains Gemini to a strict JSON schema (files, test cases, notes) so
  generated code can be reliably parsed, rendered, downloaded, and merged
  into saved projects without brittle text-scraping
  (`agents/test_generator_agent.py: build_prompt`,
  `build_add_requirements_prompt`)
- **Exportable business deliverables** — every triage agent (and the
  combined Orchestrator report) can be downloaded as a ready-to-paste
  Markdown bug ticket (`utils/export_utils.py`), while the Test Generator
  exports actual runnable Playwright project files (individually or as a
  `.zip`) — turning AI output into something a QA team would actually use
  in Jira, GitHub Issues, or a real automation repo
- **Resilience / production-readiness** — all Gemini calls automatically
  retry on transient 503/429 errors with exponential backoff, and cleanly
  distinguish invalid keys, transient errors, and exhausted daily quotas
  (`utils/gemini_client.py: _generate_with_retry`), so a brief Google-side
  hiccup doesn't surface as a failure to the user. The Test Generator also
  falls back to a structural code skeleton if no key is configured, instead
  of failing outright
- **Bring-your-own-key (BYOK) scalability** — each visitor pastes their own
  free Gemini API key into the sidebar; it lives only in their browser
  session (`st.session_state`), is never sent to the developer or stored
  anywhere, and disappears on refresh/close. This lets the app support
  unlimited concurrent users for free, since every visitor's usage counts
  against their own personal daily quota instead of one shared key. All
  five agents, including the Test Generator, share this same session key
  (`utils/gemini_client.py: get_active_keys`, `set_user_session_key`)
- **Security features** — no API key is ever hardcoded or logged. A
  visitor's own key stays in session memory only, entered as a plain text
  field in the sidebar (with a "How do I get a key?" guide built in). For
  the developer's own local testing, an optional fallback key can be set
  via a local `.env` file (excluded via `.gitignore`) or Streamlit Cloud
  "Secrets" — but this is never required for end users of the deployed app
- **Deployability** — the app is deployed for free on Streamlit Community
  Cloud, giving judges a live, public link to test directly with no login

## 4. Tech Stack (100% Free)

| Tool | Purpose | Cost |
|---|---|---|
| Python | Core language | Free |
| Streamlit | Web UI framework | Free |
| Google Gemini API (`google-genai`, free tier) | AI reasoning engine — text + multimodal (vision) | Free |
| Gemini 2.5 Flash (default) / Flash-Latest / 2.5 Pro | Underlying models — selectable in the Test Generator tab | Free tier |
| Playwright (target output) | Automation framework the Test Generator produces code for | Free |
| GitHub | Code hosting | Free |
| Streamlit Community Cloud | App deployment | Free |

## 5. Setup Instructions (Run Locally)

1. **Clone the repo**
   ```bash
   git clone https://github.com/<your-username>/qa-copilot.git
   cd qa-copilot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Add your Gemini API key (for local testing)**
   - Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
   - Create a `.env` file (local environment execution)
   - Paste your key into `.env`:
     ```
     GEMINI_API_KEY=your_actual_key_here
     ```
   - *(This step is only a convenience for local development — see the
     BYOK section below for how the deployed app actually works for
     real users, who never need this file.)*

4. **Run the app**
   ```bash
   python -m streamlit run app.py
   ```

5. Open the local URL Streamlit prints in your terminal (usually `http://localhost:8501`)

> **Note on models:** Gemini 1.5 and 2.0 models were retired by Google in
> early 2026. The app defaults to `gemini-2.5-flash` everywhere. The Test
> Generator tab additionally lets you pick `gemini-flash-latest` or
> `gemini-2.5-pro` for more reliable output on long/complex test case lists.

## 5a. Bring Your Own Key (BYOK) — how this scales to unlimited free users

QA Copilot is designed so that **the developer's own API key is never
shared across visitors**. Instead, each visitor pastes their own free
Gemini API key directly into the app's sidebar — and that one key powers
all five agents, including the Test Generator.

- The key is stored only in `st.session_state` — server-side memory tied
  to that one browser tab, for that one session
- It is **never** sent to the developer, never written to a file or
  database, and **disappears the moment the tab is closed or refreshed**
- A short in-app guide walks first-time visitors through getting a free
  key from Google AI Studio (no credit card required, takes about a minute)
- Because each visitor's usage counts against **their own** free daily
  quota, the app can support unlimited concurrent users for free — no
  single key gets exhausted by traffic from other people

This is implemented in `utils/gemini_client.py` (`get_user_session_key`,
`set_user_session_key`, `get_active_keys`) and wired into the sidebar in
`app.py`. The local `.env` key from Step 3 above is only used as a fallback
during the developer's own testing, and is never required for actual
visitors.

### About free tier daily limits

Gemini's free tier enforces a daily request limit (RPD) that resets at
midnight Pacific Time, tied to the Google Cloud project behind each API
key. Since every visitor brings their own key/project, this limit applies
per-person, not to the app as a whole — so one heavy user can't lock
everyone else out. `gemini_client.py` distinguishes invalid keys, transient
server errors (retried automatically), and exhausted daily quotas
(surfaced clearly so the tester knows to wait or switch keys).

## 6. Example Usage

**Orchestrator Agent input (runs the full triage workflow in one go):**
> Checkout page displays a blank screen after clicking Pay Now.

**Requirement Agent input:**
> User login page with username and password.

**Bug Analysis Agent input:**
> Login button not responding after entering credentials.

**Evidence Agent input:**
> Checkout page crashes when applying a discount code on Safari.

**Test Generator Agent input:**
> Screenshot of a login page + its DOM/HTML, with test cases:
> 1. Verify user can log in with valid email and password
> 2. Verify error message shows for invalid credentials
> 3. Verify 'Forgot password' link navigates to reset page
>
> → Generates `pages/LoginPage.js`, `tests/login.spec.js`, and (if the
> cases imply multiple credential sets) `data/login.js` — downloadable
> individually or as a project `.zip`.

## 7. Future Improvements

- Add MCP server integration so agents can read live bug tickets directly
  from a tool like Jira or GitHub Issues, instead of pasted text
- Add a self-healing locator agent that suggests robust alternatives for
  broken Selenium/Cypress/Playwright selectors when the Test Generator's
  output selectors go stale
- Extend screenshot analysis to compare a "before" and "after" screenshot
  side by side for visual regression checks
- Let the Test Generator Agent target frameworks beyond Playwright
  (Cypress, Selenium) from the same screenshot/DOM/test-case input

---

<i>QA Copilot • Designed and Developed by Varshini Umashankar • © 2026 All rights reserved.</i>


