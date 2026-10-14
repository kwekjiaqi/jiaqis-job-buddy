"""Fetch published jobs from selected public Greenhouse company boards."""

import html
import json
import re
from dataclasses import dataclass, replace
from urllib.parse import urlparse
from urllib.request import Request, urlopen


API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
DEFAULT_BOARDS = ("temus", "capco", "simplifynext")
LEVER_API = "https://api.lever.co/v0/postings/{site}?mode=json&limit=100"


@dataclass(frozen=True)
class Job:
    id: str
    title: str
    company: str
    category: str
    location: str
    salary: str
    description: str
    url: str
    source: str


def job_key(job: Job) -> str:
    """A posting URL identifies a role across board refreshes and query variants."""
    parsed = urlparse(job.url.strip())
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return f"url:{parsed.hostname.casefold()}{parsed.path.rstrip('/').casefold()}"
    return f"id:{job.source.casefold()}:{job.id}" if job.id else f"role:{job.company.casefold()}:{job.title.casefold()}:{job.location.casefold()}"


def merge_jobs(existing: dict[str, Job], incoming: list[Job]) -> tuple[dict[str, Job], int]:
    """Refresh listings, count only unseen postings, and retain IDs used for statuses."""
    merged = existing.copy()
    added = 0
    for job in incoming:
        key = job_key(job)
        if key in merged:
            job = replace(job, id=merged[key].id)
        else:
            added += 1
        merged[key] = job
    return merged, added


def plain_text(markup: str) -> str:
    markup = html.unescape(html.unescape(markup))
    markup = re.sub(r"(?is)<(script|style).*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<(?:br\s*/?|/p|/li|/div)>\s*", "\n", markup)
    return " ".join(re.sub(r"<[^>]+>", " ", markup).split())[:20000]


def is_in_person_location(location: str, city: str) -> bool:
    if not city.strip() or not location.strip():
        return False
    if re.search(r"\b(remote|anywhere|worldwide|work from home|wfh)\b", location, re.I):
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(city.strip()) + r"(?!\w)", location, re.I))


def from_record(raw: dict, board: str) -> Job:
    url = str(raw.get("absolute_url") or "")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"job-boards.greenhouse.io", "boards.greenhouse.io"}:
        url = ""
    description = plain_text(str(raw.get("content") or ""))
    location = raw.get("location") or {}
    location_name = str(location.get("name") or "") if isinstance(location, dict) else ""
    department = raw.get("departments") or []
    category = ", ".join(str(x.get("name", "")) for x in department if isinstance(x, dict))[:120]
    salary_match = re.search(r"(?:SGD\s*|S\$|USD\s*|(?<!S)\$)\s*\d[\d,.]*\s*[kK]?\s*(?:-|–|to)\s*(?:SGD\s*|S\$|USD\s*|(?<!S)\$)\s*\d[\d,.]*\s*[kK]?", description)
    salary = salary_match.group(0) if salary_match else ""
    if salary_match and re.search(r"\b(?:per month|monthly|per hour|hourly)\b", description[salary_match.end():salary_match.end()+40], re.I):
        salary += " per month or hour (check original listing)"
    return Job(id=f"{board}:{raw.get('id', '')}", title=str(raw.get("title") or "Untitled role")[:180],
               company=board.replace("-", " ").title(), category=category, location=location_name[:150],
               salary=salary, description=description, url=url, source=f"Greenhouse · {board}")


def fetch_jobs(boards: tuple[str, ...], city: str) -> tuple[list[Job], list[str]]:
    """Return only explicit local listings; skip unavailable boards with visible errors."""
    jobs: list[Job] = []
    errors: list[str] = []
    for board in boards[:8]:
        if not re.fullmatch(r"[a-z0-9-]{2,60}", board):
            errors.append(f"Invalid board token: {board[:60]}")
            continue
        try:
            request = Request(API.format(board=board), headers={"User-Agent": "JobSearchBuddyDemo/2.0"})
            with urlopen(request, timeout=10) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
                raise ValueError("Unexpected response")
            for raw in data["jobs"]:
                if not isinstance(raw, dict):
                    continue
                job = from_record(raw, board)
                if is_in_person_location(job.location, city) and job.url and job.description:
                    jobs.append(job)
        except Exception:
            errors.append(f"Could not load board: {board}")
    return jobs, errors


def fetch_lever_jobs(sites: tuple[str, ...], city: str) -> tuple[list[Job], list[str]]:
    """Read published Lever postings from user-selected public company sites."""
    jobs, errors = [], []
    for site in sites[:8]:
        if not re.fullmatch(r"[a-z0-9-]{2,60}", site):
            errors.append(f"Invalid Lever site: {site[:60]}")
            continue
        try:
            request = Request(LEVER_API.format(site=site), headers={"Accept": "application/json", "User-Agent": "JobSearchBuddyDemo/3.0"})
            with urlopen(request, timeout=10) as response:
                postings = json.load(response)
            if not isinstance(postings, list):
                raise ValueError("Unexpected response")
            for raw in postings:
                if not isinstance(raw, dict) or str(raw.get("workplaceType", "")).lower() == "remote":
                    continue
                categories = raw.get("categories") or {}
                if not isinstance(categories, dict):
                    categories = {}
                location = str(categories.get("location") or "")
                if not is_in_person_location(location, city):
                    continue
                url = str(raw.get("hostedUrl") or "")
                parsed = urlparse(url)
                if parsed.scheme != "https" or parsed.hostname not in {"jobs.lever.co", "jobs.eu.lever.co"}:
                    continue
                sections = raw.get("lists") or []
                details = " ".join(plain_text(str(x.get("content") or "")) for x in sections if isinstance(x, dict))
                description = (str(raw.get("descriptionPlain") or "") + " " + details).strip()[:20000]
                salary_range = raw.get("salaryRange") or {}
                salary = ""
                if isinstance(salary_range, dict) and salary_range.get("min") and salary_range.get("max"):
                    salary = f"{salary_range.get('currency','')} {salary_range['min']} - {salary_range.get('currency','')} {salary_range['max']}"
                    if salary_range.get("interval") and str(salary_range["interval"]).lower() not in {"year", "annual", "annually"}:
                        salary += f" per {salary_range['interval']}"
                if description:
                    jobs.append(Job(id=f"lever:{site}:{raw.get('id','')}", title=str(raw.get("text") or "Untitled role")[:180],
                                    company=site.replace("-", " ").title(), category=str(categories.get("team") or "")[:120],
                                    location=location[:150], salary=salary, description=description, url=url,
                                    source=f"Lever · {site}"))
        except Exception:
            errors.append(f"Could not load Lever site: {site}")
    return jobs, errors
