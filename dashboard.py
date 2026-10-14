"""Small, inspectable dashboard calculations and CSV restore."""

import csv
import io
from collections import Counter
from urllib.parse import urlparse


FIELDS = ("title", "company", "recommendation", "status", "source", "url")
STATUSES = {"New", "KIV", "Applied", "Rejected"}
LEGACY_STATUSES = {"Interested": "KIV", "Skipped": "Rejected"}
RECOMMENDATIONS = {"Apply", "Review", "Skip"}


def identity(title: str, company: str, url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return f"{parsed.hostname.casefold()}{parsed.path.rstrip('/').casefold()}"
    return f"{company.strip().casefold()}::{title.strip().casefold()}"


def merge_records(saved: list[dict[str, str]], current: list[dict[str, str]]) -> list[dict[str, str]]:
    """Current assessment and user status win over a restored copy of the role."""
    merged = {identity(row["title"], row["company"], row["url"]): row for row in saved}
    for row in current:
        merged[identity(row["title"], row["company"], row["url"])] = row
    return list(merged.values())


def change_status(records: list[dict[str, str]], target: dict[str, str], status: str) -> list[dict[str, str]]:
    """Update an imported role even when its original job listing is unavailable."""
    if status not in STATUSES:
        raise ValueError("Unknown pipeline status")
    key = identity(target["title"], target["company"], target["url"])
    return [dict(row, status=status) if identity(row["title"], row["company"], row["url"]) == key else row
            for row in records]


def parse_pipeline_csv(data: bytes) -> list[dict[str, str]]:
    if len(data) > 250_000:
        raise ValueError("Pipeline CSV is too large.")
    try:
        text = data.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise ValueError("This is not a Job Search Buddy pipeline CSV.")
        records = []
        for row in reader:
            if len(records) >= 500:
                raise ValueError("Pipeline CSV has too many rows.")
            item = {field: (row.get(field) or "").strip()[:300] for field in FIELDS}
            item["status"] = LEGACY_STATUSES.get(item["status"], item["status"])
            if not item["title"] or not item["company"] or item["status"] not in STATUSES or item["recommendation"] not in RECOMMENDATIONS:
                raise ValueError("Pipeline CSV contains an invalid role, status, or recommendation.")
            records.append(item)
        return merge_records([], records)
    except UnicodeError as exc:
        raise ValueError("Pipeline CSV must be UTF-8 text.") from exc


def summary(records: list[dict[str, str]], contact_count: int = 0) -> dict[str, int]:
    recommendations = Counter(row["recommendation"] for row in records)
    statuses = Counter(row["status"] for row in records)
    return {
        "shortlisted": len(records),
        "apply": recommendations["Apply"],
        "review": recommendations["Review"],
        "new": statuses["New"],
        "kiv": statuses["KIV"],
        "applied": statuses["Applied"],
        "rejected": statuses["Rejected"],
        "contacts": contact_count,
    }
