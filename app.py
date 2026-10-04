"""Streamlit Web Application for resume_screener.

Features:
- Recruiter Mode: Bulk resume ranking, skill filters, experience filters, and shortlist PDF export.
- Candidate Mode: Deep-dive single resume match, score gauge, category radar, gap analysis, actionable advice, and improvement report PDF export.
- History View: SQLite persistence inspection and export.
- Taxonomy Explorer: Interactive browser for tech, business, and soft skills.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from screener.database import Database
from screener.gap_analysis import generate_gap_analysis
from screener.jd_parser import EmptyJobDescriptionError, JobDescriptionParser, JobDescriptionProfile
from screener.logger import get_logger
from screener.matcher import MatchBreakdown, ResumeMatcher
from screener.parser import (
    CorruptedResumeError,
    ResumeParserError,
    ScannedResumeError,
    UnsupportedFormatError,
    parse_resume,
)
from screener.report import generate_candidate_report, generate_recruiter_report
from screener.scorer import WEIGHT_PROFILES, ResumeScorer, ScreeningResult
from screener.sections import ResumeProfile, parse_resume_to_profile
from screener.skills_extractor import SkillsExtractor

logger = get_logger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_RESUMES_DIR = DATA_DIR / "sample_resumes"
SAMPLE_JD_PATH = DATA_DIR / "sample_job_description.txt"

# Page configuration
st.set_page_config(
    page_title="AI Resume Screener & Career Matcher",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- Custom Styling ---
st.markdown(
    """
    <style>
    /* Main container styling */
    .main .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }
    
    /* Headers & Typography */
    h1, h2, h3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-weight: 700;
    }
    
    .hero-container {
        background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 100%);
        color: white;
        padding: 24px 28px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
    }
    
    .hero-title {
        font-size: 28px;
        font-weight: 800;
        margin-bottom: 6px;
        color: #FFFFFF !important;
    }
    
    .hero-subtitle {
        font-size: 14px;
        color: #94A3B8;
        margin-bottom: 0;
    }
    
    /* Score card styling */
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }
    
    .metric-value {
        font-size: 26px;
        font-weight: 800;
        color: #1E3A8A;
    }
    
    .metric-label {
        font-size: 12px;
        font-weight: 600;
        color: #64748B;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Skill pills */
    .skill-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 16px;
        font-size: 12px;
        font-weight: 600;
        margin: 2px 4px 4px 0;
    }
    .skill-matched {
        background-color: #DCFCE7;
        color: #166534;
        border: 1px solid #86EFAC;
    }
    .skill-missing {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 1px solid #FCA5A5;
    }
    .skill-preferred {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FDE68A;
    }
    .skill-additional {
        background-color: #E0F2FE;
        color: #075985;
        border: 1px solid #BAE6FD;
    }

    /* Suggestion card */
    .suggestion-card {
        background: #FFFFFF;
        border-left: 4px solid #3B82F6;
        border-radius: 0 8px 8px 0;
        padding: 14px 18px;
        margin-bottom: 12px;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
    }
    .suggestion-high {
        border-left-color: #EF4444;
    }
    .suggestion-med {
        border-left-color: #F59E0B;
    }
    .suggestion-low {
        border-left-color: #3B82F6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_core_services():
    """Cache and load core NLP, taxonomy, matcher, and database services."""
    extractor = SkillsExtractor()
    jd_parser = JobDescriptionParser(extractor=extractor)
    matcher = ResumeMatcher(extractor=extractor)
    scorer = ResumeScorer(matcher=matcher)
    db = Database()
    return extractor, jd_parser, matcher, scorer, db


extractor, jd_parser, matcher, scorer, db = load_core_services()


# --- Plotly Visualization Helpers ---

def create_score_gauge(score: float, title: str = "Overall Match Score") -> go.Figure:
    """Create a Plotly Gauge chart for match percentage."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": title, "font": {"size": 18, "color": "#1E293B"}},
            number={"suffix": "%", "font": {"size": 36, "color": "#1E3A8A"}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#94A3B8"},
                "bar": {"color": "#2563EB", "thickness": 0.25},
                "bgcolor": "white",
                "borderwidth": 1,
                "bordercolor": "#E2E8F0",
                "steps": [
                    {"range": [0, 50], "color": "#FEE2E2"},
                    {"range": [50, 75], "color": "#FEF3C7"},
                    {"range": [75, 100], "color": "#DCFCE7"},
                ],
                "threshold": {
                    "line": {"color": "#047857", "width": 4},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        )
    )
    fig.update_layout(
        height=240,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "sans-serif"},
    )
    return fig


def create_radar_chart(breakdown: MatchBreakdown) -> go.Figure:
    """Create a category radar chart of scoring metrics."""
    categories = [
        "Skills Match",
        "Experience Match",
        "Education Match",
        "Semantic Fit",
    ]
    scores = [
        breakdown.skills_score,
        breakdown.experience_score,
        breakdown.education_score,
        breakdown.semantic_score,
    ]

    # Close the radar loop
    categories.append(categories[0])
    scores.append(scores[0])

    fig = go.Figure(
        data=go.Scatterpolar(
            r=scores,
            theta=categories,
            fill="toself",
            fillcolor="rgba(37, 99, 235, 0.25)",
            line={"color": "#2563EB", "width": 2},
            marker={"size": 6, "color": "#1E3A8A"},
        )
    )
    fig.update_layout(
        polar={
            "radialaxis": {"visible": True, "range": [0, 100], "tickfont": {"size": 9}},
            "angularaxis": {"tickfont": {"size": 11, "color": "#1E293B"}},
        },
        showlegend=False,
        height=260,
        margin={"l": 40, "r": 40, "t": 25, "b": 25},
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def create_skills_distribution_bar(
    matched_count: int,
    missing_req_count: int,
    missing_pref_count: int,
    additional_count: int,
) -> go.Figure:
    """Create a breakdown horizontal stacked bar chart of skill distribution."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Skills"],
        x=[matched_count],
        name="Matched",
        orientation="h",
        marker={"color": "#22C55E"},
        text=[f"{matched_count} Matched"],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Skills"],
        x=[missing_req_count],
        name="Missing (Required)",
        orientation="h",
        marker={"color": "#EF4444"},
        text=[f"{missing_req_count} Missing Req"],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Skills"],
        x=[missing_pref_count],
        name="Missing (Preferred)",
        orientation="h",
        marker={"color": "#F59E0B"},
        text=[f"{missing_pref_count} Missing Pref"],
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Skills"],
        x=[additional_count],
        name="Candidate Extra",
        orientation="h",
        marker={"color": "#38BDF8"},
        text=[f"{additional_count} Extra"],
        textposition="inside",
    ))

    fig.update_layout(
        barmode="stack",
        height=140,
        margin={"l": 10, "r": 10, "t": 20, "b": 20},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.05, "xanchor": "center", "x": 0.5},
        xaxis={"visible": False},
        yaxis={"visible": False},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# --- Header Banner ---
st.markdown(
    """
    <div class="hero-container">
        <div class="hero-title">📄 AI Resume Screener & Talent Matcher</div>
        <div class="hero-subtitle">Production-grade automated resume screening, taxonomy-based skill gap analysis, and ATS optimization reports.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Mode Selector
app_mode = st.sidebar.radio(
    "Navigation Mode",
    [
        "👥 Recruiter Mode (Bulk Screening)",
        "🎯 Candidate Mode (Gap Analysis)",
        "📜 Screening History",
        "📚 Skills Taxonomy Explorer",
    ],
    index=0,
)


# ==============================================================================
# MODE 1: RECRUITER MODE
# ==============================================================================
if app_mode == "👥 Recruiter Mode (Bulk Screening)":
    st.subheader("👥 Recruiter Mode: Bulk Resume Screening & Ranking")
    st.markdown(
        "Upload a job description and candidate resumes to rank applicants by technical fit, experience, and required skills."
    )

    col_jd, col_res = st.columns([1, 1], gap="medium")

    with col_jd:
        st.markdown("### 1. Job Description")
        jd_input_method = st.radio(
            "Job Description Source",
            ["Paste / Type Text", "Upload File (PDF/DOCX/TXT)", "Use Preloaded Sample JD"],
            horizontal=True,
        )

        jd_text = ""
        if jd_input_method == "Paste / Type Text":
            jd_text = st.text_area(
                "Paste Job Posting",
                height=260,
                placeholder="Paste the full job description here (responsibilities, requirements, qualifications)...",
            )
        elif jd_input_method == "Upload File (PDF/DOCX/TXT)":
            jd_file = st.file_uploader(
                "Upload JD Document",
                type=["pdf", "docx", "txt"],
                key="recruiter_jd_upload",
            )
            if jd_file:
                try:
                    jd_text = parse_resume(jd_file, filename=jd_file.name)
                    st.success(f"Loaded '{jd_file.name}' ({len(jd_text.split())} words)")
                except Exception as e:
                    st.error(f"Error reading JD file: {e}")
        else:
            if SAMPLE_JD_PATH.exists():
                jd_text = SAMPLE_JD_PATH.read_text(encoding="utf-8")
                st.info("Loaded preloaded sample: Senior Python & Cloud Backend Engineer")
                with st.expander("View Sample JD Content"):
                    st.text(jd_text)

    with col_res:
        st.markdown("### 2. Candidate Resumes")
        res_input_method = st.radio(
            "Resumes Source",
            ["Upload Multiple Resumes (PDF/DOCX/TXT)", "Use Preloaded Sample Resumes"],
            horizontal=True,
        )

        uploaded_files = []
        if res_input_method == "Upload Multiple Resumes (PDF/DOCX/TXT)":
            uploaded_files = st.file_uploader(
                "Upload Resumes (Select one or more)",
                type=["pdf", "docx", "txt"],
                accept_multiple_files=True,
                key="recruiter_resumes_upload",
            )
            if uploaded_files:
                st.caption(f"{len(uploaded_files)} files selected.")
        else:
            st.info("Uses 3 realistic preloaded sample candidates (PDF, DOCX, TXT):")
            st.markdown("- **Alex Morgan**: Senior Python / Cloud Engineer (PDF)")
            st.markdown("- **Dr. Elena Rostova**: Data Scientist & ML Engineer (DOCX)")
            st.markdown("- **Sam Rivera**: Junior Frontend Developer (TXT)")

    # Scoring Preferences
    with st.expander("⚙️ Advanced Scoring Weights & Settings", expanded=False):
        weight_choice = st.selectbox(
            "Scoring Weight Profile",
            list(WEIGHT_PROFILES.keys()),
            index=0,
        )
        selected_weights = WEIGHT_PROFILES[weight_choice]
        st.caption(
            f"Weights: Skills ({selected_weights['skills']*100:.0f}%), "
            f"Experience ({selected_weights['experience']*100:.0f}%), "
            f"Education ({selected_weights['education']*100:.0f}%), "
            f"Semantic Text Similarity ({selected_weights['semantic']*100:.0f}%)"
        )

    # Action Button
    screen_btn = st.button("🚀 Screen & Rank Candidates", type="primary", use_container_width=True)

    if screen_btn:
        if not jd_text or len(jd_text.strip()) < 20:
            st.error("Please provide a valid, detailed job description before screening.")
            st.stop()

        # Parse JD
        try:
            with st.spinner("Analyzing Job Description requirements..."):
                parsed_jd = jd_parser.parse(jd_text)
                jd_db_id = db.save_job_description(
                    title=parsed_jd.title,
                    raw_text=parsed_jd.raw_text,
                    min_experience_years=parsed_jd.min_experience_years,
                    required_skills=parsed_jd.required_skills,
                    preferred_skills=parsed_jd.preferred_skills,
                )
        except EmptyJobDescriptionError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Failed to parse job description: {e}")
            st.stop()

        # Gather Resumes
        resumes_to_process = []
        if res_input_method == "Use Preloaded Sample Resumes":
            sample_files = [
                ("alex_morgan_senior_python.pdf", SAMPLE_RESUMES_DIR / "alex_morgan_senior_python.pdf"),
                ("elena_rostova_data_scientist.docx", SAMPLE_RESUMES_DIR / "elena_rostova_data_scientist.docx"),
                ("sam_rivera_junior_frontend.txt", SAMPLE_RESUMES_DIR / "sam_rivera_junior_frontend.txt"),
            ]
            for fn, path in sample_files:
                if path.exists():
                    resumes_to_process.append((fn, path.read_bytes()))
        else:
            for uf in uploaded_files:
                resumes_to_process.append((uf.name, uf.read()))

        if not resumes_to_process:
            st.warning("Please upload candidate resumes or select the preloaded sample resumes.")
            st.stop()

        screening_results: List[ScreeningResult] = []
        parsing_errors = []

        progress_bar = st.progress(0, text="Parsing and scoring resumes...")
        for i, (fname, file_bytes) in enumerate(resumes_to_process):
            progress_bar.progress((i + 1) / len(resumes_to_process), text=f"Processing {fname}...")
            try:
                raw_text = parse_resume(file_bytes, filename=fname)
                profile = parse_resume_to_profile(raw_text)
                res = scorer.score_single(profile, parsed_jd, filename=fname, weights=selected_weights)
                screening_results.append(res)

                # Persist to database
                res_db_id = db.save_resume(
                    filename=fname,
                    candidate_name=profile.name,
                    email=profile.email,
                    phone=profile.phone,
                    raw_text=raw_text,
                    experience_years=profile.total_experience_years,
                    skills=res.breakdown.matched_skills + res.breakdown.additional_skills,
                    degrees=profile.degrees,
                )
                db.save_match_result(
                    jd_id=jd_db_id,
                    resume_id=res_db_id,
                    mode="recruiter",
                    overall_score=res.overall_score,
                    rating_label=res.rating_label,
                    breakdown_dict={
                        "skills_score": res.breakdown.skills_score,
                        "experience_score": res.breakdown.experience_score,
                        "education_score": res.breakdown.education_score,
                        "semantic_score": res.breakdown.semantic_score,
                        "matched_skills": res.breakdown.matched_skills,
                        "missing_required_skills": res.breakdown.missing_required_skills,
                    },
                )
            except ScannedResumeError as e:
                parsing_errors.append((fname, f"Scanned/Image-Only Resume: {e}"))
            except CorruptedResumeError as e:
                parsing_errors.append((fname, f"Corrupted File: {e}"))
            except UnsupportedFormatError as e:
                parsing_errors.append((fname, f"Unsupported Format: {e}"))
            except Exception as e:
                logger.error(f"Unexpected error processing {fname}: {e}")
                parsing_errors.append((fname, f"Extraction Error: {e}"))

        progress_bar.empty()

        # Store in session state for dynamic filtering without re-running parsing
        st.session_state["recruiter_results"] = screening_results
        st.session_state["recruiter_jd"] = parsed_jd
        st.session_state["recruiter_errors"] = parsing_errors

    # Render Results if available in session state
    if "recruiter_results" in st.session_state and st.session_state["recruiter_results"]:
        results: List[ScreeningResult] = st.session_state["recruiter_results"]
        parsed_jd: JobDescriptionProfile = st.session_state["recruiter_jd"]
        errors = st.session_state.get("recruiter_errors", [])

        if errors:
            with st.expander(f"⚠️ {len(errors)} File Warnings / Errors Encountered", expanded=False):
                for fn, err in errors:
                    st.warning(f"**{fn}**: {err}")

        st.markdown("---")
        st.subheader(f"📊 Screening Results for: {parsed_jd.title}")

        # Top Summary KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(
                f"""<div class="metric-card"><div class="metric-value">{len(results)}</div><div class="metric-label">Screened Candidates</div></div>""",
                unsafe_allow_html=True,
            )
        with k2:
            avg_score = sum(r.overall_score for r in results) / len(results)
            st.markdown(
                f"""<div class="metric-card"><div class="metric-value">{avg_score:.1f}%</div><div class="metric-label">Average Match Score</div></div>""",
                unsafe_allow_html=True,
            )
        with k3:
            top_cand = sorted(results, key=lambda x: x.overall_score, reverse=True)[0]
            st.markdown(
                f"""<div class="metric-card"><div class="metric-value">{top_cand.overall_score:.1f}%</div><div class="metric-label">Top Score ({top_cand.candidate_name.split()[0]})</div></div>""",
                unsafe_allow_html=True,
            )
        with k4:
            req_skill_count = len(parsed_jd.required_skills)
            st.markdown(
                f"""<div class="metric-card"><div class="metric-value">{req_skill_count}</div><div class="metric-label">Required Skills in JD</div></div>""",
                unsafe_allow_html=True,
            )

        st.markdown("<br/>", unsafe_allow_html=True)

        # Filters Row
        f1, f2, f3 = st.columns([1, 1.2, 1.5])
        with f1:
            min_exp = st.slider(
                "Filter: Min Experience (Years)",
                min_value=0.0,
                max_value=15.0,
                value=0.0,
                step=0.5,
            )
        with f2:
            all_skills_pool = sorted(list(set(
                s for r in results for s in (r.breakdown.matched_skills + r.breakdown.additional_skills)
            )))
            must_have_skills = st.multiselect(
                "Filter: Mandatory Skills Present",
                options=all_skills_pool,
                default=[],
            )
        with f3:
            query = st.text_input("Filter: Search Candidate Name or Skill", placeholder="e.g. Python, Elena...")

        filtered_results = scorer.rank_candidates(
            results,
            min_experience_years=min_exp,
            required_must_have_skills=must_have_skills,
            query=query,
        )

        st.markdown(f"**Showing {len(filtered_results)} of {len(results)} candidates:**")

        # Leaderboard Table View
        table_rows = []
        for rank, r in enumerate(filtered_results, start=1):
            table_rows.append({
                "Rank": f"#{rank}",
                "Candidate Name": r.candidate_name,
                "File": r.filename,
                "Overall Match": f"{r.overall_score:.1f}%",
                "Rating": r.rating_label,
                "Experience": f"{r.resume_profile.total_experience_years:.1f} yrs",
                "Skills Score": f"{r.breakdown.skills_score:.1f}%",
                "Degrees": ", ".join(r.resume_profile.degrees) or "Not specified",
                "Top Matched Skills": ", ".join(r.top_matched_skills[:4]),
                "Missing Critical Skills": ", ".join(r.top_missing_skills[:3]) or "None",
            })

        df_results = pd.DataFrame(table_rows)
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        # Export Recruiter PDF Shortlist
        st.markdown("#### 📥 Export Recruiter Shortlist Report")
        try:
            pdf_bytes = generate_recruiter_report(filtered_results, job_title=parsed_jd.title)
            st.download_button(
                label="📄 Download Shortlist PDF Report",
                data=pdf_bytes,
                file_name=f"recruiter_shortlist_{parsed_jd.title.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                type="secondary",
            )
        except Exception as e:
            st.error(f"Error generating PDF report: {e}")

        # Individual Candidate Drill-Down Expanders
        st.markdown("---")
        st.subheader("🔍 In-Depth Candidate Profiles")
        for rank, r in enumerate(filtered_results, start=1):
            with st.expander(f"#{rank} - {r.candidate_name} ({r.overall_score:.1f}% - {r.rating_label}) | {r.filename}"):
                c1, c2 = st.columns([1, 1])

                with c1:
                    st.markdown("**Contact & Education:**")
                    st.write(f"- 📧 Email: `{r.resume_profile.email or 'N/A'}`")
                    st.write(f"- 📞 Phone: `{r.resume_profile.phone or 'N/A'}`")
                    st.write(f"- 🎓 Degrees: {', '.join(r.resume_profile.degrees) or 'Not explicitly listed'}")
                    st.write(f"- ⏱️ Total Experience: **{r.resume_profile.total_experience_years:.1f} years**")
                    if r.resume_profile.job_titles:
                        st.write(f"- 💼 Detected Titles: {', '.join(r.resume_profile.job_titles[:4])}")

                    st.markdown("**Score Component Breakdown:**")
                    b_df = pd.DataFrame({
                        "Dimension": ["Skills Match", "Experience Match", "Education Match", "Semantic Alignment"],
                        "Score": [
                            f"{r.breakdown.skills_score:.1f}%",
                            f"{r.breakdown.experience_score:.1f}%",
                            f"{r.breakdown.education_score:.1f}%",
                            f"{r.breakdown.semantic_score:.1f}%",
                        ],
                    })
                    st.table(b_df)

                with c2:
                    st.markdown("**Skills Breakdown:**")
                    st.markdown("✅ **Matched Skills:**")
                    if r.breakdown.matched_skills:
                        matched_html = "".join([f'<span class="skill-pill skill-matched">{s}</span>' for s in r.breakdown.matched_skills])
                        st.markdown(matched_html, unsafe_allow_html=True)
                    else:
                        st.caption("None matched")

                    st.markdown("<br/>❌ **Missing Required Skills:**", unsafe_allow_html=True)
                    if r.breakdown.missing_required_skills:
                        missing_html = "".join([f'<span class="skill-pill skill-missing">{s}</span>' for s in r.breakdown.missing_required_skills])
                        st.markdown(missing_html, unsafe_allow_html=True)
                    else:
                        st.caption("All required skills satisfied!")

                    if r.breakdown.additional_skills:
                        st.markdown("<br/>💡 **Other Relevant Skills:**", unsafe_allow_html=True)
                        extra_html = "".join([f'<span class="skill-pill skill-additional">{s}</span>' for s in r.breakdown.additional_skills[:12]])
                        st.markdown(extra_html, unsafe_allow_html=True)

                st.markdown("<br/>", unsafe_allow_html=True)
                # Plot radar
                radar_fig = create_radar_chart(r.breakdown)
                st.plotly_chart(radar_fig, use_container_width=True)


# ==============================================================================
# MODE 2: CANDIDATE MODE
# ==============================================================================
elif app_mode == "🎯 Candidate Mode (Gap Analysis)":
    st.subheader("🎯 Candidate Mode: Match Analysis & Actionable Resume Improvement")
    st.markdown(
        "Upload your resume against a target job posting to get an instant match score, identify skill gaps, and receive concrete suggestions to boost your interview chances."
    )

    c_left, c_right = st.columns([1, 1], gap="medium")

    with c_left:
        st.markdown("### 1. Your Resume")
        cand_res_src = st.radio(
            "Resume Source",
            ["Upload Resume (PDF/DOCX/TXT)", "Use Sample: Alex Morgan (Senior)", "Use Sample: Sam Rivera (Junior)"],
            key="cand_res_src",
        )

        cand_resume_bytes: Optional[bytes] = None
        cand_resume_name = "resume.pdf"

        if cand_res_src == "Upload Resume (PDF/DOCX/TXT)":
            uploaded_res = st.file_uploader(
                "Upload Resume File",
                type=["pdf", "docx", "txt"],
                key="cand_single_upload",
            )
            if uploaded_res:
                cand_resume_bytes = uploaded_res.read()
                cand_resume_name = uploaded_res.name
        elif "Alex Morgan" in cand_res_src:
            path = SAMPLE_RESUMES_DIR / "alex_morgan_senior_python.pdf"
            if path.exists():
                cand_resume_bytes = path.read_bytes()
                cand_resume_name = "alex_morgan_senior_python.pdf"
                st.info("Loaded Alex Morgan's Senior Python & Cloud Resume (PDF)")
        else:
            path = SAMPLE_RESUMES_DIR / "sam_rivera_junior_frontend.txt"
            if path.exists():
                cand_resume_bytes = path.read_bytes()
                cand_resume_name = "sam_rivera_junior_frontend.txt"
                st.info("Loaded Sam Rivera's Junior Frontend Resume (TXT)")

    with c_right:
        st.markdown("### 2. Target Job Description")
        cand_jd_src = st.radio(
            "Job Posting Source",
            ["Paste Job Description", "Upload Job File (PDF/DOCX/TXT)", "Use Preloaded Sample Job"],
            key="cand_jd_src",
        )

        cand_jd_text = ""
        if cand_jd_src == "Paste Job Description":
            cand_jd_text = st.text_area(
                "Paste Target Job Posting",
                height=260,
                placeholder="Paste the full job posting text here...",
            )
        elif cand_jd_src == "Upload Job File (PDF/DOCX/TXT)":
            uploaded_jd = st.file_uploader(
                "Upload Job Document",
                type=["pdf", "docx", "txt"],
                key="cand_jd_upload",
            )
            if uploaded_jd:
                try:
                    cand_jd_text = parse_resume(uploaded_jd, filename=uploaded_jd.name)
                except Exception as e:
                    st.error(f"Error reading JD: {e}")
        else:
            if SAMPLE_JD_PATH.exists():
                cand_jd_text = SAMPLE_JD_PATH.read_text(encoding="utf-8")
                st.info("Loaded preloaded sample: Senior Python & Cloud Backend Engineer")

    cand_analyze_btn = st.button("🔍 Analyze Resume Match & Find Gaps", type="primary", use_container_width=True)

    if cand_analyze_btn:
        if not cand_resume_bytes:
            st.error("Please provide a resume to analyze.")
            st.stop()
        if not cand_jd_text or len(cand_jd_text.strip()) < 20:
            st.error("Please provide a target job description.")
            st.stop()

        try:
            with st.spinner("Extracting resume profile and matching against job description..."):
                raw_resume = parse_resume(cand_resume_bytes, filename=cand_resume_name)
                resume_profile = parse_resume_to_profile(raw_resume)
                parsed_jd = jd_parser.parse(cand_jd_text)
                breakdown = matcher.match(resume_profile, parsed_jd)
                gap_report = generate_gap_analysis(resume_profile, parsed_jd, breakdown)

                # Persist to database
                jd_id = db.save_job_description(
                    parsed_jd.title,
                    parsed_jd.raw_text,
                    parsed_jd.min_experience_years,
                    parsed_jd.required_skills,
                    parsed_jd.preferred_skills,
                )
                res_id = db.save_resume(
                    cand_resume_name,
                    resume_profile.name,
                    resume_profile.email,
                    resume_profile.phone,
                    raw_resume,
                    resume_profile.total_experience_years,
                    breakdown.matched_skills + breakdown.additional_skills,
                    resume_profile.degrees,
                )
                db.save_match_result(
                    jd_id,
                    res_id,
                    mode="candidate",
                    overall_score=breakdown.overall_score,
                    rating_label="Candidate Analysis",
                    breakdown_dict={
                        "skills_score": breakdown.skills_score,
                        "experience_score": breakdown.experience_score,
                        "education_score": breakdown.education_score,
                        "semantic_score": breakdown.semantic_score,
                    },
                )

                st.session_state["candidate_gap_report"] = gap_report
                st.session_state["candidate_breakdown"] = breakdown
                st.session_state["candidate_profile"] = resume_profile
                st.session_state["candidate_jd"] = parsed_jd
        except ScannedResumeError as e:
            st.error(f"❌ Scanned or Image-only Resume detected: {e}")
            st.stop()
        except CorruptedResumeError as e:
            st.error(f"❌ Corrupted File: {e}")
            st.stop()
        except EmptyJobDescriptionError as e:
            st.error(f"❌ Empty Job Description: {e}")
            st.stop()
        except Exception as e:
            st.error(f"Analysis Error: {e}")
            logger.error(f"Candidate mode error: {e}", exc_info=True)
            st.stop()

    # Display Analysis
    if "candidate_gap_report" in st.session_state:
        gap_report: GapAnalysisReport = st.session_state["candidate_gap_report"]
        breakdown: MatchBreakdown = st.session_state["candidate_breakdown"]
        resume_profile: ResumeProfile = st.session_state["candidate_profile"]
        parsed_jd: JobDescriptionProfile = st.session_state["candidate_jd"]

        st.markdown("---")
        st.subheader(f"📊 Match Analysis for {gap_report.candidate_name} → {gap_report.target_role}")

        # Top Visualizations Row
        v1, v2 = st.columns([1, 1])
        with v1:
            gauge_fig = create_score_gauge(breakdown.overall_score, title="Overall Match Score")
            st.plotly_chart(gauge_fig, use_container_width=True)

        with v2:
            radar_fig = create_radar_chart(breakdown)
            st.plotly_chart(radar_fig, use_container_width=True)

        # Skills distribution bar
        st.markdown("#### 🧩 Skills Breakdown & Overlap")
        dist_fig = create_skills_distribution_bar(
            len(gap_report.matched_skills),
            len(gap_report.missing_required_skills),
            len(gap_report.missing_preferred_skills),
            len(gap_report.additional_skills),
        )
        st.plotly_chart(dist_fig, use_container_width=True)

        # Categorized Skill Pills
        p1, p2 = st.columns(2)
        with p1:
            st.markdown("✅ **Matched Skills (Present in both):**")
            if gap_report.matched_skills:
                pills = "".join([f'<span class="skill-pill skill-matched">{s}</span>' for s in gap_report.matched_skills])
                st.markdown(pills, unsafe_allow_html=True)
            else:
                st.caption("No matching skills found.")

            st.markdown("<br/>💡 **Extra Skills on Your Resume:**", unsafe_allow_html=True)
            if gap_report.additional_skills:
                extra_pills = "".join([f'<span class="skill-pill skill-additional">{s}</span>' for s in gap_report.additional_skills[:16]])
                st.markdown(extra_pills, unsafe_allow_html=True)
            else:
                st.caption("None.")

        with p2:
            st.markdown("❌ **Missing Required Skills (From JD):**")
            if gap_report.missing_required_skills:
                missing_pills = "".join([f'<span class="skill-pill skill-missing">{s}</span>' for s in gap_report.missing_required_skills])
                st.markdown(missing_pills, unsafe_allow_html=True)
            else:
                st.success("You satisfy all required skills listed in the job posting!")

            if gap_report.missing_preferred_skills:
                st.markdown("<br/>⭐ **Missing Preferred / Bonus Skills:**", unsafe_allow_html=True)
                pref_pills = "".join([f'<span class="skill-pill skill-preferred">{s}</span>' for s in gap_report.missing_preferred_skills])
                st.markdown(pref_pills, unsafe_allow_html=True)

        # Concrete Improvement Suggestions
        st.markdown("---")
        st.subheader("💡 Actionable Resume Improvement Recommendations")
        st.markdown(
            "Prioritized enhancements based on ATS patterns, recruiter preferences, and gap analysis."
        )

        for sug in gap_report.suggestions:
            pri_class = (
                "suggestion-high" if sug.priority == "High"
                else ("suggestion-med" if sug.priority == "Medium" else "suggestion-low")
            )
            badge_color = "#DC2626" if sug.priority == "High" else ("#D97706" if sug.priority == "Medium" else "#2563EB")
            st.markdown(
                f"""
                <div class="suggestion-card {pri_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-weight: 700; font-size: 15px; color: #0F172A;">{sug.title}</span>
                        <span style="font-size: 11px; font-weight: 700; color: {badge_color}; text-transform: uppercase;">
                            {sug.priority} Priority • {sug.category}
                        </span>
                    </div>
                    <div style="font-size: 13.5px; color: #475569; line-height: 1.5;">
                        {sug.description}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Download Candidate PDF Report
        st.markdown("#### 📥 Export Candidate Improvement PDF Report")
        try:
            cand_pdf = generate_candidate_report(gap_report, breakdown)
            st.download_button(
                label="📄 Download My Personalized PDF Report",
                data=cand_pdf,
                file_name=f"resume_report_{gap_report.candidate_name.replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                type="primary",
            )
        except Exception as e:
            st.error(f"Error generating candidate PDF: {e}")


# ==============================================================================
# MODE 3: SCREENING HISTORY
# ==============================================================================
elif app_mode == "📜 Screening History":
    st.subheader("📜 Screening Database History")
    st.markdown("View all previously recorded screening sessions stored in local SQLite.")

    history_records = db.get_history(limit=100)

    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.write(f"Total stored records: **{len(history_records)}**")
    with col_h2:
        if st.button("🗑️ Clear All History", type="secondary"):
            db.clear_all_history()
            st.success("Database history cleared!")
            st.rerun()

    if not history_records:
        st.info("No screening history yet. Run a Recruiter or Candidate screening session first.")
    else:
        hist_table = []
        for r in history_records:
            hist_table.append({
                "Date": r.get("match_date", ""),
                "Mode": (r.get("mode") or "").capitalize(),
                "Candidate": r.get("candidate_name", "N/A"),
                "File": r.get("filename", "N/A"),
                "Target Role": r.get("job_title", "N/A"),
                "Match %": f"{r.get('overall_score', 0):.1f}%",
                "Rating": r.get("rating_label", ""),
                "Exp (Yrs)": f"{r.get('experience_years', 0):.1f}",
            })
        st.dataframe(pd.DataFrame(hist_table), use_container_width=True, hide_index=True)


# ==============================================================================
# MODE 4: SKILLS TAXONOMY EXPLORER
# ==============================================================================
elif app_mode == "📚 Skills Taxonomy Explorer":
    st.subheader("📚 Skills Taxonomy Explorer")
    st.markdown(
        f"Explore the editable skills taxonomy currently powering extraction ({len(extractor.all_canonical_skills)} canonical skills across {len(extractor.categories)} categories)."
    )

    cats = list(extractor.categories.keys())
    selected_cat = st.selectbox("Select Taxonomy Category", cats)

    if selected_cat:
        skills_in_cat = extractor.categories[selected_cat]
        st.markdown(f"### {selected_cat} ({len(skills_in_cat)} skills)")

        cat_rows = []
        for skill_name, aliases in skills_in_cat.items():
            cat_rows.append({
                "Canonical Skill": skill_name,
                "Aliases & Synonyms": ", ".join(aliases) if aliases else "(None)",
                "Total Aliases": len(aliases),
            })
        st.dataframe(pd.DataFrame(cat_rows), use_container_width=True, hide_index=True)

        st.caption(
            f"Taxonomy loaded from: `{extractor.taxonomy_path}`. "
            "You can add or update skills and aliases directly in this JSON file."
        )
