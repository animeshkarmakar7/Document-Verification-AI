import hashlib
import html
import time
import requests
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"

st.set_page_config(
    page_title="LegalDoc AI — Contract Intelligence & Analysis",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Language Translations Dictionary ─────────────────────────────────────────
TRANSLATIONS = {
    "en": {
        "app_title": "Contract Intelligence & Verification",
        "app_sub": "Automated Legal Document Analysis, Executive Summaries, Contractual Risk Exposure & Interactive Clause Inquiry",
        "pill_verify": "Document Verification",
        "pill_summary": "Executive Summary",
        "pill_risk": "Risk Exposure Analysis",
        "pill_transparency": "Clause Transparency",
        "pill_inquiry": "Interactive Inquiry",
        "upload_label": "Upload Legal Document",
        "btn_analyze": "Analyze Document",
        "active_doc": "Active Document",
        "btn_clear": "Clear Active Session",
        "disclaimer_head": "Informational Disclaimer",
        "disclaimer_text": "This platform provides automated contract verification analysis and does not constitute formal legal counsel.",
        "empty_head": "No active document selected",
        "empty_sub": "Upload a legal contract, lease, or agreement in the sidebar to initiate automated verification and risk analysis.",
        "tab_summary": "Executive Summary & Provisions",
        "tab_risk": "Risk Analysis & Exposure",
        "tab_chat": "Legal Inquiry Assistant",
        "exec_head": "Executive Document Summary",
        "exec_overview": "Executive Overview:",
        "core_provisions": "Core Document Provisions",
        "critical_dates": "Critical Dates, Fees & Notice Periods",
        "contract_obligations": "Contractual Obligations",
        "contract_rights": "Contractual Rights & Protections",
        "extracted_provisions": "Extracted Document Provisions",
        "extracted_sub": "Below are all provisions extracted from your document, categorized by legal section with source boundaries and summaries.",
        "plain_summary": "Plain Summary:",
        "verify_proof": "Verify Proof in PDF",
        "exact_quote": "Exact Quote from PDF:",
        "source_ref": "Source Reference:",
        "risk_head": "Risk Analysis & Exposure Assessment",
        "risk_sub": "Evaluating contractual provisions for liability exposure, one-sided terms, strict exit penalties, and ambiguous obligations.",
        "overall_risk": "Overall Risk Score",
        "high_risk_cnt": "High Risk Provisions",
        "med_risk_cnt": "Medium Risk Provisions",
        "low_risk_cnt": "Low Risk Provisions",
        "filter_risk": "Filter Risk Exposure Level",
        "exact_clause_text": "Exact Clause Text:",
        "risk_assessment": "Risk Assessment:",
        "user_impact": "Potential User Impact:",
        "mitigation_rec": "Mitigation Recommendation:",
        "no_risks": "No contract risks identified.",
        "chat_head": "Interactive Legal Assistant",
        "chat_sub": "Ask specific questions regarding obligations, rights, fees, or termination conditions. All responses reference verified contract text.",
        "cited_provisions": "Cited Contract Provisions:",
        "suggested_questions": "Suggested Sample Inquiries:",
        "q1": "What are the deposit refund conditions?",
        "q2": "What are the termination notice terms?",
        "q3": "Are there late payment penalty fees?",
        "chat_placeholder": "Inquire about contract terms... e.g. 'What are my fee liabilities?'",
        "status_analyzing": "Analyzing Document Verification Pipeline...",
        "status_complete": "Analysis Complete",
        "complete_lbl": "[Complete]",
        "skipped_lbl": "[Skipped]",
    },
    "hi": {
        "app_title": "अनुबंध इंटेलिजेंस और सत्यापन",
        "app_sub": "स्वचालित कानूनी दस्तावेज़ विश्लेषण, कार्यकारी सारांश, अनुबंध जोखिम और इंटरएक्टिव पूछताछ",
        "pill_verify": "दस्तावेज़ सत्यापन",
        "pill_summary": "कार्यकारी सारांश",
        "pill_risk": "जोखिम विश्लेषण",
        "pill_transparency": "धारा पारदर्शिता",
        "pill_inquiry": "इंटरएक्टिव पूछताछ",
        "upload_label": "कानूनी दस्तावेज़ अपलोड करें",
        "btn_analyze": "दस्तावेज़ का विश्लेषण करें",
        "active_doc": "सक्रिय दस्तावेज़",
        "btn_clear": "सत्र साफ़ करें",
        "disclaimer_head": "सूचनात्मक अस्वीकरण",
        "disclaimer_text": "यह मंच स्वचालित अनुबंध सत्यापन विश्लेषण प्रदान करता है और औपचारिक कानूनी सलाह का गठन नहीं करता है।",
        "empty_head": "कोई सक्रिय दस्तावेज़ नहीं चुना गया",
        "empty_sub": "स्वचालित सत्यापन और जोखिम विश्लेषण शुरू करने के लिए साइडबार में अनुबंध या समझौता अपलोड करें।",
        "tab_summary": "कार्यकारी सारांश और प्रावधान",
        "tab_risk": "जोखिम विश्लेषण और प्रभाव",
        "tab_chat": "कानूनी पूछताछ सहायक",
        "exec_head": "कार्यकारी दस्तावेज़ सारांश",
        "exec_overview": "कार्यकारी अवलोकन:",
        "core_provisions": "मुख्य दस्तावेज़ प्रावधान",
        "critical_dates": "महत्वपूर्ण तिथियां, शुल्क और नोटिस अवधि",
        "contract_obligations": "अनुबंधात्मक दायित्व",
        "contract_rights": "अनुबंधात्मक अधिकार और सुरक्षा",
        "extracted_provisions": "निकाले गए दस्तावेज़ प्रावधान",
        "extracted_sub": "नीचे आपके दस्तावेज़ से निकाले गए सभी प्रावधान कानूनी अनुभाग द्वारा वर्गीकृत हैं।",
        "plain_summary": "सरल सारांश:",
        "verify_proof": "पीडीएफ में प्रमाण सत्यापित करें",
        "exact_quote": "पीडीएफ से सटीक उद्धरण:",
        "source_ref": "स्रोत संदर्भ:",
        "risk_head": "जोखिम विश्लेषण और प्रभाव मूल्यांकन",
        "risk_sub": "दायित्व, एकतरफा शर्तों, सख्त निकास दंड और अस्पष्ट दायित्वों के लिए संविदात्मक प्रावधानों का मूल्यांकन।",
        "overall_risk": "कुल जोखिम स्कोर",
        "high_risk_cnt": "उच्च जोखिम प्रावधान",
        "med_risk_cnt": "मध्यम जोखिम प्रावधान",
        "low_risk_cnt": "कम जोखिम प्रावधान",
        "filter_risk": "जोखिम स्तर फ़िल्टर करें",
        "exact_clause_text": "सटीक धारा पाठ:",
        "risk_assessment": "जोखिम मूल्यांकन:",
        "user_impact": "संभावित उपयोगकर्ता प्रभाव:",
        "mitigation_rec": "शमन सिफारिश:",
        "no_risks": "कोई अनुबंध जोखिम नहीं पाया गया।",
        "chat_head": "इंटरएक्टिव कानूनी सहायक",
        "chat_sub": "दायित्वों, अधिकारों, शुल्कों या समाप्ति की शर्तों के बारे में प्रश्न पूछें।",
        "cited_provisions": "उद्धृत अनुबंध प्रावधान:",
        "suggested_questions": "सुझाए गए प्रश्न:",
        "q1": "जमानत वापसी की शर्तें क्या हैं?",
        "q2": "समाप्ति नोटिस की शर्तें क्या हैं?",
        "q3": "क्या देर से भुगतान का जुर्माना है?",
        "chat_placeholder": "अनुबंध की शर्तों के बारे में पूछें...",
        "status_analyzing": "दस्तावेज़ विश्लेषण पाइपलाइन चल रही है...",
        "status_complete": "विश्लेषण पूरा हुआ",
        "complete_lbl": "[पूर्ण]",
        "skipped_lbl": "[छोड़ा गया]",
    },
    "mr": {
        "app_title": "करार बुद्धिमत्ता आणि पडताळणी",
        "app_sub": "स्वयंचलित कायदेशीर दस्तऐवज विश्लेषण, कार्यकारी सारांश, करारातील धोके आणि परस्परसंवादी चौकशी",
        "pill_verify": "दस्तऐवज पडताळणी",
        "pill_summary": "कार्यकारी सारांश",
        "pill_risk": "धोका विश्लेषण",
        "pill_transparency": "कलम पारदर्शकता",
        "pill_inquiry": "परस्परसंवादी चौकशी",
        "upload_label": "कायदेशीर दस्तऐवज अपलोड करा",
        "btn_analyze": "दस्तऐवजाचे विश्लेषण करा",
        "active_doc": "सक्रिय दस्तऐवज",
        "btn_clear": "सत्र साफ करा",
        "disclaimer_head": "माहितीपूर्ण अस्वीकरण",
        "disclaimer_text": "हे व्यासपीठ स्वयंचलित करार पडताळणी विश्लेषण प्रदान करते आणि औपचारिक कायदेशीर सल्ला देत नाही.",
        "empty_head": "कोणताही दस्तऐवज निवडलेला नाही",
        "empty_sub": "स्वयंचलित पडताळणी आणि धोका विश्लेषण सुरू करण्यासाठी साइडबारमध्ये करार किंवा करारपत्र अपलोड करा.",
        "tab_summary": "कार्यकारी सारांश आणि तरतुदी",
        "tab_risk": "धोका विश्लेषण आणि प्रभाव",
        "tab_chat": "कायदेशीर चौकशी सहाय्यक",
        "exec_head": "कार्यकारी दस्तऐवज सारांश",
        "exec_overview": "कार्यकारी आढावा:",
        "core_provisions": "मुख्य दस्तऐवज तरतुदी",
        "critical_dates": "महत्त्वाच्या तारखा, शुल्क आणि नोटीस कालावधी",
        "contract_obligations": "करारातील जबाबदाऱ्या",
        "contract_rights": "करारातील हक्क आणि संरक्षण",
        "extracted_provisions": "काढलेल्या दस्तऐवजाच्या तरतुदी",
        "extracted_sub": "खाली तुमच्या दस्तऐवजातून काढलेल्या सर्व तरतुदी कायदेशीर विभागांनुसार वर्गीकृत केल्या आहेत.",
        "plain_summary": "सोपा सारांश:",
        "verify_proof": "पीडीएफमध्ये पुरावा पडताळा",
        "exact_quote": "पीडीएफमधील अचूक अवतरण:",
        "source_ref": "स्रोत संदर्भ:",
        "risk_head": "धोका विश्लेषण आणि प्रभाव मूल्यमापन",
        "risk_sub": "जबाबदारी, एकतर्फी अटी, कठोर दंड आणि अस्पष्ट जबाबदाऱ्यांसाठी करारातील तरतुदींचे मूल्यमापन.",
        "overall_risk": "एकूण धोका गुण",
        "high_risk_cnt": "उच्च धोका तरतुदी",
        "med_risk_cnt": "मध्यम धोका तरतुदी",
        "low_risk_cnt": "कमी धोका तरतुदी",
        "filter_risk": "धोका पातळी फिल्टर करा",
        "exact_clause_text": "अचूक कलम मजकूर:",
        "risk_assessment": "धोका मूल्यमापन:",
        "user_impact": "संभाव्य वापरकर्ता प्रभाव:",
        "mitigation_rec": "उपाययोजना शिफारस:",
        "no_risks": "कोणतेही करारातील धोके आढळले नाहीत.",
        "chat_head": "परस्परसंवादी कायदेशीर सहाय्यक",
        "chat_sub": "जबाबदाऱ्या, हक्क, शुल्क किंवा समाप्तीच्या अटींबद्दल प्रश्न विचारा.",
        "cited_provisions": "उधृत केलेल्या कराराच्या तरतुदी:",
        "suggested_questions": "सुचवलेले प्रश्न:",
        "q1": "ठेव परताव्याच्या अटी काय आहेत?",
        "q2": "समाप्ती नोटीसच्या अटी काय आहेत?",
        "q3": "उशिरा भरल्यास दंडात्मक शुल्क आहे का?",
        "chat_placeholder": "कराराच्या अटींबद्दल विचारा...",
        "status_analyzing": "दस्तऐवज विश्लेषण सुरू आहे...",
        "status_complete": "विश्लेषण पूर्ण झाले",
        "complete_lbl": "[पूर्ण]",
        "skipped_lbl": "[वगळले]",
    },
}

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
.sidebar-sub { font-size: 0.78rem; color: #64748B; margin-bottom: 1rem; }

.hero {
    background: linear-gradient(135deg, #131A29 0%, #1A2336 50%, #0F1623 100%);
    border: 1px solid #26334D;
    border-radius: 14px;
    padding: 1.8rem 2.2rem;
    margin-bottom: 1.8rem;
}
.hero-title {
    font-size: 2.1rem; font-weight: 800; letter-spacing: -0.5px;
    color: #F8FAFC;
}
.hero-sub { font-size: 0.92rem; color: #94A3B8; margin-top: 0.4rem; max-width: 850px; line-height: 1.5; }
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
if "lang" not in st.session_state:
    st.session_state.lang = "en"

# Active Translation Object
T = TRANSLATIONS.get(st.session_state.lang, TRANSLATIONS["en"])


# ─── API Helper Functions ─────────────────────────────────────────────────────
def post(path, json_payload=None, files=None):
    res = requests.post(f"{API_BASE_URL}/{path}", json=json_payload, files=files, timeout=180)
    res.raise_for_status()
    return res.json()


def get(path):
    res = requests.get(f"{API_BASE_URL}/{path}", timeout=60)
    res.raise_for_status()
    return res.json()


def put(path_or_url, data=None, headers=None):
    url = path_or_url if path_or_url.startswith("http") else f"{API_BASE_URL}/{path_or_url}"
    res = requests.put(url, data=data, headers=headers, timeout=300)
    res.raise_for_status()
    try:
        return res.json()
    except Exception:
        return {"status": "ok"}


def run_step(label, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        st.write(f"{T['complete_lbl']} {label}")
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
        st.warning(f"{T['skipped_lbl']} {label} — {err}")
        return None


# ─── Sidebar Controls & Language Switcher ─────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sidebar-brand'>LegalDoc AI</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sidebar-sub'>{T['app_title']}</div>", unsafe_allow_html=True)

    # 🌐 Instant UI Language Translator Buttons
    st.markdown("**UI Language / भाषा / भाषा नविडा**")
    lang_cols = st.columns(3)
    with lang_cols[0]:
        if st.button("English", type="primary" if st.session_state.lang == "en" else "secondary", use_container_width=True):
            st.session_state.lang = "en"
            st.rerun()
    with lang_cols[1]:
        if st.button("हिंदी", type="primary" if st.session_state.lang == "hi" else "secondary", use_container_width=True):
            st.session_state.lang = "hi"
            st.rerun()
    with lang_cols[2]:
        if st.button("मराठी", type="primary" if st.session_state.lang == "mr" else "secondary", use_container_width=True):
            st.session_state.lang = "mr"
            st.rerun()

    st.markdown("---")
    with st.expander("🤖 **AI Models & Resilience**", expanded=False):
        st.markdown(
            "**Primary:** `Gemini 3.6-Flash`  \n"
            "**Failover 1:** `Gemini 3.5/3.7-Flash`  \n"
            "**Failover 2:** `LLaMA3 (Groq/Ollama)`  \n"
            "**Strategy:** Auto-retry with backoff on rate-limits (429/503), seamless fallback to LLaMA3."
        )
        groq_key_input = st.text_input(
            "Groq API Key (Optional LLaMA3)",
            type="password",
            value=st.session_state.get("groq_key", ""),
            help="Free API key from console.groq.com for LLaMA 3.3 / 3.1 fallback.",
        )
        if groq_key_input and groq_key_input != st.session_state.get("groq_key"):
            st.session_state.groq_key = groq_key_input

    st.markdown(f"**{T['upload_label']}**")
    uploaded_file = st.file_uploader(
        "Upload file",
        type=["pdf", "png", "jpg", "jpeg"],
        label_visibility="collapsed",
        help="Upload a contract, lease, agreement, or terms document.",
    )

    if uploaded_file and st.button(T["btn_analyze"], type="primary", use_container_width=True):
        with st.status(T["status_analyzing"], expanded=True) as status_box:
            file_bytes = uploaded_file.getvalue()
            file_size = len(file_bytes)
            sha256_hash = hashlib.sha256(file_bytes).hexdigest()
            doc_id = None
            doc_data = None

            # ── 1. Smart Upload: Presigned PUT for files > 5MB, standard multipart otherwise ──
            if file_size > 5 * 1024 * 1024:
                try:
                    st.write("Initializing direct storage upload for large document...")
                    presigned_req = {
                        "filename": uploaded_file.name,
                        "content_type": uploaded_file.type or "application/pdf",
                        "file_size": file_size,
                    }
                    presigned = post("commands/documents/presigned-upload", json_payload=presigned_req)
                    upload_url = presigned["upload_url"]
                    st.write(f"Streaming file bytes directly ({file_size / (1024 * 1024):.1f} MB)...")
                    put(upload_url, data=file_bytes, headers=presigned.get("required_headers", {}))

                    complete_req = {
                        "document_id": presigned["document_id"],
                        "filename": uploaded_file.name,
                        "content_type": uploaded_file.type or "application/pdf",
                        "file_size": file_size,
                        "sha256": sha256_hash,
                        "object_key": presigned["object_key"],
                        "processing_pool": "cpu",
                    }
                    queued = post("commands/documents/upload-complete", json_payload=complete_req)
                    doc_id = queued["document_id"]
                    doc_data = {
                        "document_id": doc_id,
                        "original_filename": uploaded_file.name,
                        "status": queued["status"],
                    }
                    st.write(f"{T['complete_lbl']} Direct Upload Complete — Ingestion Enqueued")
                except Exception as e:
                    st.warning(f"Direct presigned upload encountered an issue ({e}); falling back to standard upload...")
                    doc_id = None

            if doc_id is None:
                files = {"file": (uploaded_file.name, file_bytes, uploaded_file.type or "application/pdf")}
                doc_data = run_step("Document Upload", post, "commands/documents/upload", files=files)
                if doc_data is None:
                    status_box.update(label="Upload failed.", state="error", expanded=True)
                    st.stop()
                doc_id = doc_data["document_id"]

            st.session_state.document_id = doc_id
            st.session_state.document_info = doc_data
            st.session_state.chat_display = []

            # ── 2. Live Background Status Polling Loop ──
            poll_start = time.time()
            max_poll_seconds = 300
            last_stage = None
            consecutive_queued = 0

            while time.time() - poll_start < max_poll_seconds:
                try:
                    pipeline_status = get(f"queries/documents/{doc_id}/pipeline-status")
                except Exception:
                    time.sleep(1.5)
                    continue

                status_val = pipeline_status.get("status", "")
                stage_name = pipeline_status.get("stage", "Processing")
                pct = pipeline_status.get("progress_percent", 10)
                clause_cnt = pipeline_status.get("clause_count", 0)

                if stage_name != last_stage:
                    st.write(f"🔄 [{pct}%] {stage_name} ({clause_cnt} provisions found)")
                    last_stage = stage_name

                status_box.update(
                    label=f"Analyzing... [{pct}%] {stage_name}",
                    state="running",
                )

                if pipeline_status.get("is_complete") or status_val == "EXPLAINED":
                    status_box.update(
                        label=f"{T['status_complete']} ({clause_cnt} provisions analyzed)",
                        state="complete",
                        expanded=False,
                    )
                    st.rerun()

                if pipeline_status.get("is_failed") or status_val == "FAILED":
                    err_msg = pipeline_status.get("error_message") or "Pipeline processing encountered an error."
                    status_box.update(label=f"Analysis Failed: {err_msg}", state="error")
                    st.error(err_msg)
                    st.stop()

                # If status remains QUEUED for 3 polling cycles (e.g. standalone local mode with no Celery worker),
                # run the synchronous pipeline gracefully so single-node testing never hangs:
                if status_val == "QUEUED":
                    consecutive_queued += 1
                    if consecutive_queued >= 3:
                        st.info("No active Celery consumer detected; executing pipeline directly...")
                        run_step("OCR & Text Extraction", post, f"commands/documents/{doc_id}/ingest/text")
                        seg_data = run_step("Clause Segmentation", post, f"commands/documents/{doc_id}/clauses/segment")
                        run_step("Clause Classification", post, f"commands/documents/{doc_id}/classify")
                        run_step("Risk Exposure Scoring", post, f"commands/documents/{doc_id}/score-risk")
                        run_step("Plain-English Explanations", post, f"commands/documents/{doc_id}/explain")
                        final_cnt = seg_data.get("clause_count", 0) if seg_data else clause_cnt
                        status_box.update(
                            label=f"{T['status_complete']} ({final_cnt} provisions analyzed)",
                            state="complete",
                            expanded=False,
                        )
                        st.rerun()

                time.sleep(1.5)

            status_box.update(label="Analysis timed out. Please check document status.", state="error")
            st.rerun()

    if st.session_state.document_id:
        st.markdown("---")
        st.markdown(f"**{T['active_doc']}**")
        info = st.session_state.document_info or {}
        filename = info.get("original_filename", "Document")
        st.markdown(f"`{filename}`")
        st.code(st.session_state.document_id[:12] + "...", language="text")
        if st.button(T["btn_clear"], use_container_width=True):
            st.session_state.document_id = None
            st.session_state.document_info = None
            st.session_state.chat_display = []
            st.rerun()

    st.markdown("---")
    st.markdown(
        f"<div style='font-size:0.73rem; color:#475569; line-height:1.5;'>"
        f"<strong>{T['disclaimer_head']}</strong><br>"
        f"{T['disclaimer_text']}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ─── Hero Header ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class='hero'>
  <div class='hero-title'>{T['app_title']}</div>
  <div class='hero-sub'>{T['app_sub']}</div>
  <span class='hero-pill'>{T['pill_verify']}</span>
  <span class='hero-pill'>{T['pill_summary']}</span>
  <span class='hero-pill'>{T['pill_risk']}</span>
  <span class='hero-pill'>{T['pill_transparency']}</span>
  <span class='hero-pill'>{T['pill_inquiry']}</span>
</div>
""", unsafe_allow_html=True)

# ─── Empty Document State Guard ────────────────────────────────────────────────
if not st.session_state.document_id:
    st.markdown(f"""
    <div class='empty-state'>
        <div style='font-size: 1.1rem; font-weight: 600; color: #94A3B8; margin-bottom: 0.5rem;'>
            {T['empty_head']}
        </div>
        <div style='color: #475569;'>
            {T['empty_sub']}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

doc_id = st.session_state.document_id

# ─── Main Content Tabs ────────────────────────────────────────────────────────
tab_summary, tab_risk, tab_chat = st.tabs([
    T["tab_summary"],
    T["tab_risk"],
    T["tab_chat"],
])


# ==============================================================================
# TAB 1 — EXECUTIVE SUMMARY & DOCUMENT CLAUSES
# ==============================================================================
with tab_summary:
    st.markdown(f"<div class='section-head'>{T['exec_head']}</div>", unsafe_allow_html=True)

    # 1. Fetch Executive Document Summary
    try:
        doc_summary = get(f"queries/documents/{doc_id}/summary")

        st.markdown(f"""
        <div class='summary-card'>
            <div class='summary-title'>{html.escape(doc_summary.get('title', 'Contract Summary'))}</div>
            <div class='summary-type'>Type: {html.escape(doc_summary.get('document_type', 'Legal Agreement'))} &nbsp;·&nbsp; Total Clauses: {doc_summary.get('total_clauses', 0)}</div>
            <div class='summary-exec'>
                <strong>{T['exec_overview']}</strong><br>
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
                        ref_label = f"{T['verify_proof']} ({c_id})" if c_id else T["verify_proof"]
                        with st.expander(ref_label, expanded=False):
                            if loc or c_id:
                                st.caption(f"{T['source_ref']} {html.escape(c_id)} &nbsp;·&nbsp; {html.escape(loc)}")
                            if proof:
                                st.markdown(
                                    f"<div class='verbatim-text'><strong>{T['exact_quote']}</strong><br><i>\"{html.escape(proof)}\"</i></div>",
                                    unsafe_allow_html=True,
                                )
                else:
                    st.markdown(f"- {html.escape(str(item))}")

        with col_left:
            st.markdown(f"### {T['core_provisions']}")
            render_verified_items(doc_summary.get("key_points", []))

            st.markdown(f"### {T['critical_dates']}")
            render_verified_items(doc_summary.get("important_dates_fees", []))

        with col_right:
            st.markdown(f"### {T['contract_obligations']}")
            render_verified_items(doc_summary.get("user_obligations", []))

            st.markdown(f"### {T['contract_rights']}")
            render_verified_items(doc_summary.get("user_rights", []))

    except Exception as e:
        st.warning(f"Executive summary unavailable. Please complete document processing. ({e})")

    st.divider()

    # 2. Detailed Document Clauses Section
    st.markdown(f"<div class='section-head'>{T['extracted_provisions']}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:#64748B; font-size:0.87rem;'>"
        f"{T['extracted_sub']}"
        f"</p>",
        unsafe_allow_html=True,
    )

    try:
        clauses_resp = get(f"queries/documents/{doc_id}/clauses?limit=200")
        clauses = clauses_resp.get("clauses", [])

        class_map = {}
        try:
            class_data = get(f"queries/documents/{doc_id}/classifications")
            for c in class_data.get("classifications", []):
                class_map[c["clause_id"]] = c.get("category", "OTHER")
        except Exception:
            pass

        expl_map = {}
        try:
            explanations = get(f"queries/documents/{doc_id}/explanations")
            for e in explanations:
                expl_map[e["clause_id"]] = e
        except Exception:
            pass

        if not clauses:
            st.info("No clauses identified in this document.")
        else:
            from collections import defaultdict
            groups = defaultdict(list)
            for clause in clauses:
                cat = class_map.get(clause["clause_id"], "OTHER")
                groups[cat].append(clause)

            for cat, cat_clauses in sorted(groups.items()):
                cat_label = cat.replace("_", " ").title()
                with st.expander(f"{cat_label} ({len(cat_clauses)} provision{'s' if len(cat_clauses) > 1 else ''})", expanded=True):
                    for clause in cat_clauses:
                        c_id = clause["clause_id"]
                        raw_text = clause.get("text", "").strip()
                        expl = expl_map.get(c_id, {})
                        summary = expl.get("plain_summary", "")
                        source_span = clause.get("source_text_span", {})
                        span_start = source_span.get("start", 0)
                        span_end = source_span.get("end", 0)

                        st.markdown(f"**{html.escape(c_id)}** &nbsp;•&nbsp; <span style='font-size:0.75rem; color:#64748B;'>chars {span_start}–{span_end}</span>", unsafe_allow_html=True)
                        st.markdown(f"<div class='verbatim-text'>{html.escape(raw_text)}</div>", unsafe_allow_html=True)
                        if summary:
                            st.info(f"**{T['plain_summary']}** {summary}")
                        st.caption("---")

    except Exception as e:
        st.warning(f"Could not load provision details. ({e})")


# ==============================================================================
# TAB 2 — RISK ANALYSIS & IMPACT
# ==============================================================================
with tab_risk:
    st.markdown(f"<div class='section-head'>{T['risk_head']}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:#64748B; font-size:0.87rem;'>"
        f"{T['risk_sub']}"
        f"</p>",
        unsafe_allow_html=True,
    )

    try:
        dashboard = get(f"queries/documents/{doc_id}/risk-dashboard")
        overall_score = dashboard.get("overall_risk_score", 0)
        high_cnt = dashboard.get("high_risk_count", 0)
        med_cnt = dashboard.get("medium_risk_count", 0)
        low_cnt = dashboard.get("low_risk_count", 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(T["overall_risk"], f"{overall_score} / 100")
        c2.metric(T["high_risk_cnt"], high_cnt)
        c3.metric(T["med_risk_cnt"], med_cnt)
        c4.metric(T["low_risk_cnt"], low_cnt)

        st.progress(min(overall_score / 100.0, 1.0))
        st.divider()

        # Load clauses for verbatim text matching
        clause_text_map = {}
        try:
            all_c = get(f"queries/documents/{doc_id}/clauses?limit=200").get("clauses", [])
            for c in all_c:
                clause_text_map[c["clause_id"]] = c.get("text", "").strip()
        except Exception:
            pass

        all_risks = dashboard.get("clauses", [])

        if not all_risks:
            st.success(T["no_risks"])
        else:
            filter_levels = st.multiselect(
                T["filter_risk"],
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

                    st.markdown(f"<div class='verbatim-text-{r_level}'><strong>{T['exact_clause_text']}</strong><br>{html.escape(verbatim_txt if verbatim_txt else 'Text unavailable.')}</div>", unsafe_allow_html=True)
                    st.markdown(f"**{T['risk_assessment']}** {html.escape(reason)}")
                    st.markdown(f"<div class='impact-box'><strong>{T['user_impact']}</strong> {html.escape(impact_text)}</div>", unsafe_allow_html=True)
                    if mitigation:
                        st.markdown(f"<div class='mitigation-box'><strong>{T['mitigation_rec']}</strong> {html.escape(mitigation)}</div>", unsafe_allow_html=True)
                    st.caption(f"Flag Category: {flag}")
                    st.divider()

    except Exception as e:
        st.warning(f"Risk analysis data unavailable. Please complete document processing. ({e})")


# ==============================================================================
# TAB 3 — GROUNDED RAG CHATBOT
# ==============================================================================
with tab_chat:
    st.markdown(f"<div class='section-head'>{T['chat_head']}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:#64748B; font-size:0.87rem;'>"
        f"{T['chat_sub']}"
        f"</p>",
        unsafe_allow_html=True,
    )

    # Load chat history
    if not st.session_state.chat_display:
        try:
            history = get(f"queries/documents/{doc_id}/chat-history")
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
                st.markdown(f"**{T['cited_provisions']}**")
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
        st.markdown(f"**{T['suggested_questions']}**")
        rec_cols = st.columns(3)
        with rec_cols[0]:
            if st.button(T["q1"], use_container_width=True):
                st.session_state._quick_q = T["q1"]
                st.rerun()
        with rec_cols[1]:
            if st.button(T["q2"], use_container_width=True):
                st.session_state._quick_q = T["q2"]
                st.rerun()
        with rec_cols[2]:
            if st.button(T["q3"], use_container_width=True):
                st.session_state._quick_q = T["q3"]
                st.rerun()

    quick_q = st.session_state.pop("_quick_q", None)
    user_input = st.chat_input(T["chat_placeholder"])

    query_to_run = quick_q or user_input

    if query_to_run:
        with st.chat_message("user"):
            st.markdown(query_to_run)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing document provisions and formulating answer..."):
                try:
                    res = post(
                        f"commands/documents/{doc_id}/chat",
                        json_payload={"query": query_to_run, "top_k": 4},
                    )
                    answer_text = res.get("answer", "")
                    citations = res.get("citations", [])

                    st.markdown(answer_text)

                    if citations:
                        st.markdown(f"**{T['cited_provisions']}**")
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
                    history = get(f"queries/documents/{doc_id}/chat-history")
                    st.session_state.chat_display = history.get("messages", [])
                    st.rerun()

                except Exception as e:
                    st.error(f"Inquiry query failed: {e}")
