"""Build human-reviewed LinkedIn searches; never scrape or invent people."""

from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlparse


@dataclass(frozen=True)
class LeadSearch:
    label: str
    reason: str
    url: str


def linkedin_people_search(query: str) -> str:
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(query[:180])


def linkedin_job_search(function: str, domain: str, city: str) -> str:
    return "https://www.linkedin.com/jobs/search/?" + urlencode({
        "keywords": f"{function} {domain} on-site"[:160], "location": city[:80]})


def validated_job_url(value: str) -> str | None:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}:
        return None
    if not parsed.path.startswith("/jobs/view/") or len(parsed.path) <= len("/jobs/view/"):
        return None
    return value.strip()


def lead_searches(company: str, city: str, function: str, schools: str = "", employers: str = "") -> list[LeadSearch]:
    base = f'"{company}" "{city}"'
    search = [
        LeadSearch("Possible hiring leaders", "Look for managers or directors in the target function; confirm they work on this team.",
                   linkedin_people_search(base + f' "{function}" (manager OR director OR head)')),
        LeadSearch("Same function locally", "Look for colleagues doing similar work in the same region.",
                   linkedin_people_search(base + f' "{function}"')),
    ]
    for school in [x.strip() for x in schools.split(",") if x.strip()][:2]:
        search.append(LeadSearch(f"Shared school: {school}", "Confirm the school and current employer on the profile.",
                                 linkedin_people_search(base + f' "{school}"')))
    for employer in [x.strip() for x in employers.split(",") if x.strip()][:2]:
        search.append(LeadSearch(f"Shared former employer: {employer}", "Confirm previous employment before mentioning a connection.",
                                 linkedin_people_search(base + f' "{employer}"')))
    return search


def validated_profile_url(value: str) -> str | None:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}:
        return None
    if not parsed.path.startswith("/in/") or len(parsed.path) <= 4:
        return None
    return value.strip()


def outreach_draft(name: str, company: str, job_title: str, reason: str, evidenced_skills: tuple[str, ...] = ()) -> str:
    """Draft a note from a manually verified contact and CV-backed skill only."""
    def clean(value: str) -> str:
        return " ".join(value.split()).strip(" .")

    first_name = clean(name).split(" ")[0] or "there"
    connection = clean(reason)
    skill = clean(evidenced_skills[0]) if evidenced_skills else ""
    evidence_line = f"My CV includes work with {skill}. " if skill else ""
    return (f"Hi {first_name},\n\n"
            f"I'm exploring the {clean(job_title)} role at {clean(company)} and came across your profile. "
            f"Your background caught my attention because of {connection}. "
            f"{evidence_line}Would you be open to a brief chat about the work your team does?\n\n"
            "Thanks,\n[Your name]")
