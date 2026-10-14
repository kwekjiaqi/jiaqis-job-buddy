"""Document extraction and evidence-preserving tailoring."""

from io import BytesIO


def read_cv(name: str, data: bytes) -> str:
    if len(data) > 2_000_000:
        raise ValueError("Keep the CV below 2 MB.")
    name = name.lower()
    if name.endswith(".txt"):
        result = data.decode("utf-8-sig", errors="replace")
    elif name.endswith(".pdf"):
        from pypdf import PdfReader
        result = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages[:10])
    elif name.endswith(".docx"):
        from docx import Document
        result = "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)
    else:
        raise ValueError("Upload a TXT, PDF, or DOCX file.")
    if len(result.strip()) < 30:
        raise ValueError("Could not extract enough text. Scanned PDFs may need OCR; paste the text instead.")
    return result[:20000]


def tailor_cv(cv: str, job_description: str, job_title: str) -> str:
    """Moves supported CV lines into a targeted highlights section without rewriting claims."""
    from engine import analyze

    findings = analyze(job_description, cv)["evidenced"]
    lines = list(dict.fromkeys(x.resume_evidence for x in findings if x.resume_evidence))
    skills = ", ".join(x.skill for x in findings) or "No verified skill keywords found"
    highlights = "\n".join("- " + line for line in lines[:6]) or "- Add a real example relevant to this role."
    return (f"TARGET ROLE: {job_title}\n"
            f"RELEVANT SKILLS FROM ORIGINAL CV: {skills}\n\n"
            f"SELECTED EXPERIENCE FROM ORIGINAL CV\n{highlights}\n\n"
            "FULL ORIGINAL CV (edit and format before applying)\n\n" + cv.strip())
