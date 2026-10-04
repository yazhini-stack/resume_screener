"""Skills extraction module using a rich taxonomy, alias mapping, RapidFuzz, and spaCy NER.

Extracts tech, business, and soft skills with category tagging and alias resolution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

from screener.logger import get_logger
from screener.sections import get_spacy_nlp

logger = get_logger(__name__)

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "skills_taxonomy.json"


@dataclass
class ExtractedSkill:
    """Represents an identified skill."""
    name: str
    category: str
    match_type: str  # 'exact', 'alias', 'fuzzy', 'ner_detected'
    confidence: float
    raw_match: str


class SkillsExtractor:
    """Loads taxonomy and extracts canonical skills from text."""

    def __init__(self, taxonomy_file: Optional[Path] = None):
        self.taxonomy_path = taxonomy_file or TAXONOMY_PATH
        self.categories: Dict[str, Dict[str, List[str]]] = {}
        # skill_to_category: canonical_name -> category
        self.skill_to_category: Dict[str, str] = {}
        # alias_map: lowercase_alias -> canonical_name
        self.alias_map: Dict[str, str] = {}
        # short_skills: skills with <= 3 characters requiring strict word boundaries
        self.short_skills: Set[str] = set()
        self.all_canonical_skills: Set[str] = set()

        self._load_taxonomy()

    def _load_taxonomy(self) -> None:
        """Load and index the skills taxonomy from JSON."""
        if not self.taxonomy_path.exists():
            logger.warning(f"Taxonomy file not found at {self.taxonomy_path}. Creating fallback.")
            self._create_fallback_taxonomy()

        try:
            with open(self.taxonomy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.categories = data.get("categories", {})
        except Exception as e:
            logger.error(f"Error loading taxonomy {self.taxonomy_path}: {e}")
            self._create_fallback_taxonomy()

        self._index_skills()

    def _create_fallback_taxonomy(self) -> None:
        """Fallback basic skills taxonomy."""
        self.categories = {
            "Programming Languages": {
                "Python": ["python", "py"],
                "JavaScript": ["javascript", "js"],
                "SQL": ["sql"],
                "Java": ["java"],
                "C++": ["c++", "cpp"],
            },
            "Frameworks": {
                "React": ["react", "react.js"],
                "FastAPI": ["fastapi"],
                "Django": ["django"],
            },
            "Cloud": {
                "AWS": ["aws", "amazon web services"],
                "Docker": ["docker"],
                "Kubernetes": ["kubernetes", "k8s"],
            }
        }

    def _index_skills(self) -> None:
        """Build fast lookup indexes for skills, aliases, and categories."""
        self.alias_map.clear()
        self.skill_to_category.clear()
        self.short_skills.clear()
        self.all_canonical_skills.clear()

        for category, skills in self.categories.items():
            for canonical_name, aliases in skills.items():
                self.all_canonical_skills.add(canonical_name)
                self.skill_to_category[canonical_name] = category

                # Canonical name itself (lowercased)
                canonical_lower = canonical_name.lower().strip()
                self.alias_map[canonical_lower] = canonical_name
                if len(canonical_lower) <= 3:
                    self.short_skills.add(canonical_lower)

                # Aliases
                for alias in aliases:
                    alias_lower = alias.lower().strip()
                    self.alias_map[alias_lower] = canonical_name
                    if len(alias_lower) <= 3:
                        self.short_skills.add(alias_lower)

        logger.info(
            f"Indexed {len(self.all_canonical_skills)} canonical skills across "
            f"{len(self.categories)} categories with {len(self.alias_map)} aliases."
        )

    def extract_skills(
        self,
        text: str,
        fuzzy_threshold: float = 90.0,
        enable_ner: bool = True
    ) -> List[ExtractedSkill]:
        """Extract all matched skills from text.

        Args:
            text: Resume or job description content.
            fuzzy_threshold: Minimum RapidFuzz ratio for fuzzy alias matching (default 90%).
            enable_ner: Whether to also inspect spaCy entities and noun chunks.

        Returns:
            List of ExtractedSkill instances with canonical names and categories.
        """
        if not text:
            return []

        text_clean = text.replace("\r", " ").replace("\t", " ")
        text_lower = text_clean.lower()
        extracted: Dict[str, ExtractedSkill] = {}

        # 1. Exact & Alias matching with boundary checks
        # Sort aliases by length descending so longer multi-word phrases match first
        sorted_aliases = sorted(self.alias_map.keys(), key=len, reverse=True)

        for alias in sorted_aliases:
            canonical = self.alias_map[alias]
            if canonical in extracted:
                continue

            # Check if alias exists in text with proper boundaries
            # Handle special characters in tech terms like C++, C#, .NET, CI/CD
            escaped_alias = re.escape(alias)
            if alias in self.short_skills:
                # Strict boundary for short terms like C, R, Go, JS, Py
                pattern = rf"(?<![a-zA-Z0-9_]){escaped_alias}(?![a-zA-Z0-9_])"
            else:
                pattern = rf"\b{escaped_alias}\b"

            match = re.search(pattern, text_lower)
            if match:
                raw = text_clean[match.start():match.end()]
                match_type = "exact" if alias == canonical.lower() else "alias"
                extracted[canonical] = ExtractedSkill(
                    name=canonical,
                    category=self.skill_to_category.get(canonical, "General"),
                    match_type=match_type,
                    confidence=1.0 if match_type == "exact" else 0.95,
                    raw_match=raw,
                )

        # 2. Fuzzy matching on token n-grams for skills not yet matched
        # Extract potential 1-word and 2-word terms from text
        words = re.findall(r"\b[A-Za-z0-9+#.-]{3,}\b", text_clean)
        candidates_to_check: Set[str] = set()
        for i in range(len(words)):
            candidates_to_check.add(words[i].lower())
            if i + 1 < len(words):
                candidates_to_check.add(f"{words[i].lower()} {words[i+1].lower()}")

        # Check candidate tokens against remaining unextracted canonical skills
        for canonical in self.all_canonical_skills:
            if canonical in extracted:
                continue
            canonical_lower = canonical.lower()
            if len(canonical_lower) < 4:
                continue  # Never fuzzy match very short terms like 'R' or 'Go'

            best_ratio = 0.0
            best_token = ""
            for token in candidates_to_check:
                # Skip if length disparity is too large
                if abs(len(token) - len(canonical_lower)) > 3:
                    continue
                ratio = fuzz.ratio(canonical_lower, token)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_token = token

            if best_ratio >= fuzzy_threshold:
                extracted[canonical] = ExtractedSkill(
                    name=canonical,
                    category=self.skill_to_category.get(canonical, "General"),
                    match_type="fuzzy",
                    confidence=round(best_ratio / 100.0, 2),
                    raw_match=best_token,
                )

        # 3. spaCy NER / Noun Chunk extraction for contextual skills & entities
        if enable_ner and text.strip():
            try:
                nlp = get_spacy_nlp()
                # Process first 3000 chars or skills section to extract organizations and technologies
                doc = nlp(text[:3000])
                for ent in doc.ents:
                    if ent.label_ in ("PRODUCT", "ORG"):
                        ent_lower = ent.text.lower().strip()
                        if ent_lower in self.alias_map:
                            can = self.alias_map[ent_lower]
                            if can not in extracted:
                                extracted[can] = ExtractedSkill(
                                    name=can,
                                    category=self.skill_to_category.get(can, "General"),
                                    match_type="ner_detected",
                                    confidence=0.92,
                                    raw_match=ent.text,
                                )
            except Exception as e:
                logger.debug(f"spaCy NER processing notice: {e}")

        return sorted(list(extracted.values()), key=lambda s: (s.category, s.name))

    def get_skill_names(self, text: str) -> List[str]:
        """Convenience method returning a sorted list of unique canonical skill names."""
        skills = self.extract_skills(text)
        return sorted([s.name for s in skills])

    def get_skills_by_category(self, text: str) -> Dict[str, List[str]]:
        """Group extracted skills by category."""
        skills = self.extract_skills(text)
        categorized: Dict[str, List[str]] = {}
        for s in skills:
            categorized.setdefault(s.category, []).append(s.name)
        return categorized
