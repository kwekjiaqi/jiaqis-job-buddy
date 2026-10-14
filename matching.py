"""Transparent, conservative candidate-to-role triage. Not a hiring prediction."""

import re
from dataclasses import dataclass

from engine import analyze
from jobs import Job


@dataclass(frozen=True)
class Profile:
    role_terms: tuple[str, ...]
    domain_terms: tuple[str, ...]
    years: int
    minimum_pay: int | None
    currency: str = "SGD"


@dataclass(frozen=True)
class Assessment:
    job: Job
    recommendation: str
    rank: int
    reasons: tuple[str, ...]
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]


def terms(value: str) -> tuple[str, ...]:
    return tuple(x.strip().lower() for x in value.split(",") if x.strip())[:8]


def contains(text: str, term: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I))


def required_years(description: str) -> int | None:
    # This extracts only explicit, nearby experience phrasing; many ads are ambiguous.
    patterns = [r"\b(\d{1,2})\+?\s*(?:years|yrs)\s+(?:of\s+)?(?:relevant\s+)?experience\b",
                r"\b(?:at least|minimum of)\s+(\d{1,2})\s*(?:years|yrs)\b"]
    found = [int(m.group(1)) for p in patterns for m in re.finditer(p, description, re.I)]
    return max(found) if found else None


def salary_bounds(salary: str, currency: str) -> tuple[int, int] | None:
    # No conversion between currencies; ambiguous or nonannual pay stays unknown.
    if re.search(r"\b(?:hour|hourly|month|monthly|day|daily)\b", salary, re.I):
        return None
    if currency == "SGD":
        if not re.search(r"\bSGD\b|S\$", salary, re.I):
            return None
        amounts = re.findall(r"(?:SGD\s*|S\$)\s*(\d{2,3})(?:,?(\d{3})|(?:\.\d+)?\s*([kK]))?", salary, re.I)
    elif currency == "USD":
        if re.search(r"\bSGD\b|S\$", salary, re.I):
            return None
        amounts = re.findall(r"(?:USD\s*|\$)\s*(\d{2,3})(?:,?(\d{3})|(?:\.\d+)?\s*([kK]))?", salary, re.I)
    else:
        return None
    numbers = []
    for whole, thousands, k in amounts:
        n = int(whole + thousands) if thousands else int(whole) * (1000 if k else 1)
        if n >= 10000:
            numbers.append(n)
    return (min(numbers), max(numbers)) if numbers else None


def assess(job: Job, cv: str, profile: Profile) -> Assessment:
    reasons: list[str] = []
    hard_skip = False
    uncertain = False
    title_match = not profile.role_terms or any(contains(job.title, t) for t in profile.role_terms)
    if not title_match:
        reasons.append("Function: target role term not in job title")
        hard_skip = True
    else:
        reasons.append("Function: title matches target")
    domain_text = f"{job.title} {job.category} {job.description}"
    domain_match = not profile.domain_terms or any(contains(domain_text, t) for t in profile.domain_terms)
    if not domain_match:
        reasons.append("Domain: target term not found in listing")
        hard_skip = True
    else:
        reasons.append("Domain: target term found")

    evidence = analyze(job.description, cv)
    matched = tuple(x.skill for x in evidence["evidenced"])
    missing = tuple(x.skill for x in evidence["not_evidenced"])
    total = len(matched) + len(missing)
    coverage = len(matched) / total if total else 0.0
    if total == 0:
        reasons.append("Skills: no supported requirements detected; needs manual review")
        uncertain = True
    elif coverage < .5:
        reasons.append(f"Skills: {len(matched)}/{total} supported terms evidenced in CV")
        uncertain = True
    else:
        reasons.append(f"Skills: {len(matched)}/{total} supported terms evidenced in CV")

    years = required_years(job.description)
    if years is None:
        reasons.append("Experience: minimum years not explicit")
        uncertain = True
    elif profile.years < years:
        reasons.append(f"Experience: listing asks {years}+ years; profile says {profile.years}")
        hard_skip = True
    else:
        reasons.append(f"Experience: {profile.years} years meets {years}+ stated minimum")

    if profile.minimum_pay is not None:
        bounds = salary_bounds(job.salary, profile.currency)
        if bounds is None:
            reasons.append(f"Compensation: comparable annual {profile.currency} range unavailable; verify on listing")
            uncertain = True
        elif bounds[1] < profile.minimum_pay:
            reasons.append(f"Compensation: listed maximum {profile.currency} {bounds[1]:,} below your {profile.minimum_pay:,} minimum")
            hard_skip = True
        elif bounds[0] < profile.minimum_pay:
            reasons.append("Compensation: range overlaps your minimum; verify level and offer")
            uncertain = True
        else:
            reasons.append("Compensation: listed range meets your minimum")

    decision = "Skip" if hard_skip else "Review" if uncertain else "Apply"
    # Rank is a sorting aid, not a probability or candidate quality score.
    rank = (30 if title_match else 0) + (20 if domain_match else 0) + round(30 * coverage) + (10 if years is not None and profile.years >= years else 0)
    bounds = salary_bounds(job.salary, profile.currency)
    if profile.minimum_pay is not None and bounds and bounds[1] >= profile.minimum_pay:
        rank += 10
    return Assessment(job, decision, rank, tuple(reasons), matched, missing)


def shortlist(jobs: list[Job], cv: str, profile: Profile, limit: int = 10) -> list[Assessment]:
    unique = {j.id or j.url or j.title + j.company: j for j in jobs}
    eligible = [j for j in unique.values() if j.description
                and (not profile.role_terms or any(contains(j.title, t) for t in profile.role_terms))
                and (not profile.domain_terms or any(contains(f"{j.title} {j.category} {j.description}", t) for t in profile.domain_terms))]
    rows = [assess(job, cv, profile) for job in eligible]
    # Prefer actionable listings, then transparent relevance rank; skip roles remain visible if <10 others.
    priority = {"Apply": 2, "Review": 1, "Skip": 0}
    return sorted(rows, key=lambda x: (priority[x.recommendation], x.rank), reverse=True)[:limit]
