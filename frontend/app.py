import html
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="LegalDoc AI — Contract Intelligence & Analysis",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Global Custom CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background: #0B0E14; color: #E2E8F0; }
section[data-testid="stSidebar"] { background: #121722; border-right: 1px solid #1E2638; }

.sidebar-brand {
    font-size: 1.35rem; font-weight: 800; letter-spacing: -0.3px;
    color: #F8FAFC; margin-bottom: 0.2rem;
}
.sidebar-sub { font-size: 0.78rem; color: #64748B; margin-bottom: 1.5rem; }

.hero {
    background: linear-gradient(135deg, #131A29 0%, #1A2336 50%, #0F1623 100%);
    border: 1px solid #26334D;
    border-radius: 14px;
    padding: 2rem 2.4rem;
    margin-bottom: 1.8rem;
}
.hero-title {
    font-size: 2.2rem; font-weight: 800; letter-spacing: -0.5px;
    color: #F8FAFC;
}
.hero-sub { font-size: 0.95rem; color: #94A3B8; margin-top: 0.4rem; max-width: 800px; line-height: 1.5; }
.hero-pill {
    display: inline-block; background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.3); border-radius: 6px;
    padding: 0.25rem 0.75rem; font-size: 0.76rem; font-weight: 600; color: #A5B4FC;
    margin-right: 0.5rem; margin-top: 0.8rem; letter-spacing: 0.02em;
}

.summary-card {
    background: #141C2B; border: 1px solid #222F47; border-radius: 10px;
    padding: 1.5rem; margin-bottom: 1.5rem;
}
.summary-title { font-size: 1.25rem; font-weight: 700; color: #F8FAFC; margin-bottom: 0.3rem; }
.summary-type { font-size: 0.78rem; color: #818CF8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 1rem; }
.summary-exec { background: rgba(99,102,241,0.06); border-left: 3px solid #6366F1; padding: 1rem 1.2rem; border-radius: 6px; font-size: 0.92rem; color: #CBD5E1; line-height: 1.6; margin-bottom: 1rem; }

.section-head { font-size: 1.1rem; font-weight: 700; color: #F8FAFC; border-left: 3px solid #6366F1; padding-left: 0.75rem; margin: 1.5rem 0 1rem 0; }

.verbatim-text {
    background: #0D131F; border-left: 3px solid #475569; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}

.verbatim-text-HIGH {
    background: #0D131F; border-left: 4px solid #EF4444; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}
.verbatim-text-MEDIUM {
    background: #0D131F; border-left: 4px solid #F59E0B; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}
.verbatim-text-LOW {
    background: #0D131F; border-left: 4px solid #10B981; border-radius: 6px;
    padding: 0.9rem 1.1rem; font-family: 'Georgia', serif; font-size: 0.9rem;
    color: #E2E8F0; line-height: 1.7; margin: 0.6rem 0;
}

.badge-HIGH { background: rgba(239,68,68,0.15); border: 1px solid #EF4444; color: #FCA5A5; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; }
.badge-MEDIUM { background: rgba(245,158,11,0.15); border: 1px solid #F59E0B; color: #FCD34D; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; }
.badge-LOW { background: rgba(16,185,129,0.15); border: 1px solid #10B981; color: #6EE7B7; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.04em; }

.impact-box { background: rgba(239,68,68,0.05); border: 1px solid rgba(239,68,68,0.2); border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.6rem; font-size: 0.85rem; color: #FCA5A5; }
.mitigation-box { background: rgba(99,102,241,0.06); border: 1px solid rgba(99,102,241,0.2); border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.6rem; font-size: 0.85rem; color: #C7D2FE; }

.citation-card { background: rgba(20,28,43,0.9); border: 1px solid #222F47; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.5rem; font-size: 0.82rem; color: #A5B4FC; }

.empty-state { text-align: center; padding: 3.5rem 1rem; color: #64748B; font-size: 0.95rem; }
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
        st.write(f"[Complete] {label}")
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
        st.warning(f"[Skipped] {label} — {err}")
        return None


# ─── Sidebar Controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sidebar-brand'>LegalDoc AI</div>", unsafe_allow_html=True)
    st.markdown("<div class='sidebar-sub'>Contract Verification Platform</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Upload Document**")
    uploaded_file = st.file_uploader(
        "Drag and drop or browse",
        type=["pdf", "png", "jpg", "jpeg"],
        label_visibility="collapsed",
        help="Upload a contract, lease, agreement, or terms document.",
    )

    if uploaded_file and st.button("Analyze Document", type="primary", use_container_width=True):
        with st.status("Analyzing Document Verification Pipeline...", expanded=True) as status_box:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

            doc_data = run_step("Document Upload", post, "documents/upload", files=files)
            if doc_data is None:
                status_box.update(label="Upload failed.", state="error", expanded=True)
                st.stop()

            doc_id = doc_data["document_id"]
            st.session_state.document_id = doc_id
            st.session_state.document_info = doc_data
            st.session_state.chat_display = []

            run_step("Text Ingestion & Normalization", post, f"documents/{doc_id}/ocr")
            run_step("Clause Boundary Segmentation", post, f"documents/{doc_id}/clauses/segment")
            run_step("Taxonomy Categorization", post, f"documents/{doc_id}/classify")
            run_step("Risk Assessment & Evaluation", post, f"documents/{doc_id}/score-risk")
            run_step("Summary & Plain Language Analysis", post, f"documents/{doc_id}/explain")

            status_box.update(label="Analysis Complete", state="complete", expanded=False)
            st.rerun()

    if st.session_state.document_id:
        st.markdown("---")
        st.markdown("**Active Document**")
        info = st.session_state.document_info or {}
        filename = info.get("original_filename", "Document")
        st.markdown(f"`{filename}`")
        st.code(st.session_state.document_id[:12] + "...", language="text")
        if st.button("Clear Active Session", use_container_width=True):
            st.session_state.document_id = None
            st.session_state.document_info = None
            st.session_state.chat_display = []
            st.rerun()

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.73rem; color:#475569; line-height:1.5;'>"
        "<strong>Informational Disclaimer</strong><br>"
        "This platform provides automated contract verification analysis and does not constitute formal legal counsel."
        "</div>",
        unsafe_allow_html=True,
    )


# ─── Hero Header ──────────────────────────────────────────────────────────────
st.markdown("""
<div class='hero'>
  <div class='hero-title'>Contract Intelligence & Verification</div>
  <div class='hero-sub'>Automated Legal Document Analysis, Executive Summaries, Contractual Risk Exposure & Interactive Clause Inquiry</div>
  <span class='hero-pill'>Document Verification</span>
  <span class='hero-pill'>Executive Summary</span>
  <span class='hero-pill'>Risk Exposure Analysis</span>
  <span class='hero-pill'>Clause Transparency</span>
  <span class='hero-pill'>Interactive Inquiry</span>
</div>
""", unsafe_allow_html=True)

# ─── Empty Document State Guard ────────────────────────────────────────────────
if not st.session_state.document_id:
    st.markdown("""
    <div class='empty-state'>
        <div style='font-size: 1.1rem; font-weight: 600; color: #94A3B8; margin-bottom: 0.5rem;'>
            No active document selected
        </div>
        <div style='color: #475569;'>
            Upload a legal contract, lease, or agreement in the sidebar to initiate automated verification and risk analysis.
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

doc_id = st.session_state.document_id

# ─── Main Content Tabs ────────────────────────────────────────────────────────
tab_summary, tab_risk, tab_chat = st.tabs([
    "Executive Summary & Provisions",
    "Risk Analysis & Exposure",
    "Legal Inquiry Assistant",
])


# ==============================================================================
# TAB 1 — EXECUTIVE SUMMARY & DOCUMENT CLAUSES
# ==============================================================================
with tab_summary:
    st.markdown("<div class='section-head'>Executive Document Summary</div>", unsafe_allow_html=True)

    # 1. Fetch Executive Document Summary
    try:
        doc_summary = get(f"documents/{doc_id}/summary")

        st.markdown(f"""
        <div class='summary-card'>
            <div class='summary-title'>{html.escape(doc_summary.get('title', 'Contract Summary'))}</div>
            <div class='summary-type'>Type: {html.escape(doc_summary.get('document_type', 'Legal Agreement'))} &nbsp;·&nbsp; Total Clauses: {doc_summary.get('total_clauses', 0)}</div>
            <div class='summary-exec'>
                <strong>Executive Overview:</strong><br>
                {html.escape(doc_summary.get('executive_summary', 'No summary available.'))}
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns(2)

        def render_verified_items(items):
            if not items:
                st.caption("No specific items reported.")
                return
            for item in items:
                if isinstance(item, dict):
                    stmt = item.get("statement", "")
                    c_id = item.get("clause_id", "")
                    loc = item.get("source_location", "")
                    proof = item.get("verbatim_proof", "")

                    st.markdown(f"- **{html.escape(stmt)}**")
                    if proof or c_id or loc:
                        ref_label = f"Verify Proof in PDF ({c_id})" if c_id else "Verify Proof in PDF"
                        with st.expander(ref_label, expanded=False):
                            if loc or c_id:
                                st.caption(f"Source Reference: {html.escape(c_id)} &nbsp;·&nbsp; {html.escape(loc)}")
                            if proof:
                                st.markdown(
                                    f"<div class='verbatim-text'><strong>Exact Quote from PDF:</strong><br><i>\"{html.escape(proof)}\"</i></div>",
                                    unsafe_allow_html=True,
                                )
                else:
                    st.markdown(f"- {html.escape(str(item))}")

        with col_left:
            st.markdown("### Core Document Provisions")
            render_verified_items(doc_summary.get("key_points", []))

            st.markdown("### Critical Dates, Fees & Notice Periods")
            render_verified_items(doc_summary.get("important_dates_fees", []))

        with col_right:
            st.markdown("### Contractual Obligations")
            render_verified_items(doc_summary.get("user_obligations", []))

            st.markdown("### Contractual Rights & Protections")
            render_verified_items(doc_summary.get("user_rights", []))

    except Exception as e:
        st.warning(f"Executive summary unavailable. Please complete document processing. ({e})")


    st.divider()

    # 2. Detailed Document Clauses Section
    st.markdown("<div class='section-head'>Extracted Document Provisions</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Below are all provisions extracted from your document, categorized by legal section with source boundaries and summaries."
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
            st.info("No clauses identified in this document.")
        else:
            from collections import defaultdict
            groups = defaultdict(list)
            for clause in clauses:
                cat = class_map.get(clause["id"], "OTHER")
                groups[cat].append(clause)

            for cat, cat_clauses in sorted(groups.items()):
                cat_label = cat.replace("_", " ").title()
                with st.expander(f"{cat_label} ({len(cat_clauses)} provision{'s' if len(cat_clauses) > 1 else ''})", expanded=True):
                    for clause in cat_clauses:
                        pk = clause["id"]
                        c_id = clause["clause_id"]
                        raw_text = clause.get("text", "").strip()
                        expl = expl_map.get(pk, {})
                        summary = expl.get("plain_summary", "")
                        span_start = clause.get("source_start", 0)
                        span_end = clause.get("source_end", 0)

                        st.markdown(f"**{html.escape(c_id)}** &nbsp;•&nbsp; <span style='font-size:0.75rem; color:#64748B;'>chars {span_start}–{span_end}</span>", unsafe_allow_html=True)
                        st.markdown(f"<div class='verbatim-text'>{html.escape(raw_text)}</div>", unsafe_allow_html=True)
                        if summary:
                            st.info(f"**Plain Summary:** {summary}")
                        st.caption("---")

    except Exception as e:
        st.warning(f"Could not load provision details. ({e})")


# ==============================================================================
# TAB 2 — RISK ANALYSIS & IMPACT
# ==============================================================================
with tab_risk:
    st.markdown("<div class='section-head'>Risk Analysis & Exposure Assessment</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Evaluating contractual provisions for liability exposure, one-sided terms, strict exit penalties, and ambiguous obligations."
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
        c2.metric("High Risk Provisions", high_cnt)
        c3.metric("Medium Risk Provisions", med_cnt)
        c4.metric("Low Risk Provisions", low_cnt)

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
            st.success("No contract risks identified.")
        else:
            filter_levels = st.multiselect(
                "Filter Risk Exposure Level",
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
                    impact_text = f"This high-risk provision could impose unilateral legal liability, severe financial penalties, or restrict rights without prior notice."
                elif r_level == "MEDIUM":
                    impact_text = f"This medium-risk provision warrants review as it contains strict timelines, conditional charges, or ambiguous terms."
                else:
                    impact_text = f"Low risk term representing standard commercial practices with minimal negative legal impact."

                with st.container():
                    st.markdown(
                        f"""
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <strong style='font-size:1.05rem;'>{html.escape(c_id)}</strong>
                            <span class='badge-{r_level}'>{r_level} RISK (Score: {int(score*100) if score <= 1.0 else int(score)}%)</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown(f"<div class='verbatim-text-{r_level}'><strong>Exact Clause Text:</strong><br>{html.escape(verbatim_txt if verbatim_txt else 'Text unavailable.')}</div>", unsafe_allow_html=True)
                    st.markdown(f"**Risk Assessment:** {html.escape(reason)}")
                    st.markdown(f"<div class='impact-box'><strong>Potential User Impact:</strong> {html.escape(impact_text)}</div>", unsafe_allow_html=True)
                    if mitigation:
                        st.markdown(f"<div class='mitigation-box'><strong>Mitigation Recommendation:</strong> {html.escape(mitigation)}</div>", unsafe_allow_html=True)
                    st.caption(f"Flag Category: {flag}")
                    st.divider()

    except Exception as e:
        st.warning(f"Risk analysis data unavailable. Please complete document processing. ({e})")


# ==============================================================================
# TAB 3 — GROUNDED RAG CHATBOT
# ==============================================================================
with tab_chat:
    st.markdown("<div class='section-head'>Interactive Legal Assistant</div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; font-size:0.87rem;'>"
        "Ask specific questions regarding obligations, rights, fees, or termination conditions. All responses reference verified contract text."
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
                st.markdown("**Cited Contract Provisions:**")
                for cit in citations:
                    if isinstance(cit, dict):
                        q_txt = cit.get("quoted_text", "")
                        st.markdown(
                            f"<div class='citation-card'>"
                            f"<strong>{html.escape(cit.get('clause_id', ''))}</strong> (chars {cit.get('source_span_start', 0)}–{cit.get('source_span_end', 0)})<br>"
                            f"<i>\"{html.escape(q_txt[:200])}{'...' if len(q_txt) > 200 else ''}\"</i>"
                            f"</div>",
                            unsafe_allow_html=True,
                            )

    # Prompt Recommendations
    if not st.session_state.chat_display:
        st.markdown("**Suggested Sample Inquiries:**")
        rec_cols = st.columns(3)
        with rec_cols[0]:
            if st.button("What are the deposit refund conditions?", use_container_width=True):
                st.session_state._quick_q = "What are the deposit refund conditions?"
                st.rerun()
        with rec_cols[1]:
            if st.button("What are the termination notice terms?", use_container_width=True):
                st.session_state._quick_q = "What are the termination notice terms?"
                st.rerun()
        with rec_cols[2]:
            if st.button("Are there late payment penalty fees?", use_container_width=True):
                st.session_state._quick_q = "Are there late payment penalty fees?"
                st.rerun()

    quick_q = st.session_state.pop("_quick_q", None)
    user_input = st.chat_input("Inquire about contract terms... e.g. 'What are my fee liabilities?'")

    query_to_run = quick_q or user_input

    if query_to_run:
        with st.chat_message("user"):
            st.markdown(query_to_run)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing document provisions and formulating answer..."):
                try:
                    res = post(
                        f"documents/{doc_id}/chat",
                        json_payload={"query": query_to_run, "top_k": 4},
                    )
                    answer_text = res.get("answer", "")
                    citations = res.get("citations", [])

                    st.markdown(answer_text)

                    if citations:
                        st.markdown("**Cited Contract Provisions:**")
                        for cit in citations:
                            q_txt = cit.get("quoted_text", "")
                            st.markdown(
                                f"<div class='citation-card'>"
                                f"<strong>{html.escape(cit.get('clause_id', ''))}</strong> (chars {cit.get('source_span_start', 0)}–{cit.get('source_span_end', 0)})<br>"
                                f"<i>\"{html.escape(q_txt[:200])}{'...' if len(q_txt) > 200 else ''}\"</i>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                    # Refresh chat history
                    history = get(f"documents/{doc_id}/chat-history")
                    st.session_state.chat_display = history.get("messages", [])
                    st.rerun()

                except Exception as e:
                    st.error(f"Inquiry query failed: {e}")
