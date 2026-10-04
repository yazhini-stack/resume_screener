"""Job description parser module.

Extracts job title, minimum years of experience, required vs preferred skills,
and education qualifications from job postings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from screener.logger import get_logger
from screener.sections import DEGREE_LEVELS
from screener.skills_extractor import ExtractedSkill, SkillsExtractor

logger = get_logger(__name__)


class EmptyJobDescriptionError(Exception):
    """Raised when job description text is empty or meaningless."""
    pass


@dataclass
class JobDescriptionProfile:
    """Structured representation of a parsed job description."""
    raw_text: str
    title: str = "Job Opening"
    min_experience_years: float = 0.0
    max_experience_years: Optional[float] = None
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    all_skills: List[str] = field(default_factory=list)
    categorized_skills: Dict[str, List[str]] = field(default_factory=dict)
    required_education: Optional[str] = None
    responsibilities: List[str] = field(default_factory=list)


# Heading patterns for required vs nice-to-have skills
REQUIRED_HEADINGS = [
    r"requirements",
    r"required qualifications",
    r"what you need",
    r"must have",
    r"minimum qualifications",
    r"what we are looking for",
    r"core skills",
    r"essential skills",
    r"basic qualifications",
]

PREFERRED_HEADINGS = [
    r"nice to have",
    r"preferred qualifications",
    r"preferred skills",
    r"bonus points",
    r"what would set you apart",
    r"pluses",
    r"good to have",
    r"desired skills",
]


class JobDescriptionParser:
    """Parser for job descriptions."""

    def __init__(self, extractor: Optional[SkillsExtractor] = None):
        self.extractor = extractor or SkillsExtractor()

    def parse(self, text: str) -> JobDescriptionProfile:
        """Parse raw job description text into a structured profile."""
        if not text or len(text.strip()) < 15:
            raise EmptyJobDescriptionError(
                "Job description is empty or too short. Please provide a detailed job posting."
            )

        clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

        title = self.extract_title(clean_text)
        min_years, max_years = self.extract_experience_requirement(clean_text)
        required_edu = self.extract_education_requirement(clean_text)

        req_skills, pref_skills, all_skills = self.extract_categorized_skills(clean_text)
        categorized = self.extractor.get_skills_by_category(clean_text)

        return JobDescriptionProfile(
            raw_text=clean_text,
            title=title,
            min_experience_years=min_years,
            max_experience_years=max_years,
            required_skills=req_skills,
            preferred_skills=pref_skills,
            all_skills=all_skills,
            categorized_skills=categorized,
            required_education=required_edu,
        )

    def extract_title(self, text: str) -> str:
        """Extract or infer job title from job description."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return "Job Opening"

        # Check line 1 or line 2 for "Job Title:", "Role:", "Position:"
        for line in lines[:5]:
            match = re.search(r"^(?:job\s+title|role|position|opening)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip().title()

        # Check first line if short and title-like
        first_line = lines[0]
        if len(first_line.split()) <= 6 and not any(k in first_line.lower() for k in ["about", "company", "we are", "overview"]):
            return first_line.strip().title()

        # Search for common role names in text
        for line in lines[:10]:
            clean = line.strip()
            if any(term in clean.lower() for term in ["engineer", "developer", "architect", "scientist", "manager", "lead", "analyst"]):
                if len(clean.split()) <= 6:
                    return clean.title()

        return "Job Opening"

    def extract_experience_requirement(self, text: str) -> Tuple[float, Optional[float]]:
        """Extract minimum and optional maximum years of experience required."""
        # Patterns like:
        # "5+ years of professional backend software development experience"
        # "3-5 years of experience", "at least 4 years of experience"
        patterns = [
            # Range: 3-5 years / 3 to 5 years
            r"(\d+)\s*(?:-|–|to)\s*(\d+)\+?\s*years?(?:\s+of)?(?:\s+[\w\s/-]{0,50})?\s+experience",
            # At least / minimum / min X years
            r"(?:at\s+least|minimum|min|no\s+less\s+than)\s*(\d+)\+?\s*years?(?:\s+of)?(?:\s+[\w\s/-]{0,50})?\s+experience",
            # X+ years ... experience
            r"(\d+)\+\s*years?(?:\s+of)?(?:\s+[\w\s/-]{0,50})?\s+experience",
            # X years of ... experience
            r"(\d+)\s+years?(?:\s+of)?(?:\s+[\w\s/-]{0,50})?\s+experience",
            # Experience: X+ years
            r"experience\s*[:\-]\s*(\d+)\+?\s*(?:-|–|to)?\s*(\d+)?\s*years?",
            # X+ years of hands-on experience
            r"(\d+)\+?\s*years?(?:\s+of)?\s+(?:hands-on\s+)?experience",
        ]

        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                min_yr = float(groups[0])
                max_yr = float(groups[1]) if len(groups) > 1 and groups[1] else None
                return min_yr, max_yr

        return 0.0, None

    def extract_education_requirement(self, text: str) -> Optional[str]:
        """Detect minimum degree level required by JD."""
        text_lower = text.lower()
        if any(term in text_lower for term in ["ph.d", "phd", "doctorate"]):
            return "Ph.D. / Doctorate"
        if any(term in text_lower for term in ["master's", "masters", "master of", "m.s.", "ms degree", "mba"]):
            return "Master's Degree"
        if any(term in text_lower for term in ["bachelor's", "bachelors", "bachelor of", "b.s.", "bs degree", "b.tech", "b.e."]):
            return "Bachelor's Degree"
        return None

    def extract_categorized_skills(self, text: str) -> Tuple[List[str], List[str], List[str]]:
        """Separate required skills from preferred/nice-to-have skills."""
        all_skills = self.extractor.get_skill_names(text)
        if not all_skills:
            return [], [], []

        # Split text into sections based on headings
        lines = text.split("\n")
        req_lines: List[str] = []
        pref_lines: List[str] = []
        current_section = "general"

        req_pattern = re.compile(r"^(?:[\s\*\#\-\_\>]*)\b(" + "|".join(REQUIRED_HEADINGS) + r")\b[\s\:\-\_]*$", re.IGNORECASE)
        pref_pattern = re.compile(r"^(?:[\s\*\#\-\_\>]*)\b(" + "|".join(PREFERRED_HEADINGS) + r")\b[\s\:\-\_]*$", re.IGNORECASE)

        for line in lines:
            line_str = line.strip()
            if req_pattern.match(line_str):
                current_section = "required"
                continue
            elif pref_pattern.match(line_str):
                current_section = "preferred"
                continue
            elif re.match(r"^(?:[\s\*\#\-\_\>]*)\b(?:benefits|about us|perks|company)\b", line_str, re.IGNORECASE):
                current_section = "other"
                continue

            if current_section == "required":
                req_lines.append(line)
            elif current_section == "preferred":
                pref_lines.append(line)

        req_text = "\n".join(req_lines)
        pref_text = "\n".join(pref_lines)

        req_skills = self.extractor.get_skill_names(req_text)
        pref_skills = self.extractor.get_skill_names(pref_text)

        # Remove overlap: if in preferred, make sure it's not marked required unless explicitly so
        pref_skills_clean = [s for s in pref_skills if s not in req_skills]

        # If no explicit sections were parsed, mark all detected skills as required
        if not req_skills and not pref_skills_clean:
            req_skills = all_skills

        return sorted(list(set(req_skills))), sorted(list(set(pref_skills_clean))), sorted(all_skills)
