"""Resume section splitting and candidate metadata extraction.

Extracts structured sections (experience, education, skills, projects, summary)
and metadata (name, email, phone, links, years of experience, degrees, titles).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import spacy

from screener.logger import get_logger

logger = get_logger(__name__)

# Lazy loaded spaCy model
_NLP = None


def get_spacy_nlp():
    """Lazy load and return spaCy en_core_web_sm pipeline."""
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except Exception as e:
            logger.warning(f"Could not load en_core_web_sm directly: {e}. Trying spacy.blank('en').")
            _NLP = spacy.blank("en")
    return _NLP


# Common section header keywords mapped to canonical section names
SECTION_PATTERNS = {
    "summary": [
        r"summary",
        r"professional summary",
        r"executive summary",
        r"career summary",
        r"profile",
        r"personal profile",
        r"about me",
        r"objective",
        r"career objective",
    ],
    "experience": [
        r"experience",
        r"work experience",
        r"employment history",
        r"professional experience",
        r"work history",
        r"relevant experience",
        r"internships",
        r"career history",
    ],
    "education": [
        r"education",
        r"academic background",
        r"educational background",
        r"academics",
        r"qualifications",
        r"academic qualifications",
        r"degrees",
    ],
    "skills": [
        r"skills",
        r"technical skills",
        r"core competencies",
        r"key skills",
        r"technologies",
        r"tools & technologies",
        r"tech stack",
        r"proficiencies",
        r"expertise",
        r"areas of expertise",
    ],
    "projects": [
        r"projects",
        r"personal projects",
        r"academic projects",
        r"key projects",
        r"portfolio",
        r"open source",
    ],
    "certifications": [
        r"certifications",
        r"certificates",
        r"licenses",
        r"courses",
        r"credentials",
        r"awards",
        r"honors",
    ],
}

COMMON_JOB_TITLES = [
    "software engineer", "software developer", "full stack developer", "full stack engineer",
    "frontend developer", "frontend engineer", "backend developer", "backend engineer",
    "senior software engineer", "lead developer", "tech lead", "engineering manager",
    "devops engineer", "cloud engineer", "site reliability engineer", "sre",
    "data scientist", "data engineer", "data analyst", "machine learning engineer", "ml engineer",
    "ai engineer", "product manager", "project manager", "scrum master",
    "qa engineer", "quality assurance engineer", "automation engineer",
    "solutions architect", "system architect", "cloud architect", "database administrator",
    "security engineer", "cybersecurity analyst", "consultant", "intern", "associate"
]

DEGREE_LEVELS = {
    "phd": ["ph.d", "phd", "doctor of philosophy", "doctorate"],
    "masters": ["master", "m.s.", "m.s", "ms", "m.sc", "msc", "m.tech", "mtech", "mba", "m.eng"],
    "bachelors": ["bachelor", "b.s.", "b.s", "bs", "b.sc", "bsc", "b.tech", "btech", "b.e.", "be", "b.a.", "ba"],
    "associate": ["associate degree", "associates", "associate of science", "associate of arts"],
}


@dataclass
class ResumeProfile:
    """Structured representation of a parsed resume."""
    raw_text: str
    name: str = "Unknown Candidate"
    email: Optional[str] = None
    phone: Optional[str] = None
    links: List[str] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)
    total_experience_years: float = 0.0
    job_titles: List[str] = field(default_factory=list)
    degrees: List[str] = field(default_factory=list)
    education_institutions: List[str] = field(default_factory=list)
    has_quantifiable_metrics: bool = False
    metrics_count: int = 0


def extract_email(text: str) -> Optional[str]:
    """Extract primary email address from text."""
    pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    match = re.search(pattern, text)
    return match.group(0).lower().strip() if match else None


def extract_phone(text: str) -> Optional[str]:
    """Extract contact phone number from text."""
    pattern = r"(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?"
    # Alternative international / simple format
    intl_pattern = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    
    match = re.search(pattern, text)
    if match and len(match.group(0).strip()) >= 10:
        return match.group(0).strip()

    match_intl = re.search(intl_pattern, text)
    if match_intl and len(match_intl.group(0).strip()) >= 10:
        return match_intl.group(0).strip()
    return None


def extract_links(text: str) -> List[str]:
    """Extract LinkedIn, GitHub, and portfolio URLs."""
    patterns = [
        r"(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?",
        r"(?:https?://)?(?:www\.)?github\.com/[a-zA-Z0-9_-]+/?",
        r"https?://[a-zA-Z0-9_.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?"
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            link = m.group(0)
            if not any(link in existing for existing in found):
                found.append(link)
    return found[:5]


def extract_candidate_name(text: str, nlp=None) -> str:
    """Extract the candidate's name from the header/top lines of the resume."""
    if nlp is None:
        nlp = get_spacy_nlp()

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "Unknown Candidate"

    # Examine the first 6 lines
    top_lines = lines[:6]
    candidate_lines = []
    for line in top_lines:
        lower = line.lower()
        # Skip lines that are clearly emails, URLs, phones, or section titles
        if "@" in line or "github" in lower or "linkedin" in lower or "resume" in lower or "curriculum" in lower:
            continue
        if any(h in lower for h in ["summary", "experience", "education", "skills"]):
            break
        # Remove numbers and punctuation
        cleaned = re.sub(r"[0-9\(\)\+\-\|\:\,]", "", line).strip()
        words = cleaned.split()
        if 2 <= len(words) <= 4 and all(w.isalpha() for w in words):
            candidate_lines.append(cleaned)

    # 1. Try NER on top lines
    header_block = " \n ".join(candidate_lines if candidate_lines else top_lines[:3])
    doc = nlp(header_block)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            words = ent.text.strip().split()
            if 2 <= len(words) <= 4 and not any(w.lower() in ["curriculum", "resume", "page", "developer", "engineer"] for w in words):
                return ent.text.strip().title()

    # 2. Fallback to first plausible 2-4 word title line
    if candidate_lines:
        return candidate_lines[0].title()

    # 3. Fallback to first line cleaned
    first_words = [w for w in re.sub(r"[^A-Za-z\s]", "", lines[0]).split() if len(w) > 1]
    if 1 <= len(first_words) <= 4:
        return " ".join(first_words).title()

    return "Unknown Candidate"


def split_into_sections(text: str) -> Dict[str, str]:
    """Segment a resume's text into logical sections based on header patterns."""
    sections: Dict[str, str] = {
        "header": "",
        "summary": "",
        "experience": "",
        "education": "",
        "skills": "",
        "projects": "",
        "certifications": "",
        "other": "",
    }

    # Compile regex pattern to identify headers
    # A header is typically on its own line, often capitalized, <= 4 words
    all_headers: List[Tuple[str, re.Pattern]] = []
    for sec_name, pats in SECTION_PATTERNS.items():
        pattern = re.compile(
            r"^(?:[\s\*\#\-\_\>]*)\b(" + "|".join(pats) + r")\b[\s\:\-\_]*$",
            re.IGNORECASE | re.MULTILINE
        )
        all_headers.append((sec_name, pattern))

    lines = text.split("\n")
    indexed_headers: List[Tuple[int, str]] = []

    for idx, line in enumerate(lines):
        trimmed = line.strip()
        if not trimmed or len(trimmed.split()) > 5:
            continue
        
        # Test if line matches any section keyword
        for sec_name, pattern in all_headers:
            if pattern.match(trimmed):
                indexed_headers.append((idx, sec_name))
                break

    if not indexed_headers:
        # Fallback: couldn't detect explicit headers, treat all as experience/general
        sections["summary"] = text[:500]
        sections["experience"] = text
        return sections

    # Capture header section (before first recognized heading)
    first_idx = indexed_headers[0][0]
    sections["header"] = "\n".join(lines[:first_idx]).strip()

    # Populate sections
    for i, (start_idx, sec_name) in enumerate(indexed_headers):
        end_idx = indexed_headers[i + 1][0] if i + 1 < len(indexed_headers) else len(lines)
        # Content from line start_idx + 1 to end_idx
        content = "\n".join(lines[start_idx + 1 : end_idx]).strip()
        if sec_name in sections and sections[sec_name]:
            sections[sec_name] += "\n\n" + content
        else:
            sections[sec_name] = content

    return sections


MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12
}


def _parse_month_year(text: str) -> Optional[Tuple[int, int]]:
    """Parse date tokens into (year, month). Returns None on failure."""
    text = text.strip().lower()
    if text in ["present", "current", "now", "ongoing"]:
        now = datetime.datetime.now()
        return (now.year, now.month)

    # Format: Month Year (e.g. June 2021)
    m1 = re.search(r"([a-z]{3,9})\.?\s+(\d{4})", text)
    if m1:
        mon_str, yr_str = m1.groups()
        mon = MONTH_NAMES.get(mon_str[:3], 1)
        yr = int(yr_str)
        return (yr, mon)

    # Format: MM/YYYY or MM-YYYY
    m2 = re.search(r"(\d{1,2})[/-](\d{4})", text)
    if m2:
        mon, yr = int(m2.group(1)), int(m2.group(2))
        if 1 <= mon <= 12 and 1970 <= yr <= 2040:
            return (yr, mon)

    # Format: Just Year (e.g. 2020)
    m3 = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    if m3:
        yr = int(m3.group(1))
        return (yr, 1)

    return None


def calculate_experience_years(text: str) -> float:
    """Calculate total years of experience from date intervals found in text."""
    # Match patterns like:
    # "Jan 2018 - Mar 2021", "2019 – Present", "05/2020 to 11/2022"
    month_regex = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    date_token = rf"(?:{month_regex}\.?\s+\d{{4}}|\d{{1,2}}[/-]\d{{4}}|\b(?:19\d{{2}}|20\d{{2}})\b|Present|Current|Now)"
    
    interval_pattern = re.compile(
        rf"({date_token})\s*(?:-|–|—|to)\s*({date_token})",
        re.IGNORECASE
    )

    intervals: List[Tuple[float, float]] = []

    for match in interval_pattern.finditer(text):
        start_str, end_str = match.groups()
        start = _parse_month_year(start_str)
        end = _parse_month_year(end_str)

        if start and end:
            start_val = start[0] + (start[1] - 1) / 12.0
            end_val = end[0] + (end[1] - 1) / 12.0
            if end_val >= start_val and (end_val - start_val) <= 40:
                intervals.append((start_val, end_val))

    if not intervals:
        # Fallback: check if text explicitly states "X years of experience"
        exp_match = re.search(r"(\d+(?:\.\d+)?)\+?\s*years?(?:\s+of)?\s+experience", text, re.IGNORECASE)
        if exp_match:
            try:
                return float(exp_match.group(1))
            except ValueError:
                pass
        return 0.0

    # Merge overlapping intervals to avoid double counting
    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[float, float]] = []
    for start, end in intervals:
        if not merged:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

    total_years = sum(end - start for start, end in merged)
    # Reasonable cap between 0 and 45 years
    return round(min(max(total_years, 0.0), 45.0), 1)


def extract_job_titles(text: str) -> List[str]:
    """Identify job titles mentioned in the resume."""
    found_titles: Set[str] = set()
    text_lower = text.lower()

    for title in COMMON_JOB_TITLES:
        pattern = rf"\b{re.escape(title)}\b"
        if re.search(pattern, text_lower):
            found_titles.add(title.title())

    # Check capitalized title-like phrases (e.g. Lead Cloud Architect)
    for line in text.split("\n"):
        clean_line = line.strip()
        if 2 <= len(clean_line.split()) <= 4:
            clean_lower = clean_line.lower()
            if any(term in clean_lower for term in ["engineer", "developer", "architect", "manager", "lead", "analyst"]):
                if not any(char in clean_line for char in [":", "@", ".", "/", "\\"]):
                    found_titles.add(clean_line)

    return sorted(list(found_titles))[:8]


def extract_degrees_and_education(text: str, nlp=None) -> Tuple[List[str], List[str]]:
    """Extract academic degrees and university names from text."""
    if nlp is None:
        nlp = get_spacy_nlp()

    found_degrees: Set[str] = set()
    text_lower = text.lower()

    # Detect degree levels
    for level, degree_synonyms in DEGREE_LEVELS.items():
        for syn in degree_synonyms:
            pattern = rf"\b{re.escape(syn)}\b"
            if re.search(pattern, text_lower):
                if level == "phd":
                    found_degrees.add("Ph.D. / Doctorate")
                elif level == "masters":
                    found_degrees.add("Master's Degree")
                elif level == "bachelors":
                    found_degrees.add("Bachelor's Degree")
                elif level == "associate":
                    found_degrees.add("Associate Degree")
                break

    # Extract institutions with spaCy ORG or educational terms
    institutions: Set[str] = set()
    for line in text.split("\n"):
        line_clean = line.strip()
        line_lower = line_clean.lower()
        if any(term in line_lower for term in ["university", "college", "institute", "polytechnic", "school of"]):
            # Clean punctuation
            clean_inst = re.sub(r"[,|\(\)\d]", "", line_clean).strip()
            if 3 <= len(clean_inst) <= 60:
                institutions.add(clean_inst)

    # Also check spaCy NER for ORG in education section
    doc = nlp(text[:1000])
    for ent in doc.ents:
        if ent.label_ == "ORG":
            ent_lower = ent.text.lower()
            if any(term in ent_lower for term in ["univ", "college", "institute", "school"]):
                institutions.add(ent.text.strip())

    return sorted(list(found_degrees)), sorted(list(institutions))[:4]


def detect_quantifiable_achievements(text: str) -> Tuple[bool, int]:
    """Detect whether the candidate included measurable metrics (% improvements, $ revenue, numbers)."""
    # Regex looking for metrics like "35%", "$1.2M", "reduced latency by 40%", "10k users"
    metric_patterns = [
        r"\b\d+%",
        r"\$\s*\d+(?:\.\d+)?\s*[kmb]?",
        r"\b(?:increased|decreased|reduced|improved|grew|saved|boosted)\s+\w*\s*\d+%",
        r"\b\d+\s*(?:users|clients|customers|requests|transactions|stars|downloads|team members)\b",
    ]
    total_count = 0
    for pat in metric_patterns:
        matches = re.findall(pat, text, re.IGNORECASE)
        total_count += len(matches)

    return total_count > 0, total_count


def parse_resume_to_profile(text: str) -> ResumeProfile:
    """Full pipeline: extract structured profile from resume text."""
    nlp = get_spacy_nlp()
    sections = split_into_sections(text)

    name = extract_candidate_name(text, nlp=nlp)
    email = extract_email(text)
    phone = extract_phone(text)
    links = extract_links(text)

    # Compute experience specifically from the experience section, or full text if empty
    exp_text = sections.get("experience", "") or text
    exp_years = calculate_experience_years(exp_text)

    job_titles = extract_job_titles(exp_text)

    # Education
    edu_text = sections.get("education", "") or text
    degrees, institutions = extract_degrees_and_education(edu_text, nlp=nlp)

    has_metrics, metrics_count = detect_quantifiable_achievements(exp_text)

    return ResumeProfile(
        raw_text=text,
        name=name,
        email=email,
        phone=phone,
        links=links,
        sections=sections,
        total_experience_years=exp_years,
        job_titles=job_titles,
        degrees=degrees,
        education_institutions=institutions,
        has_quantifiable_metrics=has_metrics,
        metrics_count=metrics_count,
    )
