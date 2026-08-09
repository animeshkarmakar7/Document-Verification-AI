import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="Legal Document Intelligence AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1.0rem; color: #64748B; margin-bottom: 1.5rem; }
    .risk-card-high { background-color: #FEF2F2; border-left: 5px solid #EF4444; padding: 1rem; border-radius: 6px; margin-bottom: 1rem; }
    .risk-card-medium { background-color: #FFFBEB; border-left: 5px solid #F59E0B; padding: 1rem; border-radius: 6px; margin-bottom: 1rem; }
    .risk-card-low { background-color: #F0FDF4; border-left: 5px solid #10B981; padding: 1rem; border-radius: 6px; margin-bottom: 1rem; }
    .citation-box { background-color: #F8FAFC; border: 1px solid #E2E8F0; padding: 0.75rem; border-radius: 4px; font-size: 0.9rem; font-family: monospace; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "document_id" not in st.session_state:
    st.session_state.document_id = None
if "document_info" not in st.session_state:
    st.session_state.document_info = None


def post(path, json_payload=None, files=None):
    url = f"{API_BASE_URL}/{path}"
    res = requests.post(url, json=json_payload, files=files, timeout=120)
    res.raise_for_status()
    return res.json()


def get(path):
    url = f"{API_BASE_URL}/{path}"
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    return res.json()


def run_step(label, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        st.write(f"✅ {label}")
        return result
    except Exception as e:
        err_detail = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                body = e.response.json()
                err_detail = body.get("detail") or body.get("error", {}).get("message", str(e))
            except Exception:
                err_detail = str(e)
        else:
            err_detail = str(e)
        st.warning(f"⚠️ {label} — skipped ({err_detail})")
        return None


with st.sidebar:
    st.image("https://img.icons8.com/color/96/scales.png", width=64)
    st.markdown("### Document Ingestion")

    uploaded_file = st.file_uploader(
        "Upload Legal Document",
        type=["pdf", "png", "jpg", "jpeg"],
        help="Upload a contract, lease, or Terms of Service. You can upload the same file again — results are retrieved from the database.",
    )

    if uploaded_file and st.button("Analyse with AI Pipeline", type="primary"):
        with st.status("Running Legal AI Pipeline...", expanded=True) as status_box:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}

            doc_data = run_step(
                "Uploading document",
                post, "documents/upload", files=files,
            )
            if doc_data is None:
                status_box.update(label="Upload failed — check backend.", state="error", expanded=True)
                st.stop()

            doc_id = doc_data["document_id"]
            st.session_state.document_id = doc_id
            st.session_state.document_info = doc_data

            run_step("OCR text extraction", post, f"documents/{doc_id}/ocr")
            run_step("Clause segmentation", post, f"documents/{doc_id}/clauses/segment")
            run_step("Gemini 3.6 classification", post, f"documents/{doc_id}/classify")
            run_step("Risk scoring", post, f"documents/{doc_id}/score-risk")
            run_step("Plain-language explanation", post, f"documents/{doc_id}/explain")

            status_box.update(label="Pipeline complete!", state="complete", expanded=False)
            st.rerun()

    if st.session_state.document_id:
        st.divider()
        st.markdown("**Active Document ID:**")
        st.code(st.session_state.document_id, language="text")
        if st.button("Clear Session"):
            st.session_state.document_id = None
            st.session_state.document_info = None
            st.rerun()


st.markdown(
    "<div class='main-header'>Generative AI Legal Document Demystifier</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='sub-header'>OCR &nbsp;•&nbsp; Clause Segmentation &nbsp;•&nbsp; Gemini 3.6 Classification &nbsp;•&nbsp; Risk Scoring &nbsp;•&nbsp; Grounded RAG Chat</div>",
    unsafe_allow_html=True,
)

if not st.session_state.document_id:
    st.info("👈 Upload a legal document in the sidebar to begin analysis.")
    st.stop()

doc_id = st.session_state.document_id

tab_dashboard, tab_clauses, tab_chat, tab_readability = st.tabs(
    ["📊 Risk Dashboard", "🔍 Clause Inspector", "💬 Grounded RAG Chat", "📈 Readability Report"]
)

with tab_dashboard:
    try:
        dashboard = get(f"documents/{doc_id}/risk-dashboard")
        overall_score = dashboard.get("overall_risk_score", 0)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Overall Risk Score", f"{overall_score} / 100")
        col2.metric("Total Clauses", dashboard.get("total_clauses", 0))
        col3.metric("High Risk Flags", dashboard.get("high_risk_count", 0), delta_color="inverse")
        col4.metric("Medium Risk Flags", dashboard.get("medium_risk_count", 0), delta_color="off")
        st.progress(min(overall_score / 100.0, 1.0))

        breakdown = dashboard.get("category_breakdown", {})
        if breakdown:
            st.subheader("Category Risk Breakdown")
            cols = st.columns(min(len(breakdown), 4))
            for idx, (cat, counts) in enumerate(breakdown.items()):
                with cols[idx % len(cols)]:
                    st.markdown(f"**{cat.replace('_', ' ')}**")
                    st.caption(
                        f"🔴 {counts.get('HIGH', 0)}  🟡 {counts.get('MEDIUM', 0)}  🟢 {counts.get('LOW', 0)}"
                    )

        st.subheader("⚠️ High-Risk Flags & Mitigations")
        high_clauses = dashboard.get("high_risk_clauses", [])
        if not high_clauses:
            st.success("No critical high-risk flags detected.")
        else:
            for item in high_clauses:
                st.markdown(
                    f"""
                    <div class='risk-card-high'>
                        <h4>🚨 {item.get('clause_id')} — {item.get('category', '').replace('_', ' ')}</h4>
                        <p><strong>Reason:</strong> {item.get('risk_reason', 'N/A')}</p>
                        <p><strong>Flag:</strong> {item.get('flag_type', 'N/A')} &nbsp;|&nbsp; <strong>Score:</strong> {item.get('risk_score', 'N/A')}</p>
                        <p><strong>Mitigation:</strong> {item.get('suggested_mitigation', 'N/A')}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    except Exception as e:
        st.warning(f"Risk dashboard not yet available. Run the pipeline first. ({e})")

with tab_clauses:
    st.subheader("Annotated Clauses & Plain-English Summaries")
    try:
        clauses_data = get(f"documents/{doc_id}/clauses?limit=100")
        clauses = clauses_data.get("items", [])

        try:
            class_data = get(f"documents/{doc_id}/classifications")
            class_map = {c["clause_pk"]: c["category"] for c in class_data.get("classifications", [])}
        except Exception:
            class_map = {}

        try:
            dashboard_data = get(f"documents/{doc_id}/risk-dashboard")
            risk_map = {r["clause_pk"]: r for r in dashboard_data.get("clauses", [])}
        except Exception:
            risk_map = {}

        try:
            explanations_list = get(f"documents/{doc_id}/explanations")
            expl_map = {e["clause_pk"]: e for e in explanations_list}
        except Exception:
            expl_map = {}

        if not clauses:
            st.info("No clauses found yet. Run the pipeline to segment this document.")
        else:
            for clause in clauses:
                pk = clause["id"]
                c_id = clause["clause_id"]
                category = class_map.get(pk, "OTHER")
                risk_info = risk_map.get(pk, {})
                expl_info = expl_map.get(pk, {})
                risk_level = risk_info.get("risk_level", "LOW")
                card_class = f"risk-card-{risk_level.lower()}"

                with st.expander(f"{c_id}  •  {category.replace('_', ' ')}  •  Risk: {risk_level}"):
                    st.markdown(
                        f"""
                        <div class='{card_class}'>
                            <p><strong>📝 Plain Summary:</strong> {expl_info.get('plain_summary', 'Not yet explained.')}</p>
                            <p><strong>⚖️ Risk Reason:</strong> {risk_info.get('risk_reason', 'N/A')}</p>
                            <p><strong>💡 Mitigation:</strong> {risk_info.get('suggested_mitigation', 'N/A')}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown("**Original Legalese Text:**")
                    st.info(clause["text"])
                    st.caption(
                        f"Source span: {clause['source_start']}–{clause['source_end']} &nbsp;|&nbsp; "
                        f"Confidence: {expl_info.get('confidence', '–')} &nbsp;|&nbsp; "
                        f"Grounded: {expl_info.get('is_grounded', '–')}"
                    )
    except Exception as e:
        st.warning(f"Clause data not yet available. Run the pipeline first. ({e})")

with tab_chat:
    st.subheader("Grounded Natural Language Q&A")
    st.caption("Answers are strictly grounded in the contract's retrieved clauses with explicit source citations.")

    try:
        history_data = get(f"documents/{doc_id}/chat-history")
        stored_messages = history_data.get("messages", [])
    except Exception:
        stored_messages = []

    for msg in stored_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            for cit in (msg.get("citations") or []):
                if isinstance(cit, dict):
                    st.markdown(
                        f"<div class='citation-box'>📌 <strong>{cit.get('clause_id')}</strong> "
                        f"(span {cit.get('source_span_start')}–{cit.get('source_span_end')})<br>"
                        f"<i>\"{cit.get('quoted_text')}\"</i></div>",
                        unsafe_allow_html=True,
                    )

    user_query = st.chat_input("e.g. Can the landlord keep my deposit if I leave early?")
    if user_query:
        with st.chat_message("user"):
            st.write(user_query)
        with st.chat_message("assistant"):
            with st.spinner("Searching clauses & generating grounded answer..."):
                try:
                    res = post(
                        f"documents/{doc_id}/chat",
                        json_payload={"query": user_query, "top_k": 3},
                    )
                    st.write(res["answer"])
                    for cit in res.get("citations", []):
                        st.markdown(
                            f"<div class='citation-box'>📌 <strong>{cit['clause_id']}</strong> "
                            f"(span {cit['source_span_start']}–{cit['source_span_end']})<br>"
                            f"<i>\"{cit['quoted_text']}\"</i></div>",
                            unsafe_allow_html=True,
                        )
                    st.caption(f"Confidence: {res.get('confidence', '–')}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Chat request failed: {e}")

with tab_readability:
    st.subheader("Flesch-Kincaid Readability & Grounding Statistics")
    try:
        report = get(f"documents/{doc_id}/readability-report")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Original Legalese Grade", f"Grade {report.get('average_original_grade', 'N/A')}")
        m2.metric("Plain Summary Grade", f"Grade {report.get('average_summary_grade', 'N/A')}")
        m3.metric("Readability Improvement", f"-{report.get('average_improvement', 0)} Grades")
        m4.metric(
            "Grounded Citations",
            f"{report.get('grounded_count', 0)} / {report.get('total_clauses', 0)}",
        )

        clause_reports = report.get("clauses", [])
        if clause_reports:
            st.divider()
            st.markdown("### Per-Clause Readability Comparison")
            for cr in clause_reports:
                col_a, col_b = st.columns([3, 1])
                col_a.markdown(f"**{cr['clause_id']}** — {cr['plain_summary']}")
                col_b.caption(
                    f"Original: Grade {cr['readability_score_original']} → "
                    f"Summary: Grade {cr['readability_score_summary']}"
                )
    except Exception as e:
        st.warning(f"Readability report not yet available. Run the pipeline first. ({e})")
