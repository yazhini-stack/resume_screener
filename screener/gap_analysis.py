"""Candidate gap analysis and actionable resume improvement recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from screener.jd_parser import JobDescriptionProfile
from screener.matcher import MatchBreakdown
from screener.sections import ResumeProfile


@dataclass
class ImprovementSuggestion:
    """Actionable recommendation for the job seeker."""
    category: str  # 'Critical Skills', 'Experience & Impact', 'Formatting & ATS', 'Education'
    title: str
    description: str
    priority: str  # 'High', 'Medium', 'Low'


@dataclass
class GapAnalysisReport:
    """Full gap analysis summary for a candidate."""
    candidate_name: str
    target_role: str
    overall_match_percentage: float
    matched_skills: List[str]
    missing_required_skills: List[str]
    missing_preferred_skills: List[str]
    additional_skills: List[str]
    experience_gap_years: float  # required - actual (positive means deficit)
    suggestions: List[ImprovementSuggestion] = field(default_factory=list)


def generate_gap_analysis(
    resume: ResumeProfile,
    jd: JobDescriptionProfile,
    breakdown: MatchBreakdown,
) -> GapAnalysisReport:
    """Analyze discrepancies between candidate profile and job requirements and produce advice."""
    suggestions: List[ImprovementSuggestion] = []

    # 1. Missing Required Skills Suggestions
    if breakdown.missing_required_skills:
        top_missing = breakdown.missing_required_skills[:6]
        missing_str = ", ".join(f"**{s}**" for s in top_missing)
        suggestions.append(
            ImprovementSuggestion(
                category="Critical Skills",
                title="Incorporate Essential Required Skills",
                description=(
                    f"The job posting explicitly lists {missing_str} as required qualifications. "
                    "If you have hands-on experience with these tools, explicitly integrate them "
                    "into your Skills section and describe concrete tasks in your Experience bullets."
                ),
                priority="High",
            )
        )

    # 2. Missing Preferred Skills
    if breakdown.missing_preferred_skills:
        top_pref = breakdown.missing_preferred_skills[:4]
        pref_str = ", ".join(f"**{s}**" for s in top_pref)
        suggestions.append(
            ImprovementSuggestion(
                category="Critical Skills",
                title="Highlight Bonus / Preferred Competencies",
                description=(
                    f"Adding experience with preferred skills ({pref_str}) can set you apart "
                    "from other candidates. Mention any relevant side projects, certifications, or self-learning."
                ),
                priority="Medium",
            )
        )

    # 3. Experience Gap Suggestions
    exp_gap = round(jd.min_experience_years - resume.total_experience_years, 1)
    if exp_gap > 0.5:
        suggestions.append(
            ImprovementSuggestion(
                category="Experience & Impact",
                title="Address the Experience Requirement Gap",
                description=(
                    f"The posting seeks {jd.min_experience_years:.0f}+ years of experience, while your "
                    f"resume indicates approximately {resume.total_experience_years:.1f} years. "
                    "Frame your experience around advanced project outcomes, rapid velocity, and end-to-end "
                    "ownership to compensate for the numerical gap."
                ),
                priority="High" if exp_gap > 2 else "Medium",
            )
        )

    # 4. Quantifiable Metrics & Business Impact
    if not resume.has_quantifiable_metrics or resume.metrics_count < 2:
        suggestions.append(
            ImprovementSuggestion(
                category="Experience & Impact",
                title="Add Quantifiable Results & Metrics",
                description=(
                    "Recruiters and ATS favor bullet points that follow the XYZ formula "
                    "(Accomplished [X], as measured by [Y], by doing [Z]). "
                    "Include concrete numbers, e.g., 'reduced API response times by 35%', "
                    "'scaled service to handle 50k DAU', or 'automated test suites saving 12 engineer-hours/week'."
                ),
                priority="High",
            )
        )

    # 5. Section and Header Formatting / ATS Readability
    missing_sections = []
    for sec in ["summary", "skills", "experience", "education"]:
        if not resume.sections.get(sec, "").strip():
            missing_sections.append(sec.title())

    if missing_sections:
        sec_str = ", ".join(missing_sections)
        suggestions.append(
            ImprovementSuggestion(
                category="Formatting & ATS",
                title=f"Add Standard Resume Section: {sec_str}",
                description=(
                    f"Your resume appears to lack a clear '{sec_str}' section header. "
                    "Applicant Tracking Systems rely on conventional headers to parse your work history accurately."
                ),
                priority="Medium",
            )
        )

    # 6. Education Requirement Check
    if jd.required_education and breakdown.education_score < 100.0:
        suggestions.append(
            ImprovementSuggestion(
                category="Education",
                title="Clarify Academic Credentials",
                description=(
                    f"This position lists a requirement for a {jd.required_education}. Ensure your degree "
                    "major and university name are clearly formatted in an 'Education' section, or highlight "
                    "equivalent industry experience/certifications."
                ),
                priority="Low",
            )
        )

    # 7. Semantic & Keyword Density
    if breakdown.semantic_score < 60.0:
        suggestions.append(
            ImprovementSuggestion(
                category="Formatting & ATS",
                title="Tailor Professional Summary to the Job Description",
                description=(
                    "Your overall vocabulary alignment with the job description is modest. "
                    "Mirror key industry terms and methodologies from the posting in your opening summary statement."
                ),
                priority="Medium",
            )
        )

    return GapAnalysisReport(
        candidate_name=resume.name,
        target_role=jd.title,
        overall_match_percentage=breakdown.overall_score,
        matched_skills=breakdown.matched_skills,
        missing_required_skills=breakdown.missing_required_skills,
        missing_preferred_skills=breakdown.missing_preferred_skills,
        additional_skills=breakdown.additional_skills,
        experience_gap_years=max(exp_gap, 0.0),
        suggestions=suggestions,
    )
