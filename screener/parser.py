"""Resume and document parser module.

Supports PDF (via pdfplumber/pypdf), DOCX (via python-docx), and plain text.
Detects scanned/image-only documents and handles corrupted formats gracefully.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO, Union

import docx
import pdfplumber
import pypdf

from screener.logger import get_logger

logger = get_logger(__name__)


class ResumeParserError(Exception):
    """Base exception for resume parsing errors."""
    pass


class ScannedResumeError(ResumeParserError):
    """Raised when a resume appears to be an image-only or scanned PDF without text."""
    pass


class UnsupportedFormatError(ResumeParserError):
    """Raised when an unsupported file format is provided."""
    pass


class CorruptedResumeError(ResumeParserError):
    """Raised when a file cannot be read or is corrupted."""
    pass


def clean_extracted_text(text: str) -> str:
    """Normalize whitespace and strip unprintable characters from text."""
    if not text:
        return ""
    # Replace non-breaking spaces and unusual whitespace
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Replace consecutive blank lines with at most two newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace multi-spaces with single space
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def is_image_only_or_empty(text: str, min_words: int = 15) -> bool:
    """Check if the extracted text has too few words, indicating a scanned or empty file."""
    words = re.findall(r"\b[A-Za-z0-9]{2,}\b", text)
    return len(words) < min_words


def extract_text_from_pdf(source: Union[str, Path, BinaryIO, bytes]) -> str:
    """Extract selectable text from a PDF file using pdfplumber with pypdf fallback."""
    raw_text_parts: list[str] = []

    # Prepare byte stream
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if not source_path.exists():
            raise CorruptedResumeError(f"File not found: {source}")
        file_bytes = source_path.read_bytes()
    elif isinstance(source, bytes):
        file_bytes = source
    elif hasattr(source, "read"):
        file_bytes = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
    else:
        raise UnsupportedFormatError(f"Unsupported source type: {type(source)}")

    if not file_bytes:
        raise CorruptedResumeError("Empty file content.")

    # 1. Attempt extraction with pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise CorruptedResumeError("PDF has no pages.")
            for page_idx, page in enumerate(pdf.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    raw_text_parts.append(page_text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed, falling back to pypdf: {e}")
        raw_text_parts.clear()

    # 2. Fallback to pypdf if pdfplumber didn't yield sufficient text
    if not raw_text_parts:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                t = page.extract_text() or ""
                if t.strip():
                    raw_text_parts.append(t)
        except Exception as e:
            raise CorruptedResumeError(f"Failed to read PDF: {e}") from e

    full_text = clean_extracted_text("\n\n".join(raw_text_parts))

    if is_image_only_or_empty(full_text):
        raise ScannedResumeError(
            "The resume appears to be scanned or image-only without selectable text. "
            "Please provide a text-selectable PDF or DOCX file."
        )

    return full_text


def extract_text_from_docx(source: Union[str, Path, BinaryIO, bytes]) -> str:
    """Extract text from a DOCX file using python-docx."""
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if not source_path.exists():
            raise CorruptedResumeError(f"File not found: {source}")
        file_stream: BinaryIO = io.BytesIO(source_path.read_bytes())
    elif isinstance(source, bytes):
        file_stream = io.BytesIO(source)
    elif hasattr(source, "read"):
        content = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
        file_stream = io.BytesIO(content)
    else:
        raise UnsupportedFormatError(f"Unsupported source type: {type(source)}")

    try:
        doc = docx.Document(file_stream)
        paragraphs: list[str] = [p.text for p in doc.paragraphs if p.text.strip()]
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    paragraphs.append(" | ".join(row_text))

        full_text = clean_extracted_text("\n".join(paragraphs))

        if is_image_only_or_empty(full_text):
            raise ScannedResumeError(
                "The DOCX file contains little or no text. Please verify the document content."
            )
        return full_text
    except ScannedResumeError:
        raise
    except Exception as e:
        raise CorruptedResumeError(f"Failed to read DOCX file: {e}") from e


def extract_text_from_txt(source: Union[str, Path, BinaryIO, bytes]) -> str:
    """Extract text from a plain text file or stream."""
    if isinstance(source, (str, Path)):
        source_path = Path(source)
        if not source_path.exists():
            raise CorruptedResumeError(f"File not found: {source}")
        raw_bytes = source_path.read_bytes()
    elif isinstance(source, bytes):
        raw_bytes = source
    elif hasattr(source, "read"):
        raw_bytes = source.read()
        if hasattr(source, "seek"):
            source.seek(0)
    else:
        raise UnsupportedFormatError(f"Unsupported source type: {type(source)}")

    for encoding in ("utf-8", "latin-1", "cp1252", "utf-16"):
        try:
            text = raw_bytes.decode(encoding)
            clean = clean_extracted_text(text)
            if is_image_only_or_empty(clean):
                raise ScannedResumeError("The text document contains no readable content.")
            return clean
        except UnicodeDecodeError:
            continue

    raise CorruptedResumeError("Unable to decode text document with standard encodings.")


def parse_resume(source: Union[str, Path, BinaryIO, bytes], filename: str = "") -> str:
    """Auto-detect file format by extension or header and extract text.

    Args:
        source: File path, byte stream, or bytes.
        filename: Optional filename hint to determine format.

    Returns:
        Cleaned, extracted text string.
    """
    fn = filename
    if not fn and isinstance(source, (str, Path)):
        fn = Path(source).name

    fn_lower = fn.lower()

    if fn_lower.endswith(".pdf"):
        return extract_text_from_pdf(source)
    elif fn_lower.endswith(".docx"):
        return extract_text_from_docx(source)
    elif fn_lower.endswith((".txt", ".md", ".rtf")):
        return extract_text_from_txt(source)
    elif not fn_lower:
        # Probe magic bytes
        if isinstance(source, (str, Path)):
            probe = Path(source).read_bytes()[:10]
        elif isinstance(source, bytes):
            probe = source[:10]
        elif hasattr(source, "read"):
            probe = source.read(10)
            if hasattr(source, "seek"):
                source.seek(0)
        else:
            probe = b""

        if probe.startswith(b"%PDF"):
            return extract_text_from_pdf(source)
        elif probe.startswith(b"PK\x03\x04"):
            return extract_text_from_docx(source)
        else:
            return extract_text_from_txt(source)
    else:
        raise UnsupportedFormatError(
            f"Unsupported file format '{fn}'. Supported formats: PDF, DOCX, TXT."
        )
