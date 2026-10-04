"""Unit and integration test suite for resume_screener."""

from pathlib import Path
import pytest

from screener.parser import (
    parse_resume,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text_from_txt,
    ScannedResumeError,
    CorruptedResumeError,
    UnsupportedFormatError,
)
from screener.sections import (
    parse_resume_to_profile,
    split_into_sections,
    calculate_experience_years,
    extract_email,
    extract_phone,
    ResumeProfile,
)
from screener.skills_extractor import SkillsExtractor
from screener.jd_parser import JobDescriptionParser, EmptyJobDescriptionError
from screener.matcher import ResumeMatcher
from screener.scorer import ResumeScorer, get_match_rating_label
from screener.gap_analysis import generate_gap_analysis
from screener.database import Database
from screener.report import generate_recruiter_report, generate_candidate_report

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_resumes"
JD_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_job_description.txt"


@pytest.fixture
def sample_pdf():
    return SAMPLE_DIR / "alex_morgan_senior_python.pdf"


@pytest.fixture
def sample_docx():
    return SAMPLE_DIR / "elena_rostova_data_scientist.docx"


@pytest.fixture
def sample_txt():
    return SAMPLE_DIR / "sam_rivera_junior_frontend.txt"


@pytest.fixture
def sample_scanned_pdf():
    return SAMPLE_DIR / "scanned_image_only_sample.pdf"


@pytest.fixture
def sample_jd_text():
    return JD_PATH.read_text(encoding="utf-8")


# --- Parser Tests ---

def test_extract_text_from_pdf(sample_pdf):
    text = extract_text_from_pdf(sample_pdf)
    assert "Alex Morgan" in text
    assert "FastAPI" in text
    assert "Kubernetes" in text


def test_extract_text_from_docx(sample_docx):
    text = extract_text_from_docx(sample_docx)
    assert "Elena Rostova" in text
    assert "PyTorch" in text
    assert "Machine Learning" in text


def test_extract_text_from_txt(sample_txt):
    text = extract_text_from_txt(sample_txt)
    assert "Sam Rivera" in text
    assert "React" in text


def test_scanned_resume_raises_error(sample_scanned_pdf):
    with pytest.raises(ScannedResumeError):
        extract_text_from_pdf(sample_scanned_pdf)


def test_parse_resume_dispatch(sample_pdf, sample_docx, sample_txt):
    t_pdf = parse_resume(sample_pdf)
    t_docx = parse_resume(sample_docx)
    t_txt = parse_resume(sample_txt)

    assert len(t_pdf) > 100
    assert len(t_docx) > 100
    assert len(t_txt) > 100


def test_unsupported_format():
    with pytest.raises(UnsupportedFormatError):
        parse_resume("fake_file.xyz", filename="test.xyz")


# --- Section & Profile Extraction Tests ---

def test_sections_and_contact_extraction(sample_pdf):
    text = extract_text_from_pdf(sample_pdf)
    profile = parse_resume_to_profile(text)

    assert "Alex Morgan" in profile.name
    assert profile.email == "alex.morgan@email.com"
    assert profile.phone is not None
    assert "experience" in profile.sections
    assert profile.total_experience_years >= 5.0
    assert profile.has_quantifiable_metrics is True
    assert profile.metrics_count > 0


def test_calculate_experience_years():
    text = """
    Software Engineer | Tech Corp | Jan 2020 - Dec 2022
    Junior Engineer | Startup Inc | Jan 2018 - Dec 2019
    """
    years = calculate_experience_years(text)
    assert years >= 4.0


# --- Skills Extractor Tests ---

def test_skills_extractor_exact_and_alias():
    extractor = SkillsExtractor()
    sample = "We are seeking a developer with hands-on experience in Py, JS, K8s, and AWS."
    skills = extractor.extract_skills(sample)
    skill_names = [s.name for s in skills]

    assert "Python" in skill_names
    assert "JavaScript" in skill_names
    assert "Kubernetes" in skill_names
    assert "AWS" in skill_names


def test_skills_extractor_fuzzy():
    extractor = SkillsExtractor()
    # Misspelled term
    sample = "Deep expertise with Dockerr and PostgreSql databases."
    skills = extractor.extract_skills(sample, fuzzy_threshold=85.0)
    skill_names = [s.name for s in skills]

    assert "Docker" in skill_names
    assert "PostgreSQL" in skill_names


# --- JD Parser Tests ---

def test_jd_parser(sample_jd_text):
    parser = JobDescriptionParser()
    jd = parser.parse(sample_jd_text)

    assert "Senior Python" in jd.title
    assert jd.min_experience_years == 5.0
    assert "Python" in jd.required_skills
    assert "FastAPI" in jd.required_skills
    assert "Docker" in jd.required_skills
    assert "Kubernetes" in jd.required_skills


def test_empty_jd_raises_error():
    parser = JobDescriptionParser()
    with pytest.raises(EmptyJobDescriptionError):
        parser.parse("   ")


# --- Matcher & Scorer Tests ---

def test_matcher_and_ranking(sample_pdf, sample_docx, sample_txt, sample_jd_text):
    jd_parser = JobDescriptionParser()
    jd = jd_parser.parse(sample_jd_text)

    p1 = parse_resume_to_profile(parse_resume(sample_pdf))
    p2 = parse_resume_to_profile(parse_resume(sample_docx))
    p3 = parse_resume_to_profile(parse_resume(sample_txt))

    scorer = ResumeScorer()
    res1 = scorer.score_single(p1, jd, filename="alex_morgan_senior_python.pdf")
    res2 = scorer.score_single(p2, jd, filename="elena_rostova_data_scientist.docx")
    res3 = scorer.score_single(p3, jd, filename="sam_rivera_junior_frontend.txt")

    # Senior Python candidate should rank highest for Senior Python JD
    ranked = scorer.rank_candidates([res1, res2, res3])
    assert ranked[0].candidate_name == "Alex Morgan"
    assert ranked[0].overall_score > ranked[1].overall_score
    assert ranked[0].overall_score >= 80.0
    assert ranked[0].breakdown.experience_score == 100.0


def test_scorer_filtering(sample_pdf, sample_docx, sample_txt, sample_jd_text):
    jd_parser = JobDescriptionParser()
    jd = jd_parser.parse(sample_jd_text)

    p1 = parse_resume_to_profile(parse_resume(sample_pdf))
    p2 = parse_resume_to_profile(parse_resume(sample_docx))
    p3 = parse_resume_to_profile(parse_resume(sample_txt))

    scorer = ResumeScorer()
    results = [
        scorer.score_single(p1, jd, filename="alex.pdf"),
        scorer.score_single(p2, jd, filename="elena.docx"),
        scorer.score_single(p3, jd, filename="sam.txt"),
    ]

    # Filter by minimum 7 years experience (only Alex has >= 7 years, Elena has ~6, Sam has ~1.5)
    filtered = scorer.rank_candidates(results, min_experience_years=7.0)
    assert len(filtered) == 1
    assert filtered[0].candidate_name == "Alex Morgan"

    # Filter by required skill 'FastAPI'
    fastapi_filtered = scorer.rank_candidates(results, required_must_have_skills=["FastAPI"])
    assert any("Alex" in c.candidate_name for c in fastapi_filtered)


# --- Gap Analysis Tests ---

def test_gap_analysis(sample_txt, sample_jd_text):
    # Sam Rivera (Junior Frontend) against Senior Python JD
    p3 = parse_resume_to_profile(parse_resume(sample_txt))
    jd = JobDescriptionParser().parse(sample_jd_text)
    matcher = ResumeMatcher()
    breakdown = matcher.match(p3, jd)

    gap_report = generate_gap_analysis(p3, jd, breakdown)

    assert len(gap_report.missing_required_skills) > 0
    assert "Python" in gap_report.missing_required_skills
    assert gap_report.experience_gap_years > 0.0
    assert len(gap_report.suggestions) >= 2


# --- Database Tests ---

def test_database_operations(tmp_path):
    db_file = tmp_path / "test_screener.db"
    db = Database(db_path=db_file)

    jd_id = db.save_job_description(
        title="Python Dev",
        raw_text="Python and AWS",
        min_experience_years=3.0,
        required_skills=["Python", "AWS"],
        preferred_skills=["Docker"],
    )
    assert jd_id > 0

    res_id = db.save_resume(
        filename="test.pdf",
        candidate_name="Test Dev",
        email="test@test.com",
        phone="1234567890",
        raw_text="Experienced in Python",
        experience_years=4.0,
        skills=["Python"],
        degrees=["Bachelor's Degree"],
    )
    assert res_id > 0

    match_id = db.save_match_result(
        jd_id=jd_id,
        resume_id=res_id,
        mode="recruiter",
        overall_score=85.5,
        rating_label="Excellent Match",
        breakdown_dict={"skills_score": 90.0, "experience_score": 100.0},
    )
    assert match_id > 0

    history = db.get_history()
    assert len(history) == 1
    assert history[0]["candidate_name"] == "Test Dev"
    assert history[0]["overall_score"] == 85.5


# --- PDF Report Tests ---

def test_recruiter_report_generation(sample_pdf, sample_jd_text, tmp_path):
    jd = JobDescriptionParser().parse(sample_jd_text)
    profile = parse_resume_to_profile(parse_resume(sample_pdf))
    scorer = ResumeScorer()
    res = scorer.score_single(profile, jd, filename="alex.pdf")

    pdf_bytes = generate_recruiter_report([res], job_title=jd.title)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000

    out_file = tmp_path / "recruiter_report.pdf"
    generate_recruiter_report([res], job_title=jd.title, output_target=out_file)
    assert out_file.exists()
    assert out_file.stat().st_size > 2000


def test_candidate_report_generation(sample_txt, sample_jd_text, tmp_path):
    jd = JobDescriptionParser().parse(sample_jd_text)
    profile = parse_resume_to_profile(parse_resume(sample_txt))
    matcher = ResumeMatcher()
    breakdown = matcher.match(profile, jd)
    gap_report = generate_gap_analysis(profile, jd, breakdown)

    pdf_bytes = generate_candidate_report(gap_report, breakdown)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000

    out_file = tmp_path / "candidate_report.pdf"
    generate_candidate_report(gap_report, breakdown, output_target=out_file)
    assert out_file.exists()
    assert out_file.stat().st_size > 2000
