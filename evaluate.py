"""Offline evaluation: development regression cases plus separate holdout fixtures.

Run: python evaluate.py. These cases are a process demo, not a population sample.
"""

import json
import csv
import io
from unittest.mock import patch
from collections import Counter
from pathlib import Path

from cv import tailor_cv
from ai_review import request_payload, review_role, validate_review
from ai_workflow import discover_linkedin_links, draft_outreach, parse_cv, plan_leads, rank_leads, review_jobs, tailor_cv_with_ai
from dashboard import change_status, identity, merge_records, parse_pipeline_csv, summary
from engine import analyze
from jobs import Job, fetch_lever_jobs, from_record, is_in_person_location, merge_jobs
from matching import Profile, assess, salary_bounds, shortlist, terms
from outreach import lead_searches, linkedin_job_search, outreach_draft, validated_job_url, validated_profile_url
from sample_data import CV, demo_jobs


ROOT = Path(__file__).parent / "tests"


def check_cases(name: str) -> tuple[int, int]:
    cases = json.loads((ROOT / f"{name}.json").read_text())
    actuals = []
    passed = 0
    for i, case in enumerate(cases):
        job = Job(str(i), case["title"], "Example", case["category"], "Remote",
                  case["salary"], case["description"], "", "Fixture")
        result = assess(job, case["cv"], Profile(terms("consultant"), terms("AI"), case["years"], case["minimum_usd"], "USD"))
        actuals.append(result.recommendation)
        ok = result.recommendation == case["expected"]
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'} [{name}] {case['name']}: expected {case['expected']}, got {result.recommendation}")
    print(f"{name}: {passed}/{len(cases)} agreement; predicted distribution {dict(Counter(actuals))}")
    return passed, len(cases)


def check_invariants() -> None:
    assert "Python" not in {x.skill for x in analyze("Python required", "No Python experience")["evidenced"]}
    assert "SQL" not in {x.skill for x in analyze("SQL required", "NoSQL only")["evidenced"]}
    inferred = analyze("Stakeholder workshops required", "I facilitated stakeholder sessions for project planning")
    assert "Stakeholder workshops" in {x.skill for x in inferred["evidenced"]}
    draft = tailor_cv("I used Python on a project.", "Python and SQL required", "AI Consultant")
    assert "Python" in draft and "SQL" not in draft and "I used Python on a project." in draft
    assert from_record({"absolute_url": "javascript:alert(1)"}, "example").url == ""
    assert is_in_person_location("Singapore", "Singapore")
    assert not is_in_person_location("Singapore / Remote", "Singapore")
    assert not is_in_person_location("Remote - Singapore", "Singapore")
    assert not is_in_person_location("San Francisco, CA", "Singapore")
    assert salary_bounds("SGD 120k - SGD 160k", "SGD") == (120000, 160000)
    assert salary_bounds("SGD 15k - SGD 20k per month", "SGD") is None
    assert validated_profile_url("https://www.linkedin.com/in/sample-name/")
    assert not validated_profile_url("https://example.com/in/sample-name/")
    searches = lead_searches("Example Co", "Singapore", "AI Consultant", "Example University", "Former Co")
    assert len(searches) == 4 and all(x.url.startswith("https://www.linkedin.com/search/results/people/") for x in searches)
    note = outreach_draft("Alex Tan", "Example Co", "AI Consultant", "a shared consulting background", ("Python",))
    assert "Hi Alex" in note and "Python" in note and "SQL" not in note and "[Your name]" in note
    plain_note = outreach_draft("Alex Tan", "Example Co", "AI Consultant", "a shared school")
    assert "My CV includes" not in plain_note
    job_input = {"title": "AI Consultant", "company": "Example Co", "location": "Singapore",
                 "salary": "USD 120k - USD 160k", "description": "Python required. 4+ years of experience."}
    cv_input = "I used Python in client projects over six years."
    payload = request_payload(cv_input, job_input, {"target_city": "Singapore"})
    assert payload["store"] is False and payload["text"]["format"]["type"] == "json_schema"
    clean_review = {"decision": "Apply", "reason": "The CV lists Python.",
                    "cv_evidence": ["I used Python in client projects"],
                    "job_evidence": ["Python required"], "unknowns": []}
    assert validate_review(clean_review, cv_input, job_input["description"], "Apply")["decision"] == "Apply"
    tampered = dict(clean_review, cv_evidence=["I used Python in client projects", "I led SQL deployments"])
    checked = validate_review(tampered, cv_input, job_input["description"], "Apply")
    assert checked["decision"] == "Review" and checked["cv_evidence"] == ["I used Python in client projects"]
    assert validate_review(clean_review, cv_input, job_input["description"], "Skip")["decision"] == "Review"
    response_body = {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(clean_review)}]}]}
    with patch("ai_review.urlopen") as fake_call:
        fake_call.return_value.__enter__.return_value = io.BytesIO(json.dumps(response_body).encode())
        model_output = review_role("test-key", cv_input, job_input, {"target_city": "Singapore"}, "Apply")
        assert model_output["decision"] == "Apply"
        request = fake_call.call_args.args[0]
        assert request.full_url == "https://api.openai.com/v1/responses"
        assert json.loads(request.data)["store"] is False
    gemini_body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": json.dumps(clean_review)}]}}]}
    with patch("gemini_client.urlopen") as fake_gemini:
        fake_gemini.return_value.__enter__.return_value = io.BytesIO(json.dumps(gemini_body).encode())
        checked = review_role("test-key", cv_input, job_input, {}, "Apply", provider="Gemini")
        assert checked["decision"] == "Apply"
        request = fake_gemini.call_args.args[0]
        assert "gemini-2.5-flash:generateContent" in request.full_url
        gemini_payload = json.loads(request.data)
        assert gemini_payload["generationConfig"]["responseMimeType"] == "application/json"
        assert gemini_payload["generationConfig"]["responseJsonSchema"]["required"]
    with patch("gemini_client.urlopen") as fake_gemini:
        fake_gemini.return_value.__enter__.return_value = io.BytesIO(json.dumps({
            "candidates": [{"finishReason": "STOP", "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://www.linkedin.com/jobs/view/123/", "title": "Job"}},
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/redirect", "title": "LinkedIn"}},
                {"web": {"uri": "https://example.com/jobs/view/123/", "title": "Wrong host"}}]}}]
        }).encode())
        links = discover_linkedin_links("test-key", "jobs", "", "AI Consultant", "Singapore", provider="Gemini")
        assert len(links) == 1 and links[0]["url"].startswith("https://www.linkedin.com/")
        assert json.loads(fake_gemini.call_args.args[0].data)["tools"] == [{"google_search": {}}]
    with patch("ai_workflow.model_json", return_value={
        "functions": [{"name": "consultant", "quote": "Consultant"}],
        "domains": [{"name": "AI", "quote": "AI"}],
        "skills": [{"name": "Python", "quote": "Python"}, {"name": "SQL", "quote": "invented SQL"}],
        "schools": [], "employers": [], "years": 9, "years_quote": "invented nine years",
    }):
        parsed = parse_cv("test-key", "AI Consultant using Python")
        assert parsed["years"] == 0 and [x["name"] for x in parsed["skills"]] == ["Python"]
    item = Job("fixture:1", "AI Consultant", "Fixture Co", "AI", "Singapore", "", job_input["description"],
               "https://example.com/job/1", "Fixture")
    assessment = assess(item, cv_input, Profile(terms("consultant"), terms("AI"), 6, None))
    with patch("ai_workflow.model_json", return_value={"reviews": [dict(clean_review, job_id=item.id)]}):
        assert review_jobs("test-key", cv_input, [assessment], {})[item.id]["decision"] == "Apply"
    with patch("ai_workflow.model_json", return_value={
        "selected_cv_quotes": ["I used Python", "I built SQL engines"], "selected_skills": ["Python", "SQL"]}):
        tailored = tailor_cv_with_ai("test-key", cv_input, item.description, item.title)
        assert "I used Python" in tailored["draft"] and "I built SQL engines" not in tailored["draft"]
        assert "SQL" not in tailored["skills"]
    with patch("ai_workflow.model_json", return_value={"leads_to_find": [
        {"role": "Consulting manager", "why": "same function", "search_terms": "consulting manager"}]}):
        assert plan_leads("test-key", "Fixture Co", item.title, "Singapore", {})[0]["url"].startswith("https://www.linkedin.com/search/")
    contacts = [{"name": "Alex", "url": "https://www.linkedin.com/in/alex/", "employer": "Fixture Co",
                 "city": "Singapore", "title": "Manager", "reason": "same function"}]
    with patch("ai_workflow.model_json", return_value={"ranked_leads": [
        {"profile_url": "https://www.linkedin.com/in/alex/", "priority": "High", "why": "same function"},
        {"profile_url": "https://www.linkedin.com/in/invented/", "priority": "High", "why": "imagined"}]}):
        ranked = rank_leads("test-key", "Fixture Co", "Singapore", item.title, contacts, {})
        assert len(ranked) == 1 and ranked[0]["name"] == "Alex"
    with patch("ai_workflow.model_json", return_value={"message": "Hi Alex, could we chat?\n[Your name]", "cv_quote": "I used Python"}):
        assert "Hi Alex" in draft_outreach("test-key", contacts[0], "Fixture Co", item.title, cv_input, "I used Python")["message"]
    with patch("ai_workflow.model_json", return_value={"message": "I led 40 projects.\n[Your name]", "cv_quote": ""}):
        try:
            draft_outreach("test-key", contacts[0], "Fixture Co", item.title, cv_input)
            raise AssertionError("Unsupported metric should fail")
        except ValueError:
            pass
    assert validated_job_url("https://www.linkedin.com/jobs/view/12345/")
    assert not validated_job_url("https://www.evil.com/jobs/view/12345/")
    assert "Singapore" in linkedin_job_search("consultant", "AI", "Singapore")
    with patch("jobs.urlopen") as lever_call:
        lever_call.return_value.__enter__.return_value = io.BytesIO(json.dumps([
            {"id": "1", "text": "AI Consultant", "hostedUrl": "https://jobs.lever.co/fixture/1",
             "categories": {"location": "Singapore", "team": "AI"}, "workplaceType": "on-site",
             "descriptionPlain": "AI consulting projects"},
            {"id": "2", "text": "Remote Consultant", "hostedUrl": "https://jobs.lever.co/fixture/2",
             "categories": {"location": "Singapore"}, "workplaceType": "remote", "descriptionPlain": "AI"},
        ]).encode())
        found, errors = fetch_lever_jobs(("fixture",), "Singapore")
        assert not errors and len(found) == 1 and found[0].id == "lever:fixture:1"
    found_body = {"status": "completed", "output": [{"type": "web_search_call"},
        {"type": "message", "content": [{"type": "output_text", "text": "Possible search hits",
          "annotations": [{"type": "url_citation", "title": "Candidate job",
                           "url": "https://www.linkedin.com/jobs/view/123/"},
                          {"type": "url_citation", "title": "Wrong host",
                           "url": "https://example.com/jobs/view/123/"}]}]}]}
    with patch("ai_workflow.urlopen") as search_call:
        search_call.return_value.__enter__.return_value = io.BytesIO(json.dumps(found_body).encode())
        links = discover_linkedin_links("test-key", "jobs", "", "AI Consultant", "Singapore")
        assert len(links) == 1 and links[0]["title"] == "Candidate job"
        search_payload = json.loads(search_call.call_args.args[0].data)
        assert search_payload["tools"][0]["type"] == "web_search" and search_payload["store"] is False
    sample_csv = io.StringIO()
    writer = csv.DictWriter(sample_csv, fieldnames=["title", "company", "recommendation", "status", "source", "url"])
    writer.writeheader()
    writer.writerow({"title": "AI Consultant", "company": "Example Co", "recommendation": "Apply",
                     "status": "Applied", "source": "Example", "url": "https://example.com/job/1"})
    restored = parse_pipeline_csv(sample_csv.getvalue().encode())
    assert identity(restored[0]["title"], restored[0]["company"], restored[0]["url"]) == "example.com/job/1"
    assert summary(restored, 2)["applied"] == 1 and summary(restored, 2)["contacts"] == 2
    archived = change_status(restored, restored[0], "Rejected")
    assert summary(archived)["rejected"] == 1 and summary(archived)["applied"] == 0
    reopened = change_status(archived, archived[0], "KIV")
    assert summary(reopened)["kiv"] == 1 and summary(reopened)["rejected"] == 0
    legacy = sample_csv.getvalue().replace("Applied", "Interested")
    assert parse_pipeline_csv(legacy.encode())[0]["status"] == "KIV"
    duplicate = dict(restored[0], url="https://example.com/job/1/?source=email", status="Interested")
    assert len(merge_records(restored, [duplicate])) == 1
    assert merge_records(restored, [duplicate])[0]["status"] == "Interested"
    writer.writerow(duplicate)
    assert len(parse_pipeline_csv(sample_csv.getvalue().encode())) == 1
    first = Job("board:1", "AI Consultant", "Example Co", "AI", "Singapore", "", "AI consulting", "https://example.com/job/1/", "Board")
    updated = Job("other:9", "AI Consultant", "Example Co", "AI", "Singapore", "", "Updated AI consulting", "https://example.com/job/1?ref=search", "Board")
    pool, added = merge_jobs({}, [first, updated])
    assert added == 1 and len(pool) == 1 and next(iter(pool.values())).id == first.id
    pool, added = merge_jobs(pool, [updated])
    assert added == 0 and next(iter(pool.values())).description == updated.description
    try:
        parse_pipeline_csv(b"title,company\nA,B\n")
        raise AssertionError("Bad CSV should be rejected")
    except ValueError:
        pass
    demo = shortlist(demo_jobs(), CV, Profile(terms("consultant"), terms("AI"), 6, 110000))
    assert 1 <= len(demo) <= 10 and all("consultant" in x.job.title.lower() for x in demo)
    print("PASS invariants: CV parsing, board ingestion, job AI, grounded tailoring, lead ranking, drafts and CSV restore")


if __name__ == "__main__":
    check_invariants()
    dev = check_cases("development")
    held = check_cases("holdout")
    if dev[0] != dev[1] or held[0] != held[1]:
        raise SystemExit(1)
