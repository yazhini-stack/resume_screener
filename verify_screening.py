"""End-to-end verification script for resume_screener.

Screens 3 sample resumes against the job description in recruiter mode,
runs candidate mode gap analysis on one resume, and exports both PDF report types
to the outputs/ directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from screener.database import Database
from screener.gap_analysis import generate_gap_analysis
from screener.jd_parser import JobDescriptionParser
from screener.logger import get_logger
from screener.matcher import ResumeMatcher
from screener.parser import parse_resume
from screener.report import generate_candidate_report, generate_recruiter_report
from screener.scorer import ResumeScorer
from screener.sections import parse_resume_to_profile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = get_logger("verification")

BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "data" / "sample_resumes"
JD_PATH = BASE_DIR / "data" / "sample_job_description.txt"
OUTPUT_DIR = BASE_DIR / "outputs"


def main():
    print("=" * 70)
    print("[*] RESUME SCREENER END-TO-END VERIFICATION")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize services
    print("\n[1/5] Initializing NLP, Matcher, and Database...")
    jd_parser = JobDescriptionParser()
    matcher = ResumeMatcher()
    scorer = ResumeScorer(matcher=matcher)
    db = Database()

    # 2. Parse Job Description
    print("\n[2/5] Parsing Sample Job Description...")
    jd_text = JD_PATH.read_text(encoding="utf-8")
    parsed_jd = jd_parser.parse(jd_text)
    print(f"  ✓ Job Title: {parsed_jd.title}")
    print(f"  ✓ Min Experience Required: {parsed_jd.min_experience_years:.1f} years")
    print(f"  ✓ Required Skills ({len(parsed_jd.required_skills)}): {', '.join(parsed_jd.required_skills)}")
    print(f"  ✓ Preferred Skills ({len(parsed_jd.preferred_skills)}): {', '.join(parsed_jd.preferred_skills)}")
    print(f"  ✓ Required Education: {parsed_jd.required_education or 'Flexible'}")

    jd_db_id = db.save_job_description(
        title=parsed_jd.title,
        raw_text=parsed_jd.raw_text,
        min_experience_years=parsed_jd.min_experience_years,
        required_skills=parsed_jd.required_skills,
        preferred_skills=parsed_jd.preferred_skills,
    )

    # 3. Recruiter Mode: Screen 3 Resumes
    print("\n[3/5] Running Recruiter Mode on 3 Sample Resumes...")
    sample_files = [
        "alex_morgan_senior_python.pdf",
        "elena_rostova_data_scientist.docx",
        "sam_rivera_junior_frontend.txt",
    ]

    screening_results = []
    for fname in sample_files:
        file_path = SAMPLE_DIR / fname
        raw_text = parse_resume(file_path)
        profile = parse_resume_to_profile(raw_text)
        res = scorer.score_single(profile, parsed_jd, filename=fname)
        screening_results.append(res)

        # Save to DB
        res_id = db.save_resume(
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
            resume_id=res_id,
            mode="recruiter",
            overall_score=res.overall_score,
            rating_label=res.rating_label,
            breakdown_dict={
                "skills_score": res.breakdown.skills_score,
                "experience_score": res.breakdown.experience_score,
                "education_score": res.breakdown.education_score,
                "semantic_score": res.breakdown.semantic_score,
            },
        )

    # Rank Candidates
    ranked_candidates = scorer.rank_candidates(screening_results)

    print("\n  [+] RANKED CANDIDATE LEADERBOARD:")
    print("  " + "-" * 66)
    print(f"  {'Rank':<5} {'Candidate Name':<22} {'Score':<8} {'Rating':<16} {'Exp':<8}")
    print("  " + "-" * 66)
    for rank, cand in enumerate(ranked_candidates, start=1):
        print(
            f"  #{rank:<4} {cand.candidate_name:<22} {cand.overall_score:<7.1f}% "
            f"{cand.rating_label:<16} {cand.resume_profile.total_experience_years:.1f} yrs"
        )
        print(f"       Matched: {', '.join(cand.top_matched_skills[:5])}")
        print(f"       Missing: {', '.join(cand.top_missing_skills[:4]) or 'None'}")
    print("  " + "-" * 66)

    # Export Recruiter PDF
    recruiter_pdf_path = OUTPUT_DIR / "recruiter_shortlist_report.pdf"
    generate_recruiter_report(ranked_candidates, job_title=parsed_jd.title, output_target=recruiter_pdf_path)
    print(f"  [OK] Exported Recruiter Report PDF: {recruiter_pdf_path} ({recruiter_pdf_path.stat().st_size} bytes)")

    # 4. Candidate Mode: Gap Analysis on Sam Rivera (Junior Frontend seeking Senior Python role)
    print("\n[4/5] Running Candidate Mode Gap Analysis (Sam Rivera)...")
    sam_file = SAMPLE_DIR / "sam_rivera_junior_frontend.txt"
    sam_text = parse_resume(sam_file)
    sam_profile = parse_resume_to_profile(sam_text)
    sam_breakdown = matcher.match(sam_profile, parsed_jd)
    gap_report = generate_gap_analysis(sam_profile, parsed_jd, sam_breakdown)

    print(f"  [OK] Candidate: {gap_report.candidate_name}")
    print(f"  [OK] Target Role: {gap_report.target_role}")
    print(f"  [OK] Overall Match: {gap_report.overall_match_percentage:.1f}%")
    print(f"  [OK] Matched Skills ({len(gap_report.matched_skills)}): {', '.join(gap_report.matched_skills)}")
    print(f"  [OK] Missing Required Skills ({len(gap_report.missing_required_skills)}): {', '.join(gap_report.missing_required_skills)}")
    print(f"  [OK] Actionable Suggestions ({len(gap_report.suggestions)}):")
    for i, s in enumerate(gap_report.suggestions, start=1):
        print(f"     [{s.priority}] {i}. {s.title}: {s.description[:80]}...")

    # Export Candidate PDF
    candidate_pdf_path = OUTPUT_DIR / "candidate_improvement_report.pdf"
    generate_candidate_report(gap_report, sam_breakdown, output_target=candidate_pdf_path)
    print(f"  [OK] Exported Candidate Report PDF: {candidate_pdf_path} ({candidate_pdf_path.stat().st_size} bytes)")

    # 5. Validation Check
    print("\n[5/5] Validating Artifacts & Deliverables...")
    assert recruiter_pdf_path.exists() and recruiter_pdf_path.stat().st_size > 2000, "Recruiter PDF invalid"
    assert candidate_pdf_path.exists() and candidate_pdf_path.stat().st_size > 2000, "Candidate PDF invalid"
    assert recruiter_pdf_path.read_bytes().startswith(b"%PDF"), "Recruiter file header invalid"
    assert candidate_pdf_path.read_bytes().startswith(b"%PDF"), "Candidate file header invalid"
    print("  [OK] All PDF exports verified successfully!")
    print("\n[+] VERIFICATION COMPLETE: ALL SYSTEMS FUNCTIONAL!")


if __name__ == "__main__":
    main()
