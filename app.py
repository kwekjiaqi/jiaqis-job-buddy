import google.generativeai as genai
import csv
import hashlib
import hmac
import io

import streamlit as st

from ai_review import MODEL, review_role
from gemini_client import MODEL as GEMINI_MODEL
from ai_workflow import discover_linkedin_links, draft_outreach, parse_cv, plan_leads, rank_leads, review_jobs, tailor_cv_with_ai
from cv import read_cv, tailor_cv
from dashboard import change_status, identity, merge_records, parse_pipeline_csv, summary
from jobs import DEFAULT_BOARDS, Job, fetch_jobs, fetch_lever_jobs, is_in_person_location, merge_jobs
from matching import Profile, shortlist, terms
from outreach import lead_searches, linkedin_job_search, outreach_draft, validated_job_url, validated_profile_url
from sample_data import CV, demo_jobs


st.set_page_config(page_title="Job Search Buddy", page_icon="🧭", layout="wide")
st.title("Job Search Buddy")
st.caption("Find local roles, inspect fit, preserve CV evidence, and plan a human outreach route.")


@st.cache_data(ttl=900, show_spinner=False)
def live_jobs(boards: tuple[str, ...], lever_sites: tuple[str, ...], city: str):
    greenhouse, first_errors = fetch_jobs(boards, city)
    lever, second_errors = fetch_lever_jobs(lever_sites, city)
    return greenhouse + lever, first_errors + second_errors


with st.sidebar:
    st.header("Scope of this demo")
    st.write("Live search checks selected public Greenhouse and Lever company boards. LinkedIn jobs are added from listings you choose; remote locations are excluded.")
    st.write("Apply / Review / Skip are transparent triage rules, not hiring predictions.")
    st.write("LinkedIn buttons open searches for you to inspect. Paste listings and verified profiles into the app; it does not scrape LinkedIn or send messages.")
    st.write("AI actions run only when clicked. CV and job analysis send source text to your selected provider; web discovery sends search terms. The rule-based pipeline also works without AI.")
    provider = st.selectbox("AI provider", ["Gemini", "OpenAI"])
    try:
        server_key = str(st.secrets.get("GEMINI_API_KEY" if provider == "Gemini" else "OPENAI_API_KEY", ""))
        demo_code = str(st.secrets.get("AI_DEMO_PASSCODE", ""))
    except (FileNotFoundError, KeyError):
        server_key, demo_code = "", ""
    if server_key and demo_code:
        entered_code = st.text_input("AI demo access code", type="password",
                                     help="Set privately in your app's Streamlit Secrets.")
        ai_key = server_key if hmac.compare_digest(entered_code, demo_code) else ""
    else:
        ai_key = st.text_input(f"Your {provider} API key for this session", type="password",
                               help="Used only when you click an AI action; never upload an API key to GitHub.")
    st.caption(f"AI model: {GEMINI_MODEL if provider == 'Gemini' else MODEL}. Gemini has limited free usage; provider quotas and billing may apply.")

mode = st.radio("Job source", ["Fictional demo", "Live local openings"], horizontal=True)
upload = st.file_uploader("Upload your CV (TXT, PDF, DOCX), or paste text below", type=["txt", "pdf", "docx"])
if "cv_text" not in st.session_state:
    st.session_state.cv_text = CV
cv_text = st.text_area("CV text (editable)", key="cv_text", height=185)
if upload is not None:
    try:
        cv_text = read_cv(upload.name, upload.getvalue())
        st.caption(f"Using extracted text from {upload.name}; check it before making decisions.")
        with st.expander("Inspect extracted text"):
            st.text(cv_text[:5000])
    except Exception as exc:
        st.error(f"Could not read CV: {exc}")
        st.stop()

cv_hash = hashlib.sha256(cv_text.encode("utf-8")).hexdigest()
st.subheader("1 · AI read the CV")
if st.button("AI extract CV profile", disabled=not bool(ai_key)):
    try:
        with st.spinner("Extracting CV characteristics with source evidence…"):
            st.session_state.ai_profile = parse_cv(ai_key, cv_text, provider=provider)
            st.session_state.ai_profile_hash = (cv_hash, provider)
    except Exception:
        st.error("Could not extract the CV profile. Check AI access and try again.")
profile = st.session_state.get("ai_profile", {}) if st.session_state.get("ai_profile_hash") == (cv_hash, provider) else {}
if profile:
    st.caption("AI extracted these details from the CV. Items without an exact CV quote are omitted; edit the search filters below.")
    st.dataframe([{"Characteristic": kind[:-1].title(), "Value": item["name"], "Original CV quote": item["quote"]}
                  for kind in ("functions", "domains", "skills", "schools", "employers")
                  for item in profile.get(kind, [])], hide_index=True, use_container_width=True)
    if profile.get("years_quote"):
        st.caption(f"Experience: {profile['years']} years · CV evidence: {profile['years_quote']}")
elif not ai_key:
    st.caption("Add AI access in the sidebar to extract an evidence-backed profile.")

a, b, c, d = st.columns(4)
with a:
    role = st.text_input("Target function (comma separated)", ", ".join(x["name"] for x in profile.get("functions", [])[:2]) or "consultant")
with b:
    domain = st.text_input("Target domain (comma separated)", ", ".join(x["name"] for x in profile.get("domains", [])[:2]) or "AI")
with c:
    years_default = profile["years"] if profile else (6 if mode == "Fictional demo" and upload is None else 0)
    years = st.number_input("Your years of experience", min_value=0, max_value=50, value=years_default)
with d:
    salary = st.number_input("Minimum annual pay (0 = no filter)", min_value=0, max_value=1_000_000, value=110000, step=5000)
currency = st.selectbox("Pay currency", ["SGD", "USD"])
city = st.text_input("Target city or region", "Singapore")
pool_key = (mode, city.strip().casefold())
if "job_pools" not in st.session_state:
    st.session_state.job_pools = {}
if "assessments" not in st.session_state:
    st.session_state.assessments = {}
if "pipeline" not in st.session_state:
    st.session_state.pipeline = {}
boards_text = st.text_input("Greenhouse company board tokens, comma separated", ",".join(DEFAULT_BOARDS),
                            disabled=mode != "Live local openings")
lever_text = st.text_input("Optional Lever company site tokens, comma separated", "",
                          disabled=mode != "Live local openings")
with st.expander("Shared background for outreach (optional)"):
    schools = st.text_input("Schools (confirm the names appear in your CV)",
                            ", ".join(x["name"] for x in profile.get("schools", [])))
    employers = st.text_input("Former employers (confirm the names appear in your CV)",
                              ", ".join(x["name"] for x in profile.get("employers", [])))

with st.expander("Restore an earlier pipeline"):
    saved_csv = st.file_uploader("Upload a pipeline CSV previously downloaded from this app", type=["csv"], key="saved_pipeline_upload")
    if st.button("Restore pipeline CSV", disabled=saved_csv is None):
        try:
            snapshot = parse_pipeline_csv(saved_csv.getvalue())
            st.session_state.saved_pipeline = snapshot
            lookup = {identity(x["title"], x["company"], x["url"]): x["status"] for x in snapshot}
            for old in st.session_state.assessments.get(pool_key, []):
                key = identity(old.job.title, old.job.company, old.job.url)
                if key in lookup:
                    st.session_state.pipeline[old.job.id] = lookup[key]
            st.session_state.search_version = st.session_state.get("search_version", 0) + 1
            st.success(f"Restored {len(snapshot)} role records. Re-run a search to inspect matching live listings.")
        except ValueError as exc:
            st.error(str(exc))

if st.button("Search and update pipeline", type="primary"):
    if len(cv_text.strip()) < 30:
        st.error("Add at least a few lines of CV text first.")
    elif not terms(role) or not terms(domain):
        st.error("Enter at least one target function and domain term.")
    else:
        try:
            with st.spinner("Finding roles and checking fit…"):
                if mode == "Fictional demo":
                    jobs, errors = demo_jobs(), []
                else:
                    boards = tuple(x.strip().lower() for x in boards_text.split(",") if x.strip())[:8]
                    lever_sites = tuple(x.strip().lower() for x in lever_text.split(",") if x.strip())[:8]
                    jobs, errors = live_jobs(boards, lever_sites, city)
                pool, added = merge_jobs(st.session_state.job_pools.get(pool_key, {}), jobs)
                st.session_state.job_pools[pool_key] = pool
                st.session_state.new_jobs_added = added
                st.session_state.assessments[pool_key] = shortlist(
                    list(pool.values()), cv_text,
                    Profile(terms(role), terms(domain), years, salary or None, currency), limit=len(pool))
                st.session_state.feed_errors = errors
                restored = {identity(x["title"], x["company"], x["url"]): x["status"]
                            for x in st.session_state.get("saved_pipeline", [])}
                for row in st.session_state.assessments[pool_key]:
                    key = identity(row.job.title, row.job.company, row.job.url)
                    if row.job.id not in st.session_state.pipeline and key in restored:
                        st.session_state.pipeline[row.job.id] = restored[key]
                if "people" not in st.session_state:
                    st.session_state.people = {}
                st.session_state.search_version = st.session_state.get("search_version", 0) + 1
                st.session_state.cv_at_search = cv_text
                st.session_state.role_at_search = terms(role)[0]
                st.session_state.city_at_search = city
                st.session_state.profile_at_search = profile
                st.session_state.preferences_at_search = {
                    "target_function": role, "target_domain": domain, "years_experience": years,
                    "minimum_annual_pay": salary, "currency": currency, "target_city": city,
                    "remote_allowed": False,
                }
                st.session_state.tailored = ""
                st.session_state.source_key = pool_key
        except Exception:
            st.error("The job boards are unavailable. Check the board tokens, or switch to the fictional demo.")

if mode == "Live local openings":
    with st.expander("2 · LinkedIn job search and import (you verify the listing)"):
        st.link_button("Search LinkedIn jobs ↗", linkedin_job_search(role, domain, city))
        discovery_key = (provider, role, domain, city)
        if "linkedin_job_links" not in st.session_state:
            st.session_state.linkedin_job_links = {}
        if st.button("AI search public LinkedIn job links", disabled=not bool(ai_key)):
            try:
                with st.spinner("Searching cited public pages…"):
                    st.session_state.linkedin_job_links[discovery_key] = discover_linkedin_links(
                        ai_key, "jobs", "", f"{role} {domain}", city, provider=provider)
            except Exception:
                st.error("Public LinkedIn search was unavailable; use the direct search link above.")
        discovered_jobs = st.session_state.linkedin_job_links.get(discovery_key, [])
        if discovery_key in st.session_state.linkedin_job_links:
            st.caption("Unverified public results; some may be old, remote or no longer open. Open and confirm before adding one.")
            if not discovered_jobs:
                st.info("No cited LinkedIn job URLs found. Use the direct search link instead.")
            for hit in discovered_jobs:
                st.link_button(hit["title"][:85] + " ↗", hit["url"])
        st.caption("LinkedIn search opens in your browser. Paste a real listing below so the same AI pipeline can assess it. The app does not read LinkedIn automatically.")
        with st.form("linkedin_job_import", clear_on_submit=True):
            linked_url = st.text_input("LinkedIn job URL (linkedin.com/jobs/view/...)")
            linked_title = st.text_input("Job title shown on LinkedIn")
            linked_company = st.text_input("Company")
            linked_location = st.text_input("Location as stated in the listing")
            linked_salary = st.text_input("Annual compensation if listed; otherwise leave blank")
            linked_description = st.text_area("Paste the job description / requirements", height=160)
            imported = st.form_submit_button("Add verified LinkedIn role")
        if imported:
            safe_url = validated_job_url(linked_url)
            if not safe_url or not linked_title.strip() or not linked_company.strip() or len(linked_description.strip()) < 50:
                st.error("Add a valid LinkedIn job URL, title, company and at least 50 characters of listing text.")
            elif not is_in_person_location(linked_location, city):
                st.error("The location must explicitly match the target city and cannot be remote.")
            elif len(cv_text.strip()) < 30 or not terms(role) or not terms(domain):
                st.error("Add a CV, target function and domain first.")
            else:
                linked_job = Job(id=f"linkedin:{safe_url.split('?')[0].rstrip('/')}", title=linked_title.strip()[:180],
                                 company=linked_company.strip()[:120], category="", location=linked_location.strip()[:150],
                                 salary=linked_salary.strip()[:120], description=linked_description.strip()[:12000],
                                 url=safe_url, source="LinkedIn · user-verified import")
                pool, added = merge_jobs(st.session_state.job_pools.get(pool_key, {}), [linked_job])
                st.session_state.job_pools[pool_key] = pool
                st.session_state.new_jobs_added = added
                st.session_state.assessments[pool_key] = shortlist(
                    list(pool.values()), cv_text,
                    Profile(terms(role), terms(domain), years, salary or None, currency), limit=len(pool))
                st.session_state.cv_at_search = cv_text
                st.session_state.profile_at_search = profile
                st.session_state.role_at_search = terms(role)[0]
                st.session_state.city_at_search = city
                st.session_state.preferences_at_search = {
                    "target_function": role, "target_domain": domain, "years_experience": years,
                    "minimum_annual_pay": salary, "currency": currency, "target_city": city,
                    "remote_allowed": False,
                }
                st.session_state.source_key = pool_key
                st.session_state.search_version = st.session_state.get("search_version", 0) + 1
                st.success("LinkedIn role collected. It appears in the shortlist if your function and domain filters match." if added else "Existing LinkedIn role refreshed without a duplicate.")

rows = st.session_state.assessments.get(pool_key, []) if st.session_state.get("source_key") == pool_key else []
if "people" not in st.session_state:
    st.session_state.people = {}
if st.session_state.get("source_key") != pool_key and pool_key not in st.session_state.assessments:
    st.caption("Search to start a pipeline for this source and city.")

batch_fingerprint = hashlib.sha256((provider + str(pool_key) + st.session_state.get("cv_at_search", "") +
                                    str(st.session_state.get("preferences_at_search", {})) +
                                    "".join(row.job.id + row.job.description for row in rows[:10])).encode("utf-8")).hexdigest()
if "ai_batches" not in st.session_state:
    st.session_state.ai_batches = {}
if rows:
    st.subheader("3–5 · AI analyse the open jobs and recommend")
    st.caption("One model request reviews up to ten top-ranked jobs; the rules remain visible for comparison. Missing model results fall back to the rules.")
    if st.button("AI analyse top 10 jobs", disabled=not bool(ai_key)):
        try:
            with st.spinner("Comparing roles with CV evidence…"):
                st.session_state.ai_batches[batch_fingerprint] = review_jobs(
                    ai_key, st.session_state.cv_at_search, rows[:10], st.session_state.preferences_at_search,
                    provider=provider)
            st.success(f"AI reviewed {len(st.session_state.ai_batches[batch_fingerprint])}/{min(len(rows), 10)} roles.")
        except Exception:
            st.error("AI pipeline analysis failed. Check AI access or use the rule recommendations below.")
ai_batch = st.session_state.ai_batches.get(batch_fingerprint, {})

current_records = [{"title": row.job.title, "company": row.job.company,
                          "recommendation": ai_batch.get(row.job.id, {}).get("decision", row.recommendation),
                          "status": st.session_state.pipeline.get(row.job.id, "New"),
                          "source": row.job.source, "url": row.job.url} for row in rows]
dashboard_records = merge_records(st.session_state.get("saved_pipeline", []), current_records)

st.subheader("Your job search dashboard")
if dashboard_records:
    contact_count = sum(len(st.session_state.people.get(row.job.id, [])) for row in rows)
    counts = summary(dashboard_records, contact_count)
    metrics = st.columns(3)
    for slot, title, value in zip(metrics,
                                  ["Unique ads collected", "Unique relevant roles", "Apply matches"],
                                  [len(st.session_state.job_pools.get(pool_key, {})) if pool_key in st.session_state.job_pools else "—",
                                   counts["shortlisted"], counts["apply"]]):
        slot.metric(title, value)
    metrics = st.columns(3)
    for slot, title, value in zip(metrics,
                                  ["To review", "Marked applied", "Contacts added this session"],
                                  [counts["review"], counts["applied"], counts["contacts"]]):
        slot.metric(title, value)
    st.progress(counts["applied"] / max(counts["shortlisted"], 1))
    st.caption(f"Pipeline: {counts['new']} awaiting a decision, {counts['kiv']} KIV, {counts['applied']} applied and awaiting an update, {counts['rejected']} filed away. Applications are self-reported, not synced with employer sites.")
else:
    st.info("Run a search or restore a pipeline CSV to see progress here.")

page = st.radio("Page", ["Pipeline review", "Role details & outreach"], horizontal=True)
if page == "Pipeline review" and dashboard_records:
    st.subheader("Decide what to do next")
    st.caption("Your choice is separate from the app's Apply / Review / Skip fit recommendation. 'Applied' means you submitted the application yourself.")
    picked = st.selectbox("Choose a role to update", range(len(dashboard_records)),
                          format_func=lambda n: f"{dashboard_records[n]['title']} · {dashboard_records[n]['company']} · {dashboard_records[n]['status']}",
                          key="pipeline_review_role")
    target = dashboard_records[picked]
    yes, later, no = st.columns(3)
    decision = None
    if yes.button("Yes — I applied", use_container_width=True):
        decision = "Applied"
    if later.button("KIV — keep open", use_container_width=True):
        decision = "KIV"
    if no.button("No — reject and file away", use_container_width=True):
        decision = "Rejected"
    if decision:
        key = identity(target["title"], target["company"], target["url"])
        for row in rows:
            if identity(row.job.title, row.job.company, row.job.url) == key:
                st.session_state.pipeline[row.job.id] = decision
        st.session_state.saved_pipeline = change_status(st.session_state.get("saved_pipeline", []), target, decision)
        if not any(identity(row.job.title, row.job.company, row.job.url) == key for row in rows):
            st.session_state.saved_pipeline = merge_records(st.session_state.saved_pipeline, [dict(target, status=decision)])
        st.rerun()

    active = [x for x in dashboard_records if x["status"] != "Rejected"]
    archived = [x for x in dashboard_records if x["status"] == "Rejected"]
    st.markdown("**Open pipeline**")
    st.dataframe([{"Role": x["title"], "Company": x["company"],
                   "Fit": x["recommendation"], "Status": "Applied — pending update" if x["status"] == "Applied" else x["status"]}
                  for x in active], hide_index=True, use_container_width=True)
    with st.expander(f"Filed away · {len(archived)} rejected roles"):
        st.dataframe([{"Role": x["title"], "Company": x["company"], "Status": x["status"]}
                      for x in archived], hide_index=True, use_container_width=True)
    st.caption("Select an archived role above to move it back to KIV or mark it applied.")

inspect_rows = [row for row in rows if st.session_state.pipeline.get(row.job.id, "New") != "Rejected"]
if page == "Role details & outreach" and inspect_rows:
    st.subheader(f"Top 10 open · {len(inspect_rows)} relevant roles")
    st.caption(f"Latest search added {st.session_state.get('new_jobs_added', 0)} unique postings. Searches add to this source and city's pool; duplicate URLs refresh existing listings and retain status. The feed is cached for 15 minutes. Missing salary or years leads to Review.")
    for message in st.session_state.get("feed_errors", []):
        st.warning(message)
    st.dataframe([{"Role": r.job.title, "Company": r.job.company,
                   "Recommendation": ai_batch.get(r.job.id, {}).get("decision", r.recommendation),
                   "Analysis": "AI" if r.job.id in ai_batch else "Rules", "Source": r.job.source,
                   "Status": st.session_state.pipeline.get(r.job.id, "New")}
                  for r in inspect_rows[:10]], hide_index=True, use_container_width=True)
    if len(inspect_rows) > 10:
        with st.expander(f"See all {len(inspect_rows)} open relevant roles"):
            st.dataframe([{"Role": r.job.title, "Company": r.job.company,
                           "Recommendation": ai_batch.get(r.job.id, {}).get("decision", r.recommendation),
                           "Status": st.session_state.pipeline.get(r.job.id, "New")}
                          for r in inspect_rows], hide_index=True, use_container_width=True)
    options = [f"{r.job.title} · {r.job.company} · {r.recommendation}" for r in inspect_rows]
    selected = st.selectbox("Inspect a role", range(len(inspect_rows)), format_func=lambda n: options[n])
    r = inspect_rows[selected]
    st.write(f"**{r.job.title}** at {r.job.company} · {r.job.location} · {r.job.salary or 'Pay not listed'}")
    st.write(f"**Rule recommendation: {r.recommendation}**")
    for reason in r.reasons:
        st.write("• " + reason)
    st.write("**CV terms evidenced:** " + (", ".join(r.matched_skills) or "none in supported vocabulary"))
    st.write("**Job terms not evidenced in CV:** " + (", ".join(r.missing_skills) or "none in supported vocabulary"))
    with st.expander("Read source listing text"):
        st.text(r.job.description[:6500])

    st.subheader("AI review · model analysis")
    st.caption("The model reads this CV and listing on demand. Its answer is checked against exact CV and job quotes and compared with the rule decision above.")
    review_input = f"{r.job.id}\n{st.session_state.cv_at_search}\n{r.job.description}\n{st.session_state.preferences_at_search}"
    review_key = hashlib.sha256((provider + review_input).encode("utf-8")).hexdigest()
    if "ai_reviews" not in st.session_state:
        st.session_state.ai_reviews = {}
    if st.button("Ask AI to review this role", disabled=not bool(ai_key), key=f"ai-{review_key}"):
        try:
            with st.spinner("Checking job fit and source evidence…"):
                st.session_state.ai_reviews[review_key] = review_role(
                    ai_key, st.session_state.cv_at_search,
                    {"title": r.job.title, "company": r.job.company, "location": r.job.location,
                     "salary": r.job.salary, "description": r.job.description},
                    st.session_state.preferences_at_search, r.recommendation, provider=provider)
        except Exception:
            st.error("AI review failed. Check the API key, API credits and network, then try again. The rule review still works.")
    if not ai_key:
        st.info("Enter your session API key or the private demo access code in the sidebar to enable the AI review.")
    if r.job.id in ai_batch:
        assessed = ai_batch[r.job.id]
        st.write(f"**AI pipeline recommendation: {assessed['decision']}**")
        st.text(assessed["reason"])
        if assessed["cv_evidence"]:
            st.caption("Verified CV quote: " + assessed["cv_evidence"][0])
        for flag in assessed["flags"]:
            st.warning(flag)
    if review_key in st.session_state.ai_reviews:
        reviewed = st.session_state.ai_reviews[review_key]
        st.write(f"**AI suggestion: {reviewed['decision']}** · Rule recommendation: {r.recommendation}")
        st.text(reviewed["reason"])
        for flag in reviewed["flags"]:
            st.warning(flag)
        if reviewed["cv_evidence"]:
            st.write("**Exact CV excerpts**")
            for quote in reviewed["cv_evidence"]:
                st.code(quote, language=None)
        if reviewed["job_evidence"]:
            st.write("**Exact job listing excerpts**")
            for quote in reviewed["job_evidence"]:
                st.code(quote, language=None)
        if reviewed["unknowns"]:
            st.write("**Still verify:** " + "; ".join(reviewed["unknowns"]))
        st.caption("AI suggestions can be wrong; check the listing and CV before acting. Validated CV excerpts can guide your tailored draft.")

    st.caption(f"Pipeline status: {st.session_state.pipeline.get(r.job.id, 'New')}. Change it on the Pipeline review page.")
    if r.job.url:
        st.link_button("Open application page ↗", r.job.url)
        st.caption("This opens the source listing. It does not submit an application or update status automatically.")
    else:
        st.caption("Fictional example: no application link.")

    st.subheader("6 · AI tailor the CV using original evidence")
    tailor_key = hashlib.sha256((review_key + "tailor").encode()).hexdigest()
    if "ai_tailors" not in st.session_state:
        st.session_state.ai_tailors = {}
    if st.button("AI select CV highlights for this role", disabled=not bool(ai_key)):
        try:
            with st.spinner("Selecting supported CV evidence…"):
                st.session_state.ai_tailors[tailor_key] = tailor_cv_with_ai(
                    ai_key, st.session_state.cv_at_search, r.job.description, r.job.title, provider=provider)
        except Exception:
            st.error("AI tailoring failed. The rule-based draft remains available below.")
    if tailor_key in st.session_state.ai_tailors:
        tailored_ai = st.session_state.ai_tailors[tailor_key]
        edited_draft = st.text_area("AI-selected draft for your review", tailored_ai["draft"], height=220,
                                    key=f"tailored-ai-{tailor_key}")
        st.download_button("Download AI-selected CV draft", edited_draft,
                           "ai_selected_cv_draft.txt", "text/plain")
        st.caption("The model chooses the order and relevant keywords; the displayed experience excerpts are exact CV text. Edit before using.")
    if st.button("Make a rule-based CV draft"):
        st.session_state.tailored = tailor_cv(st.session_state.cv_at_search, r.job.description, r.job.title)
        st.session_state.tailored_job = r.job.id
    if st.session_state.get("tailored_job") == r.job.id and st.session_state.get("tailored"):
        st.text_area("Draft for your review", st.session_state.tailored, height=230)
        st.download_button("Download tailored text", st.session_state.tailored,
                           "tailored_cv_draft.txt", "text/plain")
        st.caption("Only supported keywords are added. Edit wording and formatting before applying.")

    st.subheader("7 · AI build a leads list")
    lead_plan_key = hashlib.sha256((review_key + "lead-plan" + str(st.session_state.get("profile_at_search", {}))).encode()).hexdigest()
    if "lead_plans" not in st.session_state:
        st.session_state.lead_plans = {}
    if st.button("AI suggest relevant people to look for", disabled=not bool(ai_key)):
        try:
            with st.spinner("Planning relevant outreach routes…"):
                st.session_state.lead_plans[lead_plan_key] = plan_leads(
                    ai_key, r.job.company, r.job.title, st.session_state.city_at_search,
                    st.session_state.get("profile_at_search", {}), provider=provider)
        except Exception:
            st.error("Could not make the lead search plan. Manual search links remain available below.")
    if lead_plan_key in st.session_state.lead_plans:
        st.caption("AI suggestions below are roles to search for, not named verified people.")
        for lead in st.session_state.lead_plans[lead_plan_key]:
            st.write(f"**{lead['role']}** — {lead['why']}")
            if mode == "Live local openings":
                st.link_button("Search LinkedIn people ↗", lead["url"])
    if mode == "Fictional demo":
        st.info("This company is fictional. In live mode, this section opens LinkedIn searches for leaders, peers and shared background.")
        st.subheader("8 · AI write an outreach draft")
        fictional_person = {"name": "Alex Tan", "title": "AI consulting lead",
                            "url": "", "reason": "a shared consulting background"}
        fiction_draft_key = hashlib.sha256((review_key + "fictional-draft").encode()).hexdigest()
        if "ai_drafts" not in st.session_state:
            st.session_state.ai_drafts = {}
        if st.button("AI draft a note to fictional Alex", disabled=not bool(ai_key)):
            try:
                evidence = ai_batch.get(r.job.id, {}).get("cv_evidence", [])
                with st.spinner("Writing a short source-grounded note…"):
                    st.session_state.ai_drafts[fiction_draft_key] = draft_outreach(
                        ai_key, fictional_person, r.job.company, r.job.title,
                        st.session_state.cv_at_search, evidence[0] if evidence else "", provider=provider)
            except Exception:
                st.error("AI draft failed; the template below is still available.")
        if fiction_draft_key in st.session_state.ai_drafts:
            st.code(st.session_state.ai_drafts[fiction_draft_key]["message"], language=None)
        st.write("**Template fallback for a fictional contact**")
        st.code(outreach_draft("Alex Tan", r.job.company, r.job.title,
                               "a shared consulting background", r.matched_skills), language=None)
        st.caption("Use the copy icon; replace the fictional name and review every detail before sending.")
    else:
        st.caption("These are search routes, not verified people. Open each result and confirm current employer, city, function, and any shared school or workplace.")
        people_search_key = (provider, r.job.company, r.job.title, st.session_state.city_at_search)
        if "linkedin_people_links" not in st.session_state:
            st.session_state.linkedin_people_links = {}
        if st.button("AI search public LinkedIn profile links", disabled=not bool(ai_key)):
            try:
                with st.spinner("Finding cited public profile pages…"):
                    st.session_state.linkedin_people_links[people_search_key] = discover_linkedin_links(
                        ai_key, "people", r.job.company, r.job.title, st.session_state.city_at_search,
                        provider=provider)
            except Exception:
                st.error("Public profile discovery was unavailable; use the targeted searches below.")
        if people_search_key in st.session_state.linkedin_people_links:
            st.caption("Unverified search hits; profile name, company, region and background must be confirmed manually.")
            found_people = st.session_state.linkedin_people_links[people_search_key]
            if not found_people:
                st.info("No cited public profiles found. Use the targeted LinkedIn searches below.")
            for hit in found_people:
                st.link_button(hit["title"][:85] + " ↗", hit["url"])
        verified_schools = ",".join(x.strip() for x in schools.split(",") if x.strip() and x.strip().casefold() in st.session_state.cv_at_search.casefold())
        verified_employers = ",".join(x.strip() for x in employers.split(",") if x.strip() and x.strip().casefold() in st.session_state.cv_at_search.casefold())
        if schools and not verified_schools or employers and not verified_employers:
            st.info("Some background names are absent from the CV text, so no shared-background search was made for them.")
        for lead in lead_searches(r.job.company, st.session_state.city_at_search,
                                  st.session_state.role_at_search, verified_schools, verified_employers):
            st.link_button(lead.label + " ↗", lead.url)
            st.caption(lead.reason)
        with st.form(key=f"person-{st.session_state.search_version}-{r.job.id}", clear_on_submit=True):
            person_name = st.text_input("Verified person's name")
            person_title = st.text_input("Current role / connection")
            person_employer = st.text_input("Verified current employer")
            person_city = st.text_input("Verified current city / region")
            person_url = st.text_input("LinkedIn profile URL")
            person_reason = st.text_input("Why relevant (e.g., same function or school)")
            submitted = st.form_submit_button("Add to outreach list")
        if submitted:
            verified = validated_profile_url(person_url)
            if person_name.strip() and person_employer.strip() and person_city.strip() and verified and person_reason.strip():
                contacts_for_job = st.session_state.people.setdefault(r.job.id, [])
                profile_key = verified.partition("?")[0].rstrip("/").casefold()
                if any(x["url"].partition("?")[0].rstrip("/").casefold() == profile_key for x in contacts_for_job):
                    st.info("That profile is already in this role's outreach list.")
                else:
                    contacts_for_job.append({
                        "name": person_name.strip()[:100], "title": person_title.strip()[:130],
                        "employer": person_employer.strip()[:100], "city": person_city.strip()[:100],
                        "url": verified, "reason": person_reason.strip()[:200]})
                    st.rerun()
            else:
                st.error("Add a name, current employer and city, reason, and valid https://linkedin.com/in/... profile URL.")
        contacts = st.session_state.people.get(r.job.id, [])
        if contacts:
            st.dataframe(contacts, hide_index=True, use_container_width=True)
            rank_key = hashlib.sha256((review_key + str(contacts) + "rank").encode()).hexdigest()
            if "lead_rankings" not in st.session_state:
                st.session_state.lead_rankings = {}
            if st.button("AI rank verified leads", disabled=not bool(ai_key)):
                try:
                    with st.spinner("Ranking only the profiles you verified…"):
                        st.session_state.lead_rankings[rank_key] = rank_leads(
                            ai_key, r.job.company, st.session_state.city_at_search, r.job.title,
                            contacts, st.session_state.get("profile_at_search", {}), provider=provider)
                except Exception:
                    st.error("Could not rank the saved contacts; the manual list remains available.")
            if rank_key in st.session_state.lead_rankings:
                st.write("**AI-ranked leads from verified profiles**")
                st.dataframe(st.session_state.lead_rankings[rank_key], hide_index=True, use_container_width=True)
            chosen = st.selectbox("Draft a note for a verified person", range(len(contacts)),
                                  format_func=lambda n: f"{contacts[n]['name']} · {contacts[n]['title']}")
            person = contacts[chosen]
            st.subheader("8 · AI write an outreach draft")
            if "ai_drafts" not in st.session_state:
                st.session_state.ai_drafts = {}
            draft_key = hashlib.sha256((review_key + person["url"] + person["reason"]).encode()).hexdigest()
            if st.button("AI write a note for this verified person", disabled=not bool(ai_key)):
                try:
                    evidence = ai_batch.get(r.job.id, {}).get("cv_evidence", [])
                    with st.spinner("Writing a grounded note for your review…"):
                        st.session_state.ai_drafts[draft_key] = draft_outreach(
                            ai_key, person, r.job.company, r.job.title,
                            st.session_state.cv_at_search, evidence[0] if evidence else "", provider=provider)
                except Exception:
                    st.error("AI note failed; use the template below instead.")
            if draft_key in st.session_state.ai_drafts:
                st.code(st.session_state.ai_drafts[draft_key]["message"], language=None)
                st.caption("AI-generated draft. Verify every statement before copying or sending; the app never sends it.")
            st.write("**Template fallback**")
            st.code(outreach_draft(person["name"], r.job.company, r.job.title,
                                   person["reason"], r.matched_skills), language=None)
            st.caption("Use the copy icon, personalize the note, and verify the role, connection and CV claim before sending. Nothing is sent by this app.")

    people_csv = io.StringIO()
    contact_writer = csv.writer(people_csv)
    contact_writer.writerow(["job", "company", "person", "title", "employer", "city", "profile_url", "reason"])
    for row in rows:
        for person in st.session_state.people.get(row.job.id, []):
            contact_writer.writerow([row.job.title, row.job.company, person["name"], person["title"],
                                     person.get("employer", ""), person.get("city", ""), person["url"], person["reason"]])
    st.download_button("Download outreach CSV", people_csv.getvalue(), "outreach_leads.csv", "text/csv")
elif page == "Role details & outreach" and rows:
    st.info("All roles in this pipeline are filed away. Select an archived role on Pipeline review to reopen it.")
elif page == "Role details & outreach" and pool_key in st.session_state.assessments:
    st.info("No matching local roles found on the selected boards. Try additional company board tokens, a broader function term, or the fictional demo.")

if dashboard_records:
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=["title", "company", "recommendation", "status", "source", "url"])
    writer.writeheader()
    writer.writerows(dashboard_records)
    st.download_button("Download pipeline CSV", csv_buffer.getvalue(), "job_pipeline.csv", "text/csv")
