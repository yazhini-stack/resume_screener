# 📄 Resume Screener & Talent Matcher

A standalone, production-ready Python 3.10+ application for automated resume screening, semantic matching, taxonomy-based skill extraction, and career gap analysis.

Designed for both **Recruiters** (to bulk-screen, filter, rank candidates, and export shortlist PDFs) and **Job Seekers / Candidates** (to inspect match scores, identify skill gaps against target postings, and get concrete ATS optimization recommendations).

---

## 🌟 Key Features

### 👥 Recruiter Mode (Bulk Screening & Ranking)
- **Multi-Format Ingestion**: Upload multiple resumes in bulk (`.pdf`, `.docx`, `.txt`).
- **Automated Candidate Parsing**: Extracts candidate name, email, phone, web links, total experience years (from overlapping employment date ranges), degrees, and detected job titles.
- **Ranked Leaderboard**: Dynamic ranking based on composite score (skills, experience, education, semantic fit).
- **Interactive Multi-Level Filtering**:
  - Minimum years of experience threshold.
  - Mandatory "Must-Have" skill filter.
  - Search by candidate name or keyword.
- **Customizable Scoring Weights**: Select from preset weight profiles (*Balanced*, *Skills-Heavy*, *Experience-Centric*, *Academic/Degree-Focused*).
- **Candidate Drill-Down**: In-depth score component breakdown, matched vs missing skills, and category radar chart.
- **Recruiter Shortlist PDF Export**: Formatted executive report with statistics and ranked candidate table.

### 🎯 Candidate Mode (Gap Analysis & Actionable Insights)
- **Deep-Dive Single Resume Analysis**: Upload a resume against any target job posting.
- **Interactive Visualizations**:
  - Plotly Match Gauge (0-100%).
  - Multi-axis Category Radar Chart.
  - Skills Overlap & Distribution Stacked Bar.
- **Skill Gap Classification**:
  - Matched Skills (present in both).
  - Missing Required Skills (high-priority gaps).
  - Missing Preferred/Bonus Skills.
  - Additional Resume Skills.
- **Prioritized Actionable Improvement Suggestions**:
  - Specific missing required tools/frameworks.
  - Quantifiable metrics & achievement formula suggestions (XYZ framework).
  - Experience deficit mitigation advice.
  - ATS section header health checks.
  - Professional summary vocabulary tailoring.
- **Candidate Improvement Report PDF Export**: Formatted personalized improvement report ready for download.

### 🛡️ Robust Architecture & Edge Case Handling
- **Scanned / Image-Only Resume Detection**: Identifies image-only or non-text PDFs and alerts users with friendly, actionable guidance (`ScannedResumeError`).
- **Skills Taxonomy & Fuzzy Matching**: Pre-configured JSON taxonomy covering 104+ canonical skills across 10 categories with 260+ aliases. RapidFuzz handles minor spelling variations, and word-boundary rules prevent false matches for short terms like "C" or "Go".
- **spaCy NER**: Extracts organizations, academic degrees, and entities.
- **SQLite Database Persistence**: Automatically records all job descriptions, resumes, and screening results with an interactive history viewer.

---

## 📁 Project Structure

```
resume_screener/
├── app.py                      # Streamlit application entry point (both modes)
├── verify_screening.py         # End-to-end verification and demonstration script
├── requirements.txt            # Project dependencies
├── README.md                   # Setup and usage guide
├── screener/
│   ├── __init__.py             # Public package exports
│   ├── parser.py               # Extract text from PDF, DOCX, TXT with scanned resume detection
│   ├── sections.py             # Split sections, date calculation, degrees, job titles, contacts
│   ├── skills_extractor.py     # Skills taxonomy matching, alias resolution, RapidFuzz, spaCy NER
│   ├── jd_parser.py            # Job description parser (title, experience, required/preferred skills)
│   ├── matcher.py              # TF-IDF cosine similarity, skill overlap, exp/edu scoring
│   ├── scorer.py               # Composite match score calculation, weight profiles, candidate ranking
│   ├── gap_analysis.py         # Missing skills, prioritized resume improvement suggestions
│   ├── database.py             # SQLite persistence (job descriptions, resumes, match results)
│   ├── report.py               # ReportLab PDF generation (Recruiter & Candidate reports)
│   └── logger.py               # Standardized logging setup (console + file)
├── data/
│   ├── skills_taxonomy.json    # Editable skills taxonomy with synonyms and categories
│   ├── sample_job_description.txt # Realistic sample job description (Senior Cloud/Python)
│   ├── sample_resumes/         # Preloaded sample candidates in PDF, DOCX, and TXT formats
│   │   ├── alex_morgan_senior_python.pdf
│   │   ├── elena_rostova_data_scientist.docx
│   │   ├── sam_rivera_junior_frontend.txt
│   │   └── scanned_image_only_sample.pdf
│   └── resume_screener.db      # SQLite database file
├── outputs/                    # Exported PDF reports directory
├── logs/                       # Application logs (resume_screener.log)
└── tests/
    ├── __init__.py
    └── test_matcher.py         # Comprehensive pytest suite (18 unit & integration tests)
```

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.10, 3.12, and 3.14).
- `pip` package manager.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Download the spaCy English Model
```bash
python -m spacy download en_core_web_sm
```

---

## 🚀 Running the Application

### Launch Streamlit UI
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 📖 Usage Guide

### 👥 Recruiter Mode
1. Select **"👥 Recruiter Mode (Bulk Screening)"** from the sidebar.
2. In the **Job Description** section:
   - Paste job posting text, upload a file, or click **"Use Preloaded Sample JD"**.
3. In the **Candidate Resumes** section:
   - Upload one or multiple resumes (`.pdf`, `.docx`, `.txt`), or select **"Use Preloaded Sample Resumes"**.
4. (Optional) Adjust scoring weights under **"Advanced Scoring Weights & Settings"**.
5. Click **"🚀 Screen & Rank Candidates"**.
6. View the leaderboard table with match scores, experience, and key skills.
7. Use the sliders and dropdowns to filter by minimum experience or mandatory skills.
8. Click **"📄 Download Shortlist PDF Report"** to export an executive summary PDF.

### 🎯 Candidate Mode
1. Select **"🎯 Candidate Mode (Gap Analysis)"** from the sidebar.
2. Provide your resume (upload a file or choose one of the preloaded samples).
3. Provide the target job description (paste text, upload document, or use sample).
4. Click **"🔍 Analyze Resume Match & Find Gaps"**.
5. Review the **Overall Match Score gauge**, **Category Radar Chart**, and **Skills Distribution bar**.
6. Inspect the categorized skill tags (Matched, Missing Required, Missing Preferred, Extra).
7. Read the **Prioritized Actionable Suggestions** to optimize your resume for ATS and recruiters.
8. Click **"📄 Download My Personalized PDF Report"** to export the candidate report.

### 📜 Screening History
- Select **"📜 Screening History"** in the sidebar to review all past screening runs stored in SQLite, complete with date, candidate name, score, and target job.

### 📚 Skills Taxonomy Explorer
- Select **"📚 Skills Taxonomy Explorer"** to browse canonical skills and aliases across Programming Languages, Frameworks, Cloud, Databases, DevOps, Data & AI, and Soft Skills.

---

## 🧪 Running the Tests

To run the automated test suite:
```bash
python -m pytest tests/ -v
```

All 18 unit and integration tests validate:
- PDF text extraction (pdfplumber & pypdf fallback).
- DOCX and TXT text extraction.
- Scanned / image-only resume error detection.
- Name, email, phone, links, and degree extraction.
- Non-overlapping experience years calculation.
- Exact, alias, and fuzzy skill matching.
- Job description parsing (title, experience years, required/preferred skills).
- Matcher and scorer ranking correctness.
- Gap analysis and suggestion generation.
- SQLite database persistence.
- Recruiter and Candidate PDF generation.

---

## 🛠️ Verification Script

To execute an end-to-end command-line verification run:
```bash
python verify_screening.py
```
This script screens the 3 sample resumes against the sample job description, runs candidate gap analysis, and exports both PDF report types to the `outputs/` directory.
