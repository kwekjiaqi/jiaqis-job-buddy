"""Small, inspectable matching baseline for the Job Search Buddy demo."""

import re
from dataclasses import dataclass


# A deliberately limited vocabulary. Unknown requirements are surfaced as a limitation.
SKILLS = {
    "Python": (r"\bpython\b",),
    "SQL": (r"\bsql\b",),
    "Streamlit": (r"\bstreamlit\b",),
    "Data analysis": (r"\bdata analy(?:sis|tics)\b", r"\banaly[sz](?:e|ing|ed) data\b"),
    "Stakeholder workshops": (r"\bstakeholder workshop(?:s)?\b", r"\bworkshop facilitation\b", r"\bfacilitat(?:ed|ing) (?:client|stakeholder) (?:sessions|workshops)\b"),
    "AI evaluation": (r"\b(?:ai|llm|model) eval(?:uation|uations|s)?\b", r"\bevaluat(?:e|ed|ing) (?:an )?(?:ai|llm|model)\b", r"\b(?:tested|reviewed) (?:ai|llm|chatbot|model) outputs\b"),
    "Prompt engineering": (r"\bprompt engineering\b", r"\bprompt design\b", r"\bdesigned prompts\b"),
    "Cloud deployment": (r"\bcloud deploy(?:ment|ed|ing)?\b", r"\bdeploy(?:ment|ed|ing)? (?:on|to) (?:aws|azure|gcp|cloud)\b"),
    "Change management": (r"\bchange management\b",),
    "RAG": (r"\brag\b", r"\bretrieval.augmented generation\b"),
}


@dataclass(frozen=True)
class Finding:
    skill: str
    job_evidence: str
    resume_evidence: str | None


def _evidence(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            clause = re.split(r"[.;!?\n]", text[:match.start()])[-1]
            prefix = clause[-35:]
            suffix = text[match.end():match.end() + 25]
            if re.search(r"\b(?:no|without|never|not)\s+(?:\w+\s+){0,2}$", prefix, re.I):
                continue
            if re.match(r"\s+(?:experience\s*)?(?::\s*)?(?:none|not used|not yet)\b", suffix, re.I):
                continue
            # Show the relevant line, capped to prevent huge paragraphs in the UI.
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            end = len(text) if end == -1 else end
            line = " ".join(text[start:end].split())
            if len(line) > 200:
                a = max(0, match.start() - start - 65)
                line = "…" + line[a:a + 180] + "…"
            return line
    return None


def analyze(job: str, resume: str) -> dict[str, list[Finding]]:
    if not job.strip() or not resume.strip():
        raise ValueError("Add both a job description and résumé text.")
    if len(job) > 20000 or len(resume) > 20000:
        raise ValueError("Keep each input below 20,000 characters.")
    found: list[Finding] = []
    not_evidenced: list[Finding] = []
    for skill, patterns in SKILLS.items():
        job_quote = _evidence(job, patterns)
        if job_quote:
            resume_quote = _evidence(resume, patterns)
            item = Finding(skill, job_quote, resume_quote)
            (found if resume_quote else not_evidenced).append(item)
    return {"evidenced": found, "not_evidenced": not_evidenced}


def build_brief(result: dict[str, list[Finding]]) -> str:
    strengths = result["evidenced"][:3]
    questions = result["not_evidenced"][:3]
    lines = ["INTERVIEW PREP BRIEF", "", "Evidence you can discuss:"]
    lines.extend(f"- {x.skill}: {x.resume_evidence}" for x in strengths)
    if not strengths:
        lines.append("- None found in this limited skill vocabulary. Add more résumé detail.")
    lines.extend(["", "Questions to prepare (absence of text does not prove lack of skill):"])
    lines.extend(f"- {x.skill}: Can you give a real example? The role says: {x.job_evidence}" for x in questions)
    if not questions:
        lines.append("- No unmatched terms found in this limited vocabulary.")
    lines.extend(["", "Review every finding against the full documents before using it."])
    return "\n".join(lines)
