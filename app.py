"""
app.py
--------
QA Copilot - AI Agent Suite for Testers
Main Streamlit application.

This app provides a tabbed interface where a tester/QA engineer
can use 5 AI agents:
  1. Orchestrator Agent -> one bug report in, full triage+tests+evidence out
  2. Requirement Agent  -> turns a feature requirement into test cases
  3. Bug Analysis Agent -> triages a bug report (severity, priority, root cause)
  4. Evidence Agent     -> tells the tester what evidence to attach to a ticket
  5. Test Generator     -> screenshot + DOM + test cases -> Playwright POM code

SESSION MEMORY:
Outputs from one agent are stored in st.session_state so other tabs can
reuse them automatically (e.g. Bug Agent's output feeds into Evidence
Agent's input field) instead of the tester retyping things.

EXPORT:
Each tab offers a "Download Ticket" button that exports a clean Markdown
bug-ticket document combining whatever sections are available. The Test
Generator tab instead exports the generated code files (individually and
as a .zip).

Run locally with:  streamlit run app.py
"""

import streamlit as st
from agents.requirement_agent import run_requirement_agent
from agents.bug_analysis_agent import run_bug_analysis_agent
from agents.evidence_agent import run_evidence_agent, run_screenshot_analysis
from agents.orchestrator_agent import run_orchestrator_agent
from agents.test_generator_agent import (
    run_test_generation_agent,
    run_add_requirements_agent,
)
from utils.export_utils import build_bug_ticket_markdown, build_filename
from utils.gemini_client import (
    DailyQuotaExceededError,
    NoApiKeyConfiguredError,
    SESSION_KEY_NAME,
    get_user_session_key,
    set_user_session_key,
    clear_user_session_key,
)

import io
import zipfile

# ---------- PAGE CONFIG ----------
st.set_page_config(
    page_title="QA Copilot - AI Agent Suite",
    page_icon="🐞",
    layout="wide",
)

# ---------- SESSION STATE INIT ----------
# These hold the latest bug description + each agent's latest output,
# so tabs can share context instead of the tester retyping everything.
defaults = {
    "shared_bug_text": "",
    "last_triage": "",
    "last_regression_tests": "",
    "last_evidence": "",
    "tg_dom_text": "",
    "tg_result": None,
    "tg_view": "generator",          # "generator" | "viewing_project" | "add_requirements_input"
    "tg_saved_projects": {},         # {project_name: {"files":..., "test_cases":..., "language":..., "model":...}}
    "tg_active_project": None,
    "tg_uploader_version": 0,        # bump to force-reset file_uploader widgets on "New Project"
    "tg_show_save_dialog": False,
    "tg_ar_dom_text": "",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

if SESSION_KEY_NAME not in st.session_state:
    st.session_state[SESSION_KEY_NAME] = ""

# ---------- SIDEBAR: BRING YOUR OWN API KEY ----------
# Each visitor uses their OWN free Gemini API key, entered here. It lives
# only in this browser tab's session memory — never sent to the developer,
# never written to disk, never logged, and gone the moment the tab is
# closed or refreshed. This lets unlimited people use the app for free,
# since everyone's usage counts against their own personal daily quota
# instead of one shared key getting exhausted immediately.
#
# All 5 agents (including the Test Generator) share this same key — there
# is no separate key field in the Test Generator tab.
with st.sidebar:
    st.markdown("### YOUR GEMINI API KEY")

    current_key = get_user_session_key()

    if current_key:
        masked = current_key[:4] + "•" * 8 + current_key[-4:] if len(current_key) > 8 else "••••••••"
        st.success(f"Key active for this session: `{masked}`")
        if st.button("Remove key / use a different one"):
            clear_user_session_key()
            st.rerun()
    else:
        key_input = st.text_input(
            "Gemini API Key",
            type="password",
            placeholder="Paste your key here..",
            key="api_key_text_input",
        )
        if st.button("Save key for this session", type="primary"):
            if key_input.strip():
                set_user_session_key(key_input.strip())
                st.rerun()
            else:
                st.error("Please paste a key first.")

        with st.expander(" I don't have a key — how do I get one ❓"):
            st.markdown(
                """
                1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)**
                   (sign in with your Google account)
                2. Click **"Get API key"** from sidebar
                3. Copy the key it gives you
                4. Paste it into the box above and click **"Save key for this session"**
                """
            )
    st.subheader("Privacy")
    st.caption(
        "Your API key stays only in this browser session. It is never stored or shared, and is removed when you refresh or close the page. "

    )

    st.divider()

# ---------- HEADER ----------
st.title("🐞 QA COPILOT")
st.caption("An AI agent suite for testers that turns a single bug report into full triage, regression test cases, and an evidence checklist, automatically — plus a Playwright POM test code generator.")

st.markdown(
    """
    QA Copilot uses five AI agents to speed up everyday testing work:
    - **Orchestrator Agent** — paste one bug report, get full triage + regression tests + evidence checklist automatically
    - **Requirement Agent** — turns a feature requirement into ready-to-use test cases
    - **Bug Analysis Agent** — triages a bug report into severity, priority, and root cause
    - **Evidence Agent** — tells you exactly what evidence to attach to a bug ticket
    - **Test Generator** — turns a screenshot + DOM + test cases into professional Playwright POM code and handles additional requirements. 
    """
)

st.divider()

# ---------- GATE: REQUIRE A KEY BEFORE SHOWING THE AGENTS ----------
# Checks whether ANY usable key exists (the visitor's own session key, or
# a developer fallback key from .env/Secrets for local testing). If
# neither is present, we stop here with a clear call-to-action instead of
# letting every individual tab fail with a less helpful error.
from utils.gemini_client import get_active_keys

try:
    get_active_keys()
    key_available = True
except NoApiKeyConfiguredError:
    key_available = False

if not key_available:
    st.info(
        "To get started, paste your free Gemini API key in the sidebar. "
        "It only takes a minute."
    )
    st.stop()

# ---------- TABS FOR THE 5 AGENTS ----------
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "🧭 ORCHESTRATOR",
    "📝 REQUIREMENT AGENT",
    "🐞 BUG ANALYSIS AGENT",
    "📂 EVIDENCE AGENT",
    "🎭 TEST GENERATOR",
])

# ===================== AGENT 0: ORCHESTRATOR =====================
with tab0:
    st.subheader("Orchestrator Agent")
    st.write(
        "Paste one bug report. This agent automatically runs the Bug Analysis Agent, "
        "the Requirement Agent (to generate regression test cases), and the Evidence Agent — "
        "then combines all three into one report."
    )

    orchestrator_input = st.text_area(
        "Bug or issue description",
        placeholder="e.g. Checkout page displays a blank screen after clicking Pay Now.",
        height=120,
        key="orchestrator_input",
    )

    if st.button("Run Full QA Workflow", type="primary", key="btn_orchestrator"):
        if not orchestrator_input.strip():
            st.warning("Please enter a bug description first.")
        else:
            with st.spinner("Running Bug Analysis → Requirement → Evidence agents..."):
                try:
                    result = run_orchestrator_agent(orchestrator_input)

                    if "error" in result:
                        st.warning(result["error"])
                    else:
                        # Save to session memory so other tabs can reuse it
                        st.session_state["shared_bug_text"] = orchestrator_input
                        st.session_state["last_triage"] = result["triage"]
                        st.session_state["last_regression_tests"] = result["regression_tests"]
                        st.session_state["last_evidence"] = result["evidence"]

                        st.markdown("## TRIAGE")
                        st.markdown(result["triage"])

                        st.markdown("## UNDERLYING REQUIREMENT IDENTIFIED")
                        st.info(result["requirement_used"])

                        st.markdown("## SUGGESTED REGRESSION TEST CASES")
                        st.markdown(result["regression_tests"])

                        st.markdown("## EVIDENCE CHECKLIST")
                        st.markdown(result["evidence"])

                        # Build the combined downloadable ticket
                        ticket_md = build_bug_ticket_markdown(
                            bug_description=orchestrator_input,
                            triage_section=result["triage"],
                            regression_tests_section=result["regression_tests"],
                            evidence_section=result["evidence"],
                        )
                        st.download_button(
                            label="⬇️ Download Full Ticket (Markdown)",
                            data=ticket_md,
                            file_name=build_filename("qa_copilot_full_ticket"),
                            mime="text/markdown",
                            key="download_orchestrator",
                        )
                except DailyQuotaExceededError as e:
                    st.warning(f"⏳ {e}")
                except Exception as e:
                    st.error(f"Something went wrong : {e}")

# ===================== AGENT 1: REQUIREMENT AGENT =====================
with tab1:
    st.subheader("Requirement Agent")
    st.write("Paste a feature requirement. The agent will generate positive, negative, and edge-case test cases.")

    # "Use shared context" button — lets the tester pull in the bug text
    # remembered from the Orchestrator/Bug/Evidence tabs, without forcing
    # it on them automatically. Clicking it fills the text area below.
    if st.session_state["shared_bug_text"]:
        if st.button("📋 Use shared context from other tabs", key="use_shared_requirement"):
            st.session_state["requirement_input"] = st.session_state["shared_bug_text"]

    requirement_input = st.text_area(
        "Feature requirement",
        placeholder="e.g. User login page with username and password.",
        height=120,
        key="requirement_input",
    )

    st.caption(
        "💡 Tip: a feature requirement works best here (e.g. \"User login page with "
        "username and password\"). If you pull in a bug description via shared context, "
        "the agent will still generate test cases — but for full bug-to-test-case "
        "conversion, the **Orchestrator** tab does this automatically."
    )

    if st.button("Generate Test Cases", type="primary", key="btn_requirement"):
        if not requirement_input.strip():
            st.warning("Please enter a requirement first.")
        else:
            with st.spinner("Requirement Agent is analyzing the requirement..."):
                try:
                    result = run_requirement_agent(requirement_input)
                    st.markdown(result)

                    st.download_button(
                        label="⬇️ Download Test Cases (Markdown)",
                        data=f"# Test Cases\n\n**Requirement:** {requirement_input}\n\n{result}",
                        file_name=build_filename("qa_copilot_test_cases"),
                        mime="text/markdown",
                        key="download_requirement",
                    )
                except DailyQuotaExceededError as e:
                    st.warning(f"⏳ {e}")
                except Exception as e:
                    st.error(f"Something went wrong calling the agent: {e}")

# ===================== AGENT 2: BUG ANALYSIS AGENT =====================
with tab2:
    st.subheader("Bug Analysis Agent")
    st.write("Paste a bug description. The agent will return severity, priority, root causes, and reproduction steps.")

    if st.session_state["shared_bug_text"]:
        if st.button("📋 Use shared context from other tabs", key="use_shared_bug"):
            st.session_state["bug_input"] = st.session_state["shared_bug_text"]

    bug_input = st.text_area(
        "Bug description",
        placeholder="e.g. Login button not responding after entering credentials.",
        height=120,
        key="bug_input",
    )

    st.caption(
        "💡 Tip: a Bug analysis works best here (e.g. \"User login page with "
        "username and password\"). If you pull in a bug description via shared context, "
        "the agent will still generate test cases — but for full bug-to-test-case "
        "conversion, the **Orchestrator** tab does this automatically."
    )

    if st.button("Analyze Bug", type="primary", key="btn_bug"):
        if not bug_input.strip():
            st.warning("Please enter a bug description first.")
        else:
            with st.spinner("Bug Analysis Agent is triaging the bug..."):
                try:
                    result = run_bug_analysis_agent(bug_input)
                    st.markdown(result)

                    # Save to session memory for reuse in other tabs
                    st.session_state["shared_bug_text"] = bug_input
                    st.session_state["last_triage"] = result

                    st.download_button(
                        label="⬇️ Download Triage (Markdown)",
                        data=build_bug_ticket_markdown(
                            bug_description=bug_input,
                            triage_section=result,
                        ),
                        file_name=build_filename("qa_copilot_triage"),
                        mime="text/markdown",
                        key="download_bug",
                    )
                except DailyQuotaExceededError as e:
                    st.warning(f"⏳ {e}")
                except Exception as e:
                    st.error(f"Something went wrong calling the agent: {e}")

# ===================== AGENT 3: EVIDENCE AGENT =====================
with tab3:
    st.subheader("Evidence Agent")
    st.write("Paste an issue description. The agent will tell you exactly what evidence to collect for the ticket.")

    if st.session_state["shared_bug_text"]:
        if st.button("📋 Use shared context from other tabs", key="use_shared_evidence"):
            st.session_state["evidence_input"] = st.session_state["shared_bug_text"]

    evidence_input = st.text_area(
        "Issue description",
        placeholder="e.g. Checkout page crashes when applying a discount code on Safari.",
        height=120,
        key="evidence_input",
    )
    st.caption(
        "💡 Tip: an Evidence agent works best here (e.g. \"User login page with "
        "username and password\"). If you pull in a bug description via shared context, "
        "the agent will still generate test cases — but for full bug-to-test-case "
        "conversion, the **Orchestrator** tab does this automatically."
    )

    if st.button("Suggest Evidence", type="primary", key="btn_evidence"):
        if not evidence_input.strip():
            st.warning("Please enter an issue description first.")
        else:
            with st.spinner("Evidence Agent is preparing the checklist..."):
                try:
                    result = run_evidence_agent(evidence_input)
                    st.markdown(result)

                    # Save to session memory for reuse in other tabs
                    st.session_state["shared_bug_text"] = evidence_input
                    st.session_state["last_evidence"] = result

                    st.download_button(
                        label="⬇️ Download Evidence Checklist (Markdown)",
                        data=build_bug_ticket_markdown(
                            bug_description=evidence_input,
                            evidence_section=result,
                        ),
                        file_name=build_filename("qa_copilot_evidence"),
                        mime="text/markdown",
                        key="download_evidence",
                    )
                except DailyQuotaExceededError as e:
                    st.warning(f"⏳ {e}")
                except Exception as e:
                    st.error(f"Something went wrong : {e}")

    st.divider()

    # ----- Multimodal screenshot analysis -----
    st.markdown("### 📸 Or upload a screenshot for direct analysis")
    st.write(
        "Already have a screenshot of the bug? Upload it here and the Evidence Agent "
        "will look at it directly and point out visible errors — instead of just "
        "telling you to go take one."
    )

    uploaded_screenshot = st.file_uploader(
        "Upload a screenshot (PNG or JPG)",
        type=["png", "jpg", "jpeg"],
        key="screenshot_uploader",
    )

    if uploaded_screenshot is not None:
        st.image(uploaded_screenshot, caption="Uploaded screenshot", width=500)

    if st.button("Analyze Screenshot", type="primary", key="btn_screenshot"):
        if uploaded_screenshot is None:
            st.warning("Please upload a screenshot first.")
        else:
            with st.spinner("Evidence Agent is examining the screenshot..."):
                try:
                    image_bytes = uploaded_screenshot.getvalue()
                    mime_type = uploaded_screenshot.type or "image/png"

                    analysis_result = run_screenshot_analysis(
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        issue_description=evidence_input,
                    )
                    st.markdown(analysis_result)

                    st.download_button(
                        label="⬇️ Download Screenshot Analysis (Markdown)",
                        data=build_bug_ticket_markdown(
                            bug_description=evidence_input or "(no text description provided)",
                            evidence_section=analysis_result,
                        ),
                        file_name=build_filename("qa_copilot_screenshot_analysis"),
                        mime="text/markdown",
                        key="download_screenshot_analysis",
                    )
                except DailyQuotaExceededError as e:
                    st.warning(f"⏳ {e}")
                except Exception as e:
                    st.error(f"Something went wrong analyzing the screenshot: {e}")

# ===================== AGENT 4: TEST GENERATOR =====================

def _tg_zip_bytes(files: list) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f["path"], f["content"])
    return zip_buffer.getvalue()


def _tg_render_files_and_cases(files: list, test_cases: list, key_prefix: str):
    """Shared renderer for the code + test cases tabs. Reused across all 3 views."""
    tg_tab_code, tg_tab_cases = st.tabs(["📄 Code", "🧪 Test Cases"])

    with tg_tab_code:
        if not files:
            st.warning("No files yet.")
        for f in files:
            path = f.get("path", "file")
            content = f.get("content", "")
            lang_hint = "typescript" if path.endswith(".ts") else "javascript"
            with st.expander(f"`{path}`", expanded=False):
                st.code(content, language=lang_hint)
                st.download_button(
                    "Download this file",
                    data=content,
                    file_name=path.split("/")[-1],
                    key=f"{key_prefix}_dl_{path}",
                )

    with tg_tab_cases:
        if not test_cases:
            st.warning("No test cases yet.")
        else:
            priority_color = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}
            for tc in test_cases:
                badge = priority_color.get(tc.get("priority", "Medium"), "⚪")
                data_tag = " · 📊 data-driven" if tc.get("data_driven") else ""
                st.markdown(
                    f"**{tc.get('id', '')} — {tc.get('title', '')}** "
                    f"{badge} {tc.get('priority', '')}{data_tag}"
                )
                st.caption(tc.get("description", ""))
                st.markdown("")


def _tg_new_project():
    st.session_state["tg_result"] = None
    st.session_state["tg_dom_text"] = ""
    st.session_state["tg_ar_dom_text"] = ""
    st.session_state["tg_active_project"] = None
    st.session_state["tg_view"] = "generator"
    st.session_state["tg_show_save_dialog"] = False
    st.session_state["tg_uploader_version"] += 1  # forces file_uploader widgets to reset
    st.rerun()


def _tg_phase2_buttons(files: list, test_cases: list, language: str, model: str, key_prefix: str):
    """Download Project / Save Project / New Project — shown after any generation."""
    col_dl, col_save, col_new = st.columns(3)

    with col_dl:
        st.download_button(
            "⬇️ Download Project",
            data=_tg_zip_bytes(files),
            file_name="playwright-pom-suite.zip",
            mime="application/zip",
            key=f"{key_prefix}_download_project",
            use_container_width=True,
        )

    with col_save:
        if st.button("💾 Save Project", key=f"{key_prefix}_save_project", use_container_width=True):
            st.session_state["tg_show_save_dialog"] = True

    with col_new:
        if st.button("🆕 New Project", key=f"{key_prefix}_new_project", use_container_width=True):
            _tg_new_project()

    if st.session_state.get("tg_show_save_dialog"):
        default_name = st.session_state.get("tg_active_project") or ""
        save_name = st.text_input(
            "Project name",
            value=default_name,
            key=f"{key_prefix}_save_name_input",
            placeholder="e.g. Login Page Suite",
        )
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("✅ Confirm Save", key=f"{key_prefix}_confirm_save"):
                name = save_name.strip()
                if not name:
                    st.error("Please enter a project name.")
                else:
                    st.session_state["tg_saved_projects"][name] = {
                        "files": files,
                        "test_cases": test_cases,
                        "language": language,
                        "model": model,
                    }
                    st.session_state["tg_active_project"] = name
                    st.session_state["tg_view"] = "viewing_project"
                    st.session_state["tg_show_save_dialog"] = False
                    st.success(f"Saved as '{name}'.")
                    st.rerun()
        with col_cancel:
            if st.button("Cancel", key=f"{key_prefix}_cancel_save"):
                st.session_state["tg_show_save_dialog"] = False
                st.rerun()


with tab4:
    st.subheader("Test Generator Agent (Playwright)")
    st.write(
        "Upload a screenshot, provide the DOM, and describe your test cases. "
        "This agent generates professional Playwright Page Object Model (POM) "
        "test code — JavaScript or TypeScript, ES modules — using the same "
        "Gemini key from the sidebar."
    )

    tg_view = st.session_state["tg_view"]
    uv = st.session_state["tg_uploader_version"]  # versioned widget keys for reset-on-New-Project

    # -----------------------------------------------------------------
    # VIEW 1: fresh generator (create from scratch)
    # -----------------------------------------------------------------
    if tg_view == "generator":
        col_lang, col_model = st.columns(2)
        with col_lang:
            tg_language = st.selectbox(
                "Target language",
                options=["JavaScript", "TypeScript"],
                index=0,
                key="tg_language",
            )
        with col_model:
            tg_model = st.selectbox(
                "Gemini model",
                options=["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro"],
                index=0,
                key="tg_model",
                help="Gemini 1.5 and 2.0 models were shut down in 2026 — use a "
                     "current model from this list.",
            )

        st.markdown("**1️⃣ Upload Screenshot**")
        tg_screenshot = st.file_uploader(
            "Screenshot of the screen/page to test",
            type=["png", "jpg", "jpeg", "webp"],
            key=f"tg_screenshot_uploader_{uv}",
        )
        if tg_screenshot:
            st.image(tg_screenshot, caption="Uploaded screenshot", width=420)

        st.markdown("**2️⃣ Provide the DOM Structure**")
        tg_dom_file = st.file_uploader(
            "Optional: upload DOM/HTML file (.html, .txt)",
            type=["html", "htm", "txt"],
            key=f"tg_dom_uploader_{uv}",
        )
        if tg_dom_file is not None:
            st.session_state["tg_dom_text"] = tg_dom_file.read().decode("utf-8", errors="ignore")

        tg_dom_text = st.text_area(
            "Paste the page DOM/HTML."
            "( **Steps to get DOM**: Open page → Inspect → Select <html> → Right-click → Copy → Copy outerHTML)",

            value=st.session_state["tg_dom_text"],
            height=200,
            key=f"tg_dom_text_area_{uv}",
            placeholder='<button id="login-btn" data-testid="login-submit">Login</button>\n'
                        '<input name="email" type="email" />\n...',
        )
        st.session_state["tg_dom_text"] = tg_dom_text

        st.markdown("**3️⃣ Describe the Test Cases**")
        tg_test_cases_input = st.text_area(
            "What do you want to test? (one per line)",
            height=160,
            key=f"tg_test_cases_input_{uv}",
            placeholder=(
                "1. Verify user can log in with valid email and password\n"
                "2. Verify error message shows for invalid credentials\n"
                "3. Verify 'Forgot password' link navigates to reset page"
            ),
        )

        if st.button(" Generate Playwright POM Code", type="primary", key="btn_test_generator"):
            if not tg_screenshot:
                st.warning("Please upload a screenshot first.")
            else:
                with st.spinner("Analyzing screenshot, DOM, and test cases..."):
                    try:
                        parsed = run_test_generation_agent(
                            language=tg_language,
                            dom_text=tg_dom_text,
                            test_cases_input=tg_test_cases_input,
                            screenshot_bytes=tg_screenshot.getvalue(),
                            screenshot_mime=tg_screenshot.type or "image/png",
                            model_name=tg_model,
                        )
                        st.session_state["tg_result"] = parsed
                    except DailyQuotaExceededError as e:
                        st.warning(f"⏳ {e}")
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Generation failed: {e}")

        tg_result = st.session_state["tg_result"]
        if tg_result:
            st.markdown("---")
            st.markdown("### ✅ Generated Output")

            if tg_result.get("notes"):
                st.info(tg_result["notes"])

            requested_count = len([l for l in tg_test_cases_input.splitlines() if l.strip()])
            generated_count = len(tg_result.get("test_cases", []))
            if requested_count and generated_count and generated_count < requested_count:
                st.warning(
                    f"You entered {requested_count} test case line(s) but only "
                    f"{generated_count} were generated. Some may have been merged "
                    f"or skipped — click Generate again, or try `gemini-2.5-pro` "
                    f"for more reliable coverage on longer lists."
                )

            tg_files = tg_result.get("files", [])
            tg_test_cases = tg_result.get("test_cases", [])
            _tg_render_files_and_cases(tg_files, tg_test_cases, key_prefix="gen")

            st.markdown("---")
            _tg_phase2_buttons(tg_files, tg_test_cases, tg_language, tg_model, key_prefix="gen")

    # -----------------------------------------------------------------
    # VIEW 2: viewing a saved project (with Add Requirements / Cancel)
    # -----------------------------------------------------------------
    elif tg_view == "viewing_project":
        active_name = st.session_state["tg_active_project"]
        project = st.session_state["tg_saved_projects"].get(active_name)

        if not project:
            st.warning("That project no longer exists.")
            if st.button("← Back to Test Generator"):
                st.session_state["tg_view"] = "generator"
                st.rerun()
        else:
            st.markdown(f"### 📁 {active_name}")
            st.caption(f"Language: {project['language']} · Model: {project['model']}")

            _tg_render_files_and_cases(
                project["files"], project["test_cases"], key_prefix="proj"
            )

            st.markdown("---")
            col_add, col_cancel = st.columns(2)
            with col_add:
                if st.button("➕ Add Requirements", type="primary", key="btn_add_requirements", use_container_width=True):
                    st.session_state["tg_view"] = "add_requirements_input"
                    st.session_state["tg_uploader_version"] += 1
                    st.rerun()
            with col_cancel:
                if st.button("❌ Cancel", key="btn_cancel_project_view", use_container_width=True):
                    st.session_state["tg_view"] = "generator"
                    st.session_state["tg_active_project"] = None
                    st.rerun()

            st.markdown("---")
            _tg_phase2_buttons(
                project["files"], project["test_cases"],
                project["language"], project["model"],
                key_prefix="proj",
            )

    # -----------------------------------------------------------------
    # VIEW 3: adding requirements to the active project
    # -----------------------------------------------------------------
    elif tg_view == "add_requirements_input":
        active_name = st.session_state["tg_active_project"]
        project = st.session_state["tg_saved_projects"].get(active_name)

        if not project:
            st.warning("That project no longer exists.")
            if st.button("← Back to Test Generator"):
                st.session_state["tg_view"] = "generator"
                st.rerun()
        else:
            st.markdown(f"### ➕ Add Requirements — {active_name}")
            st.caption(
                "This will generate only the new/updated code needed for the "
                "additional requirement — the rest of the project is untouched."
            )

            uv2 = st.session_state["tg_uploader_version"]

            st.markdown("**1️⃣ Upload the updated screenshot**")
            ar_screenshot = st.file_uploader(
                "Screenshot showing the new/changed UI",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"tg_ar_screenshot_uploader_{uv2}",
            )
            if ar_screenshot:
                st.image(ar_screenshot, caption="Uploaded screenshot", width=420)

            st.markdown("**2️⃣ Paste the updated DOM**")
            ar_dom_text = st.text_area(
                "Updated DOM / HTML for the new elements",
                height=180,
                key=f"tg_ar_dom_text_area_{uv2}",
                placeholder='<input id="otp-code" data-testid="otp-input" />\n...',
            )

            st.markdown("**3️⃣ Tell us about the change**")
            ar_requirements_desc = st.text_input(
                "May I know the additional requirements added?",
                key=f"tg_ar_requirements_desc_{uv2}",
                placeholder="e.g. Added OTP verification step after login",
            )

            ar_test_cases_input = st.text_area(
                "Additional test cases to cover (positive / negative / edge cases, one per line)",
                height=140,
                key=f"tg_ar_test_cases_input_{uv2}",
                placeholder=(
                    "1. Verify user can submit a valid OTP and proceed\n"
                    "2. Verify error message shows for an invalid OTP\n"
                    "3. Verify OTP field enforces exactly 6 digits"
                ),
            )

            col_generate, col_cancel_ar = st.columns([2, 1])
            with col_generate:
                generate_ar = st.button(
                    "🚀Generate Additional Code", type="primary", key="btn_generate_ar",
                    use_container_width=True,
                )
            with col_cancel_ar:
                if st.button("❌ Cancel", key="btn_cancel_ar", use_container_width=True):
                    st.session_state["tg_view"] = "viewing_project"
                    st.rerun()

            if generate_ar:
                if not ar_screenshot:
                    st.warning("Please upload the updated screenshot first.")
                else:
                    with st.spinner("Generating additional code for the new requirement..."):
                        try:
                            addition = run_add_requirements_agent(
                                language=project["language"],
                                previous_files=project["files"],
                                previous_test_cases=project["test_cases"],
                                new_dom_text=ar_dom_text,
                                requirements_description=ar_requirements_desc,
                                additional_test_cases_input=ar_test_cases_input,
                                screenshot_bytes=ar_screenshot.getvalue(),
                                screenshot_mime=ar_screenshot.type or "image/png",
                                model_name=project["model"],
                            )

                            # Merge: replace files by path, else append; append new test cases.
                            merged_files = {f["path"]: f for f in project["files"]}
                            for f in addition.get("files", []):
                                merged_files[f["path"]] = f
                            project["files"] = list(merged_files.values())
                            project["test_cases"] = project["test_cases"] + addition.get("test_cases", [])

                            st.session_state["tg_saved_projects"][active_name] = project
                            st.session_state["tg_view"] = "viewing_project"
                            if addition.get("notes"):
                                st.session_state["tg_last_ar_notes"] = addition["notes"]
                            st.success("Additional requirement added to the project.")
                            st.rerun()
                        except DailyQuotaExceededError as e:
                            st.warning(f"⏳ {e}")
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Generation failed: {e}")

# ---------- SIDEBAR: SAVED TEST GENERATOR PROJECTS ----------
with st.sidebar:
    st.markdown("### SAVED TEST PROJECTS")
    saved_projects = st.session_state["tg_saved_projects"]
    if not saved_projects:
        st.caption("No saved projects yet. Generate code in the Test Generator tab, then click Save Project.")
    else:
        for name in list(saved_projects.keys()):
            col_open, col_del = st.columns([4, 1])
            with col_open:
                if st.button(f"📂 {name}", key=f"open_project_{name}", use_container_width=True):
                    st.session_state["tg_active_project"] = name
                    st.session_state["tg_view"] = "viewing_project"
                    st.rerun()
            with col_del:
                if st.button("🗑️", key=f"delete_project_{name}"):
                    del st.session_state["tg_saved_projects"][name]
                    if st.session_state["tg_active_project"] == name:
                        st.session_state["tg_active_project"] = None
                        st.session_state["tg_view"] = "generator"
                    st.rerun()

    st.divider()

# ---------- SIDEBAR: SESSION MEMORY STATUS ----------
with st.sidebar:
    st.markdown("### SESSION MEMORY")
    st.caption(
        "QA Copilot remembers your latest Orchestrator bug description and agent outputs for the current session, allowing all agents to reuse the shared context."
    )
    if st.session_state["shared_bug_text"]:
        st.success("✅ Active bug context shared across tabs")
        with st.expander("View shared bug text"):
            st.write(st.session_state["shared_bug_text"])
    else:
        st.info("No shared context yet. Run any agent to populate it.")

    if st.button("🗑️ Clear session memory"):
        for key in defaults:
            st.session_state[key] = defaults[key]
        st.rerun()

# ---------- FOOTER ----------
st.divider()
st.caption("QA Copilot • Designed and Developed by Varshini Umashankar • © 2026 All rights reserved.")