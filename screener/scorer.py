"""Overall match scoring, weight profiles, and candidate ranking logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from screener.jd_parser import JobDescriptionProfile
from screener.matcher import MatchBreakdown, ResumeMatcher
from screener.sections import ResumeProfile


@dataclass
class ScreeningResult:
    """Complete screening result for a candidate against a job description."""
    candidate_name: str
    filename: str
    overall_score: float
    rating_label: str  # 'Excellent Match', 'Strong Match', 'Moderate Match', 'Low Match'
    breakdown: MatchBreakdown
    resume_profile: ResumeProfile
    jd_profile: JobDescriptionProfile
    top_matched_skills: List[str] = field(default_factory=list)
    top_missing_skills: List[str] = field(default_factory=list)


WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "Balanced (Recommended)": {
        "skills": 0.45,
        "experience": 0.25,
        "education": 0.10,
        "semantic": 0.20,
    },
    "Skills-Heavy": {
        "skills": 0.60,
        "experience": 0.15,
        "education": 0.05,
        "semantic": 0.20,
    },
    "Experience-Centric": {
        "skills": 0.35,
        "experience": 0.45,
        "education": 0.05,
        "semantic": 0.15,
    },
    "Academic / Degree-Focused": {
        "skills": 0.35,
        "experience": 0.20,
        "education": 0.30,
        "semantic": 0.15,
    },
}


def get_match_rating_label(score: float) -> str:
    """Return descriptive rating label based on percentage score."""
    if score >= 85.0:
        return "Excellent Match"
    elif score >= 70.0:
        return "Strong Match"
    elif score >= 55.0:
        return "Moderate Match"
    else:
        return "Low Match"


class ResumeScorer:
    """Coordinates matching, scoring, and candidate ranking."""

    def __init__(self, matcher: Optional[ResumeMatcher] = None):
        self.matcher = matcher or ResumeMatcher()

    def score_single(
        self,
        resume: ResumeProfile,
        jd: JobDescriptionProfile,
        filename: str = "resume.pdf",
        weights: Optional[Dict[str, float]] = None,
    ) -> ScreeningResult:
        """Screen and score a single resume against a job description."""
        breakdown = self.matcher.match(resume, jd, weights=weights)
        label = get_match_rating_label(breakdown.overall_score)

        return ScreeningResult(
            candidate_name=resume.name,
            filename=filename,
            overall_score=breakdown.overall_score,
            rating_label=label,
            breakdown=breakdown,
            resume_profile=resume,
            jd_profile=jd,
            top_matched_skills=breakdown.matched_skills[:8],
            top_missing_skills=breakdown.missing_required_skills[:8],
        )

    def rank_candidates(
        self,
        results: List[ScreeningResult],
        min_experience_years: float = 0.0,
        required_must_have_skills: Optional[List[str]] = None,
        query: str = "",
    ) -> List[ScreeningResult]:
        """Filter and rank candidate screening results.

        Args:
            results: List of candidate screening results.
            min_experience_years: Minimum candidate years of experience filter.
            required_must_have_skills: Mandatory skills candidate must possess.
            query: Name or skill search keyword.

        Returns:
            Ranked and filtered list of ScreeningResults.
        """
        filtered: List[ScreeningResult] = []
        must_haves = set(required_must_have_skills or [])
        clean_query = query.strip().lower()

        for res in results:
            # 1. Experience filter
            if res.resume_profile.total_experience_years < min_experience_years:
                continue

            # 2. Must-have skill filter
            if must_haves:
                cand_skills = set(res.breakdown.matched_skills + res.breakdown.additional_skills)
                if not must_haves.issubset(cand_skills):
                    continue

            # 3. Query filter
            if clean_query:
                name_match = clean_query in res.candidate_name.lower()
                file_match = clean_query in res.filename.lower()
                skill_match = any(clean_query in s.lower() for s in res.breakdown.matched_skills)
                if not (name_match or file_match or skill_match):
                    continue

            filtered.append(res)

        # Sort descending by overall score, then by experience years
        filtered.sort(
            key=lambda x: (x.overall_score, x.resume_profile.total_experience_years),
            reverse=True
        )

        return filtered
