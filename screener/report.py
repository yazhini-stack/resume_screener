"""PDF Report Generation using ReportLab for Recruiter Shortlists and Candidate Improvement Reports.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from screener.gap_analysis import GapAnalysisReport
from screener.logger import get_logger
from screener.scorer import ScreeningResult

logger = get_logger(__name__)


def _build_styles():
    """Build standardized, elegant ReportLab paragraph styles."""
    styles = getSampleStyleSheet()

    # Modify / Add custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        alignment=0,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=12,
    )

    heading1_style = ParagraphStyle(
        "CustomH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=14,
        spaceAfter=8,
    )

    heading2_style = ParagraphStyle(
        "CustomH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
    )

    table_header_style = ParagraphStyle(
        "CustomTableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )

    table_cell_style = ParagraphStyle(
        "CustomTableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E293B"),
    )

    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"),
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "h1": heading1_style,
        "h2": heading2_style,
        "body": body_style,
        "table_header": table_header_style,
        "table_cell": table_cell_style,
        "badge": badge_style,
    }


def generate_recruiter_report(
    results: List[ScreeningResult],
    job_title: str,
    output_target: Optional[Union[str, Path, io.BytesIO]] = None,
) -> bytes:
    """Generate a recruiter-focused candidate ranking and shortlist PDF.

    Args:
        results: Ranked list of ScreeningResults.
        job_title: Title of the target role.
        output_target: File path or BytesIO buffer. If None, returns raw bytes.

    Returns:
        PDF document bytes.
    """
    buffer = io.BytesIO() if output_target is None or isinstance(output_target, (str, Path)) else output_target
    doc = SimpleDocTemplate(
        buffer if output_target is None or not isinstance(output_target, (str, Path)) else str(output_target),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = _build_styles()
    story = []

    # Title & Metadata
    story.append(Paragraph("Candidate Screening & Ranking Shortlist", styles["title"]))
    now_str = datetime.now().strftime("%B %d, %Y - %I:%M %p")
    story.append(Paragraph(f"Target Role: <b>{job_title}</b> | Generated: {now_str}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=14))

    # Executive Metrics Summary Table
    total_screened = len(results)
    avg_score = round(sum(r.overall_score for r in results) / total_screened, 1) if total_screened else 0.0
    top_candidate = results[0].candidate_name if total_screened else "N/A"
    top_score = f"{results[0].overall_score:.1f}%" if total_screened else "N/A"

    summary_data = [
        [
            Paragraph("<b>Total Candidates</b>", styles["body"]),
            Paragraph(f"<b>{total_screened}</b>", styles["body"]),
            Paragraph("<b>Average Match Score</b>", styles["body"]),
            Paragraph(f"<b>{avg_score}%</b>", styles["body"]),
        ],
        [
            Paragraph("<b>Top Ranked Candidate</b>", styles["body"]),
            Paragraph(f"<b>{top_candidate}</b>", styles["body"]),
            Paragraph("<b>Highest Score</b>", styles["body"]),
            Paragraph(f"<b>{top_score}</b>", styles["body"]),
        ]
    ]
    summary_table = Table(summary_data, colWidths=[1.8 * inch, 1.8 * inch, 1.8 * inch, 1.8 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Main Candidates Table
    story.append(Paragraph("Ranked Candidate Leaderboard", styles["h1"]))

    table_data = [
        [
            Paragraph("<b>Rank</b>", styles["table_header"]),
            Paragraph("<b>Candidate Name</b>", styles["table_header"]),
            Paragraph("<b>Match %</b>", styles["table_header"]),
            Paragraph("<b>Rating</b>", styles["table_header"]),
            Paragraph("<b>Exp (Yrs)</b>", styles["table_header"]),
            Paragraph("<b>Top Matched Skills</b>", styles["table_header"]),
            Paragraph("<b>Missing Critical Skills</b>", styles["table_header"]),
        ]
    ]

    for idx, r in enumerate(results, start=1):
        matched_str = ", ".join(r.top_matched_skills[:4]) or "None identified"
        missing_str = ", ".join(r.top_missing_skills[:3]) or "None (Full match)"
        exp_str = f"{r.resume_profile.total_experience_years:.1f}y"

        score_color = "#15803D" if r.overall_score >= 80 else ("#B45309" if r.overall_score >= 60 else "#B91C1C")
        score_cell = f"<font color='{score_color}'><b>{r.overall_score:.1f}%</b></font>"

        table_data.append([
            Paragraph(f"#{idx}", styles["table_cell"]),
            Paragraph(f"<b>{r.candidate_name}</b><br/><font color='#64748B'>{r.filename}</font>", styles["table_cell"]),
            Paragraph(score_cell, styles["table_cell"]),
            Paragraph(r.rating_label, styles["table_cell"]),
            Paragraph(exp_str, styles["table_cell"]),
            Paragraph(matched_str, styles["table_cell"]),
            Paragraph(missing_str, styles["table_cell"]),
        ])

    cand_table = Table(
        table_data,
        colWidths=[0.5 * inch, 1.5 * inch, 0.8 * inch, 1.0 * inch, 0.7 * inch, 1.4 * inch, 1.4 * inch]
    )
    cand_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(cand_table)
    story.append(Spacer(1, 16))

    # Top Candidate Details Spotlight
    story.append(Paragraph("Top Candidates In-Depth Highlights", styles["h1"]))
    for top_res in results[:3]:
        details = [
            Paragraph(f"<b>{top_res.candidate_name}</b> - Match: {top_res.overall_score:.1f}% ({top_res.rating_label})", styles["h2"]),
            Paragraph(
                f"<b>Contact:</b> {top_res.resume_profile.email or 'N/A'} | {top_res.resume_profile.phone or 'N/A'} | "
                f"<b>Experience:</b> {top_res.resume_profile.total_experience_years:.1f} years | "
                f"<b>Degrees:</b> {', '.join(top_res.resume_profile.degrees) or 'Not explicitly listed'}",
                styles["body"],
            ),
            Spacer(1, 3),
            Paragraph(
                f"<b>Score Breakdown:</b> Skills: {top_res.breakdown.skills_score:.1f}% | "
                f"Experience: {top_res.breakdown.experience_score:.1f}% | "
                f"Education: {top_res.breakdown.education_score:.1f}% | "
                f"Semantic: {top_res.breakdown.semantic_score:.1f}%",
                styles["body"],
            ),
            Spacer(1, 3),
            Paragraph(
                f"<b>Identified Skills:</b> {', '.join(top_res.breakdown.matched_skills + top_res.breakdown.additional_skills)[:160]}...",
                styles["body"],
            ),
            Spacer(1, 6),
            HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=8),
        ]
        story.append(KeepTogether(details))

    doc.build(story)

    if output_target is None:
        return buffer.getvalue()
    elif isinstance(output_target, (str, Path)):
        return Path(output_target).read_bytes()
    else:
        return buffer.getvalue()


def generate_candidate_report(
    gap_report: GapAnalysisReport,
    breakdown: MatchBreakdown,
    output_target: Optional[Union[str, Path, io.BytesIO]] = None,
) -> bytes:
    """Generate a personalized resume improvement and gap analysis PDF report for a job seeker.

    Args:
        gap_report: GapAnalysisReport with suggestions.
        breakdown: MatchBreakdown scores.
        output_target: File path or BytesIO buffer. If None, returns raw bytes.

    Returns:
        PDF document bytes.
    """
    buffer = io.BytesIO() if output_target is None or isinstance(output_target, (str, Path)) else output_target
    doc = SimpleDocTemplate(
        buffer if output_target is None or not isinstance(output_target, (str, Path)) else str(output_target),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = _build_styles()
    story = []

    # Title & Target Role
    story.append(Paragraph("Candidate Resume Match & Gap Analysis Report", styles["title"]))
    now_str = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(f"Candidate: <b>{gap_report.candidate_name}</b> | Target Role: <b>{gap_report.target_role}</b> | Date: {now_str}", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0D9488"), spaceAfter=14))

    # Match Score Spotlight Box
    score = gap_report.overall_match_percentage
    score_color = "#15803D" if score >= 80 else ("#B45309" if score >= 60 else "#B91C1C")
    badge_label = "Strong Match" if score >= 70 else ("Moderate Fit" if score >= 50 else "Growth Opportunities")

    match_box_data = [
        [
            Paragraph(f"<font size=28 color='{score_color}'><b>{score:.1f}%</b></font><br/><b>Overall Match Score</b>", styles["badge"]),
            Paragraph(
                f"<b>Status: {badge_label}</b><br/>"
                f"This report highlights the strengths of your resume against this job posting "
                f"and outlines concrete, prioritized steps to maximize your interview chances.",
                styles["body"],
            ),
        ]
    ]
    match_box = Table(match_box_data, colWidths=[2.2 * inch, 5.0 * inch])
    match_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4" if score >= 70 else "#FEF3C7")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#86EFAC" if score >= 70 else "#FDE68A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(match_box)
    story.append(Spacer(1, 14))

    # Score Breakdown Table
    story.append(Paragraph("Category Score Breakdown", styles["h1"]))
    score_breakdown_data = [
        [
            Paragraph("<b>Category</b>", styles["table_header"]),
            Paragraph("<b>Score</b>", styles["table_header"]),
            Paragraph("<b>Assessment & Context</b>", styles["table_header"]),
        ],
        [
            Paragraph("<b>Skills Match</b>", styles["table_cell"]),
            Paragraph(f"<b>{breakdown.skills_score:.1f}%</b>", styles["table_cell"]),
            Paragraph(f"Matched {len(gap_report.matched_skills)} skills required or preferred by the role.", styles["table_cell"]),
        ],
        [
            Paragraph("<b>Experience Match</b>", styles["table_cell"]),
            Paragraph(f"<b>{breakdown.experience_score:.1f}%</b>", styles["table_cell"]),
            Paragraph(f"Resume shows ~{breakdown.candidate_experience_years:.1f} yrs vs {breakdown.required_experience_years:.0f} yrs requested.", styles["table_cell"]),
        ],
        [
            Paragraph("<b>Education Match</b>", styles["table_cell"]),
            Paragraph(f"<b>{breakdown.education_score:.1f}%</b>", styles["table_cell"]),
            Paragraph(f"Degree level: {', '.join(breakdown.candidate_degrees) or 'Not stated'} vs {breakdown.required_education or 'Flexible'}.", styles["table_cell"]),
        ],
        [
            Paragraph("<b>Semantic Relevance</b>", styles["table_cell"]),
            Paragraph(f"<b>{breakdown.semantic_score:.1f}%</b>", styles["table_cell"]),
            Paragraph("TF-IDF semantic vocabulary alignment with the job description.", styles["table_cell"]),
        ],
    ]
    breakdown_table = Table(score_breakdown_data, colWidths=[1.8 * inch, 1.0 * inch, 4.4 * inch])
    breakdown_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0D9488")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 14))

    # Skills Comparison (Matched vs Missing)
    story.append(Paragraph("Skills Overlap Comparison", styles["h1"]))

    skills_data = [
        [
            Paragraph("<font color='#166534'><b>Matched Skills (Present in Resume)</b></font>", styles["body"]),
            Paragraph("<font color='#991B1B'><b>Missing Required Skills (From JD)</b></font>", styles["body"]),
        ],
        [
            Paragraph(", ".join(gap_report.matched_skills) or "None explicitly matched", styles["body"]),
            Paragraph(", ".join(gap_report.missing_required_skills) or "None (All required skills present!)", styles["body"]),
        ],
    ]
    if gap_report.missing_preferred_skills:
        skills_data.append([
            Paragraph("<b>Additional Resume Skills:</b>", styles["body"]),
            Paragraph("<font color='#92400E'><b>Missing Preferred / Bonus Skills:</b></font>", styles["body"]),
        ])
        skills_data.append([
            Paragraph(", ".join(gap_report.additional_skills[:10]) or "None", styles["body"]),
            Paragraph(", ".join(gap_report.missing_preferred_skills) or "None", styles["body"]),
        ])

    skills_table = Table(skills_data, colWidths=[3.6 * inch, 3.6 * inch])
    skills_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(skills_table)
    story.append(Spacer(1, 16))

    # Actionable Improvement Recommendations
    story.append(Paragraph("Prioritized Recommendations & Suggestions", styles["h1"]))

    if not gap_report.suggestions:
        story.append(Paragraph("Outstanding match! No major gaps detected.", styles["body"]))
    else:
        for i, sug in enumerate(gap_report.suggestions, start=1):
            pri_color = "#DC2626" if sug.priority == "High" else ("#D97706" if sug.priority == "Medium" else "#2563EB")
            item = [
                Paragraph(
                    f"<b>{i}. {sug.title}</b> &nbsp;&nbsp;"
                    f"<font color='{pri_color}'><b>[{sug.priority} Priority - {sug.category}]</b></font>",
                    styles["h2"]
                ),
                Paragraph(sug.description, styles["body"]),
                Spacer(1, 4),
            ]
            story.append(KeepTogether(item))

    doc.build(story)

    if output_target is None:
        return buffer.getvalue()
    elif isinstance(output_target, (str, Path)):
        return Path(output_target).read_bytes()
    else:
        return buffer.getvalue()
