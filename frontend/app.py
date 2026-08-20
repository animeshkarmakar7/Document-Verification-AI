import html
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="LegalDoc AI — Contract Intelligence",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Global Custom CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background: #0F1117; color: #E2E8F0; }
section[data-testid="stSidebar"] { background: #161B2E; border-right: 1px solid #1E2740; }

.sidebar-brand {
    font-size: 1.4rem; font-weight: 800;
    background: linear-gradient(90deg, #6366F1, #8B5CF6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.sidebar-sub { font-size: 0.78rem; color: #64748B; margin-bottom: 1.5rem; }

.hero {
    background: linear-gradient(135deg, #1E1B4B 0%, #1E293B 50%, #0F172A 100%);
    border: 1px solid #312E81;
    border-radius: 16px;
    padding: 1.8rem 2.2rem;
    margin-bottom: 1.8rem;
}
.hero-title {
    font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px;
    background: linear-gradient(90deg, #A5B4FC, #C4B5FD, #818CF8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.hero-sub { font-size: 0.92rem; color: #94A3B8; margin-top: 0.3rem; }
.hero-pill {
    display: inline-block; background: rgba(99,102,241,0.15);
    border: 1px solid rgba(99,102,241,0.3); border-radius: 20px;
    padding: 0.2rem 0.7rem; font-size: 0.75rem; color: #A5B4FC;
    margin-right: 0.4rem; margin-top: 0.6rem;
}

.summary-card {
    background: #1E293B; border: 1px solid #334155; border-radius: 12px;
    padding: 1.5rem; margin-bottom: 1.5rem;
}
.summary-title { font-size: 1.3rem; font-weight: 700; color: #F8FAFC; margin-bottom: 0.4rem; }
.summary-type { font-size: 0.8rem; color: #818CF8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 1rem; }
.summary-exec { background: rgba(99,102,241,0.08); border-left: 4px solid #6366F1; padding: 1rem 1.2rem; border-radius: 6px; font-size: 0.92rem; color: #CBD5E1; line-height: 1.6; margin-bottom: 1.2rem; }

.section-head { font-size: 1.1rem; font-weight: 700; color: #E2E8F0; border-left: 4px solid #6366F1; padding-left: 0.75rem; margin: 1.5rem 0 1rem 0; }

.verbatim-text {
    background: #0F172A; border-left: 3px solid #6366F1; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}

.verbatim-text-HIGH {
    background: #0F172A; border-left: 4px solid #EF4444; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}
.verbatim-text-MEDIUM {
    background: #0F172A; border-left: 4px solid #F59E0B; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}
.verbatim-text-LOW {
    background: #0F172A; border-left: 4px solid #10B981; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}

.badge-HIGH { background: rgba(239,68,68,0.2); border: 1px solid #EF4444; color: #FCA5A5; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; }
.badge-MEDIUM { background: rgba(245,158,11,0.2); border: 1px solid #F59E0B; color: #FCD34D; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; }
.badge-LOW { background: rgba(16,185,129,0.2); border: 1px solid #10B981; color: #6EE7B7; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.72rem; font-weight: 700; }

.impact-box { background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.6rem; font-size: 0.85rem; color: #FCA5A5; }
.mitigation-box { background: rgba(99,102,241,0.08); border: 1px solid rgba(99,102,241,0.2); border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.6rem; font-size: 0.85rem; color: #C7D2FE; }

.citation-card { background: rgba(30,41,59,0.7); border: 1px solid #334155; border-radius: 8px; padding: 0.75rem 1rem; margin-top: 0.5rem; font-size: 0.82rem; color: #A5B4FC; }

.empty-state { text-align: center; padding: 3rem 1rem; color: #64748B; font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)

# ─── Session State Initialization ─────────────────────────────────────────────
if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "document_info" not in st.session_state:
    st.session_state.document_info = None
if "chat_display" not in st.session_state:
    st.session_state.chat_display = []


# ─── API Helper Functions ─────────────────────────────────────────────────────
def post(path, json_payload=None, files=None):
    res = requests.post(f"{API_BASE_URL}/{path}", json=json_payload, files=files, timeout=180)
    res.raise_for_status()
    return res.json()


def get(path):
    res = requests.get(f"{API_BASE_URL}/{path}", timeout=60)
    res.raise_for_status()
    return res.json()


def run_step(label, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        st.write(f"✅ {label}")
        return result
    except Exception as e:
        err = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json()
                err = body.get("detail") or body.get("error", {}).get("message", str(e))
            except Exception:
                err = str(e)
        else:
            err = str(e)
        st.warning(f"⚠️ {label} — skipped ({err})")
        return None


# ─── Sidebar Controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sidebar-brand'>⚖️ LegalDoc AI</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-sub'>Contract Intelligence Platform</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**📂 Upload Legal Document**")
    uploaded_file = st.file_uploader(
        "Drag & drop or browse",
        type=["pdf", "png", "jpg", "jpeg"],
        label_visibility="collapsed",
        help="Upload any PDF or scanned image of a legal contract, lease, or agreement.",
    )

    if uploaded_file and st.button("🚀 Analyze Document", type="primary", use_container_width=True):
        with st.status("Analyzing Legal Document...", expanded=True) as status_box:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

            doc_data = run_step("Uploading document", post, "documents/upload", files=files)
            if doc_data is None:
                status_box.update(label="Upload failed.", state="error", expanded=True)
                st.stop()

            doc_id = doc_data["document_id"]
            st.session_state.document_id = doc_id
            st.session_state.document_info = doc_data
            st.session_state.chat_display = []

            run_step("OCR Text Extraction", post, f"documents/{doc_id}/ocr")
            run_step("Clause Segmentation", post, f"documents/{doc_id}/clauses/segment")
            run_step("Gemini Classification", post, f"documents/{doc_id}/classify")
            run_step("Risk Scoring & Evaluation", post, f"documents/{doc_id}/score-risk")
            run_step("Plain-English Explanation & Summary", post, f"documents/{doc_id}/explain")

            status_box.update(label="✅ Analysis Complete!", state="complete", expanded=False)
            st.rerun()

    if st.session_state.document_id:
        st.markdown("---")
        st.markdown("**🗂️ Active Document**")
        info = st.session_state.document_info or {}
        filename = info.get("original_filename", "Document")
        st.markdown(f"📄 `{filename}`")
        st.code(st.session_state.document_id[:12] + "...", language="text")
        if st.button("🗑️ Clear Active Session", use_container_width=True):
            st.session_state.document_id = None
            st.session_state.document_info = None
            st.session_state.chat_display = []
            st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.73rem; color:#475569; line-height:1.5;'>"
        "ℹ️ <strong>Informational Use Only.</strong><br>"
        "This tool provides automated contract analysis and does not constitute formal legal advice."
        "</div>",
        unsafe_allow_html=True,
    )


# ─── Hero Header ──────────────────────────────────────────────────────────────
st.markdown("""
<div class='hero'>
  <div class='hero-title'>Legal Document Demystifier</div>
  <div class='hero-sub'>Executive Summaries · ChromaDB Hybrid Vector Search · Risk Impact Analysis · Grounded RAG</div>
  <span class='hero-pill'>📄 OCR Extraction</span>
  <span class='hero-pill'>⚡ LangChain Chunking</span>
  <span class='hero-pill'>🧠 ChromaDB Vector Store</span>
  <span class='hero-pill'>⚠️ Risk Impact Rubric</span>
  <span class='hero-pill'>💬 Cited RAG Chat</span>
</div>
""", unsafe_allow_html=True)

# ─── Empty Document State Guard ────────────────────────────────────────────────
if not st.session_state.document_id:
    st.markdown("""
    <div class='empty-state'>
        <div style='font-size: 3rem; margin-bottom: 1rem;'>⚖️</div>
        <div style='font-size: 1.1rem; font-weight: 600; color: #94A3B8; margin-bottom: 0.5rem;'>
            No legal document loaded
        </div>
        <div style='color: #475569;'>
            Upload a PDF contract or scanned agreement in the sidebar to run full AI analysis.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

doc_id = st.session_state.document_id

# ─── Main Content Tabs ────────────────────────────────────────────────────────
tab_summary, tab_risk, tab_chat = st.tabs([
    "📋 Executive Summary & Clauses",
    "🚨 Risk Analysis & Impact",
    "💬 Grounded RAG Chatbot",
])


# ==============================================================================
# TAB 1 — EXECUTIVE SUMMARY & DOCUMENT CLAUSES
# ==============================================================================
with tab_summary:
    st.markdown("<div class='section-head'>📋 Executive Document Summary Report</div>", unsafe_allow_html=True)

    # 1. Fetch Executive Document Summary
    try:
        doc_summary = get(f"documents/{doc_id}/summary")

        st.markdown(f"""
        <div class='summary-card'>
            <div class='summary-title'>📄 {html.escape(doc_summary.get('title', 'Contract Summary'))}</div>
            <div class='summary-type'>Type: {html.escape(doc_summary.get('document_type', 'Legal Agreement'))} &nbsp;·&nbsp; Total Clauses: {doc_summary.get('total_clauses', 0)}</div>
            <div class='summary-exec'>
                <strong>Executive Summary:</strong><br>
                {html.escape(doc_summary.get('executive_summary', 'No summary available.'))}
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("### 📌 Key Points Extracted from PDF")
            key_pts = doc_summary.get("key_points", [])
            if key_pts:
                for pt in key_pts:
                    st.markdown(f"- {pt}")
            else:
                st.caption("No key points generated.")

            st.markdown("### 📅 Important Dates, Fees & Notice Periods")
            dates_fees = doc_summary.get("important_dates_fees", [])
            if dates_fees:
                for df in dates_fees:
                    st.markdown(f"- 💵 {df}")
            else:
                st.caption("No specific fees or dates highlighted.")

        with col_right:
            st.markdown("### ⚖️ Your Obligation Requirements")
            obls = doc_summary.get("user_obligations", [])
            if obls:
                for ob in obls:
                    st.markdown(f"- ⚠️ {ob}")
            else:
                st.caption("Standard legal obligations apply.")

            st.markdown("### 🛡️ Your Rights & Granted Protections")
            rights = doc_summary.get("user_rights", [])
            if rights:
                for rt in rights:
                    st.markdown(f"- ✅ {rt}")
            else:
                st.caption("Standard statutory protections apply.")

    except Exception as e:
        st.warning(f"Executive summary not available yet. Run the pipeline first. ({e})")

    st.divider()

    # 2. Detailed Document Clauses Section
    st.markdown("<div class='section-head'>🔍 Document Clauses — Exact Verbatim Extracted Statements</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Below is every clause extracted from your PDF via OCR, grouped by category with its exact text span and plain summary."
        "</p>",
        unsafe_allow_html=True,
    )

    try:
        clauses_resp = get(f"documents/{doc_id}/clauses?limit=200")
        clauses = clauses_resp.get("items", [])

        class_map = {}
        try:
            class_data = get(f"documents/{doc_id}/classifications")
            for c in class_data.get("classifications", []):
                class_map[c["clause_pk"]] = c.get("category", "OTHER")
        except Exception:
            pass

        expl_map = {}
        try:
            explanations = get(f"documents/{doc_id}/explanations")
            for e in explanations:
                expl_map[e["clause_pk"]] = e
        except Exception:
            pass

        if not clauses:
            st.info("No clauses extracted from this document.")
        else:
            from collections import defaultdict
            groups = defaultdict(list)
            for clause in clauses:
                cat = class_map.get(clause["id"], "OTHER")
                groups[cat].append(clause)

            for cat, cat_clauses in sorted(groups.items()):
                cat_label = cat.replace("_", " ").title()
                with st.expander(f"📂 {cat_label} ({len(cat_clauses)} clause{'s' if len(cat_clauses) > 1 else ''})", expanded=True):
                    for clause in cat_clauses:
                        pk = clause["id"]
                        c_id = clause["clause_id"]
                        raw_text = clause.get("text", "").strip()
                        expl = expl_map.get(pk, {})
                        summary = expl.get("plain_summary", "")
                        span_start = clause.get("source_start", 0)
                        span_end = clause.get("source_end", 0)

                        st.markdown(f"**📍 {html.escape(c_id)}** &nbsp;•&nbsp; <span style='font-size:0.75rem; color:#64748B;'>chars {span_start}–{span_end}</span>", unsafe_allow_html=True)
                        st.markdown(f"<div class='verbatim-text'>{html.escape(raw_text)}</div>", unsafe_allow_html=True)
                        if summary:
                            st.info(f"🤖 **Plain-English Summary:** {summary}")
                        st.caption("---")

    except Exception as e:
        st.warning(f"Could not load clause details. ({e})")


# ==============================================================================
# TAB 2 — RISK ANALYSIS & IMPACT
# ==============================================================================
with tab_risk:
    st.markdown("<div class='section-head'>🚨 Risk Analysis & Impact Assessment</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Each flagged clause shows the <strong>verbatim text from your PDF</strong>, the assigned risk level, why it is risky, "
        "<strong>how the risk affects you</strong>, and actionable mitigations."
        "</p>",
        unsafe_allow_html=True,
    )

    try:
        dashboard = get(f"documents/{doc_id}/risk-dashboard")
        overall_score = dashboard.get("overall_risk_score", 0)
        high_cnt = dashboard.get("high_risk_count", 0)
        med_cnt = dashboard.get("medium_risk_count", 0)
        low_cnt = dashboard.get("low_risk_count", 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Overall Risk Score", f"{overall_score} / 100")
        c2.metric("High Risk Flags", high_cnt)
        c3.metric("Medium Risk Flags", med_cnt)
        c4.metric("Low Risk Flags", low_cnt)

        st.progress(min(overall_score / 100.0, 1.0))
        st.divider()

        # Load clauses for verbatim text matching
        clause_text_map = {}
        try:
            all_c = get(f"documents/{doc_id}/clauses?limit=200").get("items", [])
            for c in all_c:
                clause_text_map[c["clause_id"]] = c.get("text", "").strip()
        except Exception:
            pass

        all_risks = dashboard.get("clauses", [])

        if not all_risks:
            st.success("✅ No contract risks flagged.")
        else:
            filter_levels = st.multiselect(
                "Filter Risk Level",
                options=["HIGH", "MEDIUM", "LOW"],
                default=["HIGH", "MEDIUM", "LOW"],
            )

            order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
            sorted_risks = sorted(all_risks, key=lambda x: order.get(x.get("risk_level", "LOW"), 2))

            for risk in sorted_risks:
                r_level = risk.get("risk_level", "LOW")
                if r_level not in filter_levels:
                    continue

                c_id = risk.get("clause_id", "")
                reason = risk.get("risk_reason", "")
                flag = risk.get("flag_type", "").replace("_", " ")
                mitigation = risk.get("suggested_mitigation", "")
                score = risk.get("risk_score", 0.0)
                verbatim_txt = clause_text_map.get(c_id, "")

                # Derive user impact narrative
                if r_level == "HIGH":
                    impact_text = f"This high-risk clause could impose unilateral legal liability, financial penalties, or restrict your rights without prior notice."
                elif r_level == "MEDIUM":
                    impact_text = f"This medium-risk clause warrants review as it contains strict timelines, conditional fees, or ambiguous wording."
                else:
                    impact_text = f"Low risk term representing standard commercial practices with minimal negative impact."

                with st.container():
                    st.markdown(
                        f"""
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <strong style='font-size:1.05rem;'>📍 {html.escape(c_id)}</strong>
                            <span class='badge-{r_level}'>{r_level} RISK (Score: {int(score*100) if score <= 1.0 else int(score)}%)</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown(f"<div class='verbatim-text-{r_level}'>📄 <strong>Verbatim Text from Document:</strong><br>{html.escape(verbatim_txt if verbatim_txt else 'Text not available.')}</div>", unsafe_allow_html=True)
                    st.markdown(f"**⚠️ Risk Reason:** {html.escape(reason)}")
                    st.markdown(f"<div class='impact-box'>💥 <strong>How This Risk Affects You:</strong> {html.escape(impact_text)}</div>", unsafe_allow_html=True)
                    if mitigation:
                        st.markdown(f"<div class='mitigation-box'>💡 <strong>Suggested Mitigation:</strong> {html.escape(mitigation)}</div>", unsafe_allow_html=True)
                    st.caption(f"Flag Category: {flag}")
                    st.divider()

    except Exception as e:
        st.warning(f"Risk analysis data not yet available. Run the pipeline first. ({e})")


# ==============================================================================
# TAB 3 — GROUNDED RAG CHATBOT
# ==============================================================================
with tab_chat:
    st.markdown("<div class='section-head'>💬 Grounded RAG Legal Assistant</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Ask questions about your contract. Answers are retrieved via <strong>ChromaDB hybrid vector search</strong> "
        "and strictly grounded in the document text with verifiable citations."
        "</p>",
        unsafe_allow_html=True,
    )

    # Load chat history
    if not st.session_state.chat_display:
        try:
            history = get(f"documents/{doc_id}/chat-history")
            st.session_state.chat_display = history.get("messages", [])
        except Exception:
            st.session_state.chat_display = []

    # Display Chat History
    for msg in st.session_state.chat_display:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        citations = msg.get("citations") or []

        with st.chat_message(role):
            st.markdown(content)
            if citations and role == "assistant":
                st.markdown("**📌 Cited Source Clauses:**")
                for cit in citations:
                    if isinstance(cit, dict):
                        q_txt = cit.get("quoted_text", "")
                        st.markdown(
                            f"<div class='citation-card'>"
                            f"<strong>📍 {html.escape(cit.get('clause_id', ''))}</strong> (chars {cit.get('source_span_start', 0)}–{cit.get('source_span_end', 0)})<br>"
                            f"<i>\"{html.escape(q_txt[:200])}{'...' if len(q_txt) > 200 else ''}\"</i>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

    # Prompt Recommendations
    if not st.session_state.chat_display:
        st.markdown("**💡 Quick Recommended Questions:**")
        rec_cols = st.columns(3)
        with rec_cols[0]:
            if st.button("Can the landlord keep my deposit?", use_container_width=True):
                st.session_state._quick_q = "Can the landlord keep my deposit?"
                st.rerun()
        with rec_cols[1]:
            if st.button("What are the termination conditions?", use_container_width=True):
                st.session_state._quick_q = "What are the termination conditions?"
                st.rerun()
        with rec_cols[2]:
            if st.button("Are there any late payment penalties?", use_container_width=True):
                st.session_state._quick_q = "Are there any late payment penalties?"
                st.rerun()

    quick_q = st.session_state.pop("_quick_q", None)
    user_input = st.chat_input("Ask a question about your agreement... e.g. 'What are my payment obligations?'")

    query_to_run = quick_q or user_input

    if query_to_run:
        with st.chat_message("user"):
            st.markdown(query_to_run)

        with st.chat_message("assistant"):
            with st.spinner("Searching ChromaDB vector store & generating cited answer..."):
                try:
                    res = post(
                        f"documents/{doc_id}/chat",
                        json_payload={"query": query_to_run, "top_k": 4},
                    )
                    answer_text = res.get("answer", "")
                    citations = res.get("citations", [])

                    st.markdown(answer_text)

                    if citations:
                        st.markdown("**📌 Cited Source Clauses:**")
                        for cit in citations:
                            q_txt = cit.get("quoted_text", "")
                            st.markdown(
                                f"<div class='citation-card'>"
                                f"<strong>📍 {html.escape(cit.get('clause_id', ''))}</strong> (chars {cit.get('source_span_start', 0)}–{cit.get('source_span_end', 0)})<br>"
                                f"<i>\"{html.escape(q_txt[:200])}{'...' if len(q_txt) > 200 else ''}\"</i>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    # Refresh chat history
                    history = get(f"documents/{doc_id}/chat-history")
                    st.session_state.chat_display = history.get("messages", [])
                    st.rerun()

                except Exception as e:
                    st.error(f"Chat query failed: {e}")
