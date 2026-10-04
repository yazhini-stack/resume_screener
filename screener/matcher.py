"""Matcher module computing semantic similarity, skill overlap, experience, and education matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from screener.jd_parser import JobDescriptionProfile
from screener.logger import get_logger
from screener.sections import ResumeProfile
from screener.skills_extractor import SkillsExtractor

logger = get_logger(__name__)

DEGREE_HIERARCHY = {
    "Ph.D. / Doctorate": 4,
    "Master's Degree": 3,
    "Bachelor's Degree": 2,
    "Associate Degree": 1,
    None: 0,
}


@dataclass
class MatchBreakdown:
    """Detailed score breakdown and matched/missing components."""
    overall_score: float  # 0.0 to 100.0
    skills_score: float   # 0.0 to 100.0
    experience_score: float  # 0.0 to 100.0
    education_score: float   # 0.0 to 100.0
    semantic_score: float    # 0.0 to 100.0

    # Skill lists
    matched_skills: List[str] = field(default_factory=list)
    missing_required_skills: List[str] = field(default_factory=list)
    missing_preferred_skills: List[str] = field(default_factory=list)
    additional_skills: List[str] = field(default_factory=list)

    # Details
    candidate_experience_years: float = 0.0
    required_experience_years: float = 0.0
    candidate_degrees: List[str] = field(default_factory=list)
    required_education: Optional[str] = None
    category_coverage: Dict[str, float] = field(default_factory=dict)


class ResumeMatcher:
    """Evaluates how well a resume profile matches a job description."""

    def __init__(self, extractor: Optional[SkillsExtractor] = None):
        self.extractor = extractor or SkillsExtractor()

    def compute_semantic_similarity(self, resume_text: str, jd_text: str) -> float:
        """Calculate TF-IDF n-gram cosine similarity between resume and JD."""
        if not resume_text.strip() or not jd_text.strip():
            return 0.0

        try:
            vectorizer = TfidfVectorizer(
                ngram_range=(1, 2),
                stop_words="english",
                sublinear_tf=True,
                max_features=5000,
            )
            tfidf_matrix = vectorizer.fit_transform([resume_text, jd_text])
            sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            # TF-IDF cosine similarity between resume & JD typically ranges 0.15 - 0.75
            # Scale non-linearly to provide a normalized 0-100 score
            scaled = min(max(float(sim) * 125.0, 0.0), 100.0)
            return round(scaled, 1)
        except Exception as e:
            logger.warning(f"Error computing TF-IDF similarity: {e}")
            return 50.0

    def compute_skill_scores(
        self,
        candidate_skills: List[str],
        required_skills: List[str],
        preferred_skills: List[str]
    ) -> Tuple[float, List[str], List[str], List[str], List[str]]:
        """Calculate skill overlap score and classify matched, missing, and extra skills.

        Returns:
            Tuple of:
            - skill_score (0-100)
            - matched_skills
            - missing_required_skills
            - missing_preferred_skills
            - additional_skills
        """
        cand_set = set(candidate_skills)
        req_set = set(required_skills)
        pref_set = set(preferred_skills)

        # In case JD didn't have explicit required skills
        if not req_set and not pref_set:
            return 100.0, list(cand_set), [], [], list(cand_set)

        matched_req = cand_set.intersection(req_set)
        matched_pref = cand_set.intersection(pref_set)
        all_matched = sorted(list(matched_req.union(matched_pref)))

        missing_req = sorted(list(req_set - cand_set))
        missing_pref = sorted(list(pref_set - cand_set))
        additional = sorted(list(cand_set - req_set - pref_set))

        # Weighting: 80% on required skills recall, 20% on preferred skills recall
        req_score = (len(matched_req) / len(req_set) * 100.0) if req_set else 100.0
        pref_score = (len(matched_pref) / len(pref_set) * 100.0) if pref_set else 100.0

        if req_set and pref_set:
            final_skill_score = 0.80 * req_score + 0.20 * pref_score
        elif req_set:
            final_skill_score = req_score
        else:
            final_skill_score = pref_score

        return (
            round(min(max(final_skill_score, 0.0), 100.0), 1),
            all_matched,
            missing_req,
            missing_pref,
            additional,
        )

    def compute_experience_score(self, cand_years: float, req_years: float) -> float:
        """Score candidate's experience against requirement."""
        if req_years <= 0.0:
            return 100.0

        if cand_years >= req_years:
            # Full marks, with slight bonus if seasoned (up to 100)
            return 100.0

        # Partial credit: ratio of experience
        ratio = cand_years / req_years
        score = ratio * 100.0
        return round(min(max(score, 0.0), 100.0), 1)

    def compute_education_score(self, cand_degrees: List[str], req_degree: Optional[str]) -> float:
        """Compare candidate's degrees against JD requirement."""
        if not req_degree or req_degree not in DEGREE_HIERARCHY:
            return 100.0

        req_level = DEGREE_HIERARCHY[req_degree]

        cand_levels = [DEGREE_HIERARCHY.get(d, 0) for d in cand_degrees]
        max_cand_level = max(cand_levels) if cand_levels else 0

        if max_cand_level >= req_level:
            return 100.0
        elif max_cand_level == req_level - 1:
            return 80.0
        elif max_cand_level == req_level - 2:
            return 60.0
        else:
            return 40.0

    def compute_category_coverage(
        self,
        candidate_skills: List[str],
        jd_skills: List[str]
    ) -> Dict[str, float]:
        """Compute match percentage per skill taxonomy category."""
        cand_set = set(candidate_skills)
        cat_map: Dict[str, Set[str]] = {}
        for skill in jd_skills:
            cat = self.extractor.skill_to_category.get(skill, "General")
            cat_map.setdefault(cat, set()).add(skill)

        coverage: Dict[str, float] = {}
        for cat, skills in cat_map.items():
            matched = len(skills.intersection(cand_set))
            coverage[cat] = round((matched / len(skills)) * 100.0, 1)

        return coverage

    def match(
        self,
        resume: ResumeProfile,
        jd: JobDescriptionProfile,
        weights: Optional[Dict[str, float]] = None,
    ) -> MatchBreakdown:
        """Compute full matching breakdown between a candidate resume profile and a JD profile.

        Args:
            resume: Parsed resume profile.
            jd: Parsed job description profile.
            weights: Optional custom dictionary of weights for:
                     skills, experience, education, semantic.
        """
        w = weights or {
            "skills": 0.45,
            "experience": 0.25,
            "education": 0.10,
            "semantic": 0.20,
        }

        # Candidate skills
        cand_skills = self.extractor.get_skill_names(resume.raw_text)

        # 1. Skill Scores
        skill_score, matched, missing_req, missing_pref, additional = self.compute_skill_scores(
            cand_skills,
            jd.required_skills,
            jd.preferred_skills,
        )

        # 2. Experience Score
        exp_score = self.compute_experience_score(
            resume.total_experience_years,
            jd.min_experience_years,
        )

        # 3. Education Score
        edu_score = self.compute_education_score(
            resume.degrees,
            jd.required_education,
        )

        # 4. Semantic Similarity
        semantic_score = self.compute_semantic_similarity(
            resume.raw_text,
            jd.raw_text,
        )

        # Category coverage for visualization
        cat_coverage = self.compute_category_coverage(cand_skills, jd.all_skills)

        # Overall composite score
        overall = (
            w.get("skills", 0.45) * skill_score
            + w.get("experience", 0.25) * exp_score
            + w.get("education", 0.10) * edu_score
            + w.get("semantic", 0.20) * semantic_score
        )
        overall = round(min(max(overall, 0.0), 100.0), 1)

        return MatchBreakdown(
            overall_score=overall,
            skills_score=skill_score,
            experience_score=exp_score,
            education_score=edu_score,
            semantic_score=semantic_score,
            matched_skills=matched,
            missing_required_skills=missing_req,
            missing_preferred_skills=missing_pref,
            additional_skills=additional,
            candidate_experience_years=resume.total_experience_years,
            required_experience_years=jd.min_experience_years,
            candidate_degrees=resume.degrees,
            required_education=jd.required_education,
            category_coverage=cat_coverage,
        )
