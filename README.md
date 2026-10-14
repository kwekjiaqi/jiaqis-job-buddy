# Job Search Buddy

An interview prototype for **local, non-remote** job discovery. Choose Gemini 2.5 Flash or OpenAI gpt-4.1-mini for CV profiling, batch job analysis, selecting evidence for a tailored CV, lead-search planning, ranking verified people, and drafting outreach. It retrieves postings from user-selected public Greenhouse and Lever company boards. AI web search can suggest cited public LinkedIn job and profile links; the user confirms the listing or profile, then pastes job text or verified person details before the app treats either as a pipeline entry. The dashboard accumulates unique roles and lets the user mark a role applied, KIV or rejected.

### Eight-step workflow

1. Upload or paste a CV; inspect the extracted text.
2. Click **AI extract CV profile** to see functions, domains, skills and shared background, each backed by a verbatim CV excerpt. Set search preferences yourself.
3. Search selected Greenhouse/Lever company boards and optionally use **AI search public LinkedIn job links**. LinkedIn results are candidates to verify, not automatically imported job descriptions. Paste a verified LinkedIn job's visible details to add it to the same deduplicated pipeline.
4. Click **AI analyse top 10 jobs** to send the CV and ten shortlist candidates in one request. An individual AI review is also available inside each role.
5. Inspect AI Apply / Review / Skip decisions beside rule suggestions, exact source quotes and uncertainties. Rejected roles are archived; KIV and Applied stay open.
6. Click **AI select CV highlights**. The model chooses and orders exact original CV excerpts and only supported skills; the downloadable draft retains the full original CV.
7. Run **AI search public LinkedIn profile links** or **AI suggest relevant people to look for**. Verify profiles yourself, add their name/employer/city/reason, then click **AI rank verified leads** to build a named, ranked list from those entries.
8. Click **AI write a note** for a verified contact (or fictional Alex in demo mode), review the generated draft, and copy it. No message is sent.

The **Fictional demo** has no external job-board dependency. Its AI buttons still require your selected provider’s API key and make real model calls (Gemini has a limited free tier). For live Singapore examples, the default Greenhouse board tokens are `temus,capco,simplifynext`. These are examples, not a claim that those companies currently have ten suitable openings. Users may change company tokens, city, function and domain. Each board can change or become unavailable.

## Run locally

```bash
python -m pip install -r requirements.txt
python evaluate.py
streamlit run app.py
```

See `DEPLOY.md` for browser-based GitHub and Streamlit setup.
See `EVALUATION.md` and `tests/labeling_template.csv` for a path from synthetic checks to independent human labels.

## Evaluation: what is compared against what?

- `tests/development.json`: seven manually labeled **expected recommendations** for small, invented job/CV/profile examples. These become regression checks: a future code change must preserve the intended behavior unless the labels are intentionally reviewed.
- `tests/holdout.json`: four **different**, fixed, manually labeled examples kept in a separate file. Running them after development checks demonstrates a holdout workflow, but the small synthetic set is not independent evidence of real-world accuracy.
- `evaluate.py` compares each actual Apply / Review / Skip output against the expected label and prints agreement by split. It also asserts safety properties: negated skills and `NoSQL` do not establish skill evidence, a CV draft omits unsupported skills, remote or wrong-city locations are excluded, profile URLs are restricted, and search URLs are produced without inventing named people.
- Dashboard checks verify the exported pipeline CSV can be restored and that application counts come from user-set statuses.
- Repeat-search checks verify duplicate posting URLs count once, refresh content and retain the role ID used for statuses; restored CSV rows also deduplicate.
- Outreach draft checks prevent unsupported skill claims. Status checks cover rejecting, reopening as KIV, and restoring older CSV files that used `Interested` or `Skipped`.
- AI workflow checks use mocked model and web-search responses: they reject unsupported CV attributes, fake job or lead links, invalid quotes and unsupported CV highlights. They also check batch recommendations and draft generation. These are integration and guardrail checks, **not** a live model accuracy score.

To evaluate the actual model on the synthetic labels, run `python evaluate_ai.py --provider Gemini --split development` with `GEMINI_API_KEY` set locally (or `--provider OpenAI` with `OPENAI_API_KEY`). Run `--split holdout` only after deciding the prompt; each case makes a real API request subject to provider quotas/billing. Report the resulting counts honestly; we have not run this without a key.

None of the evaluations measures real job-market recall, the correctness of a real hiring-manager match, or CV rewrite quality with human raters. A credible next step is consented CVs plus independently labeled job/person candidates, measuring false Apply/Skip, missed relevant roles, evidence support and useful outreach precision. Keep that labeled holdout untouched while tuning rules.

## Limits to explain in the interview

- **Coverage:** Greenhouse and Lever return published jobs from selected company boards, not every job in a region. Relevance is deliberately narrow: matching target function in the title and domain in the listing. Fewer than ten results is normal. Public web-search results from LinkedIn may be missing, stale or incorrect; they have clickable citations and are never claimed to be confirmed openings.
- **Location:** only a matching named city/region qualifies. A listing whose location says remote is excluded. Hybrid postings with a local office can still appear, so inspect the original ad.
- **People:** the app supplies AI web-search hits and search routes, then ranks only profiles you verify and enter. A public search hit is not confirmation of someone's current role, employer or city. LinkedIn's general member and job search are not openly available through a simple public search API; the app does not scrape profiles or invent a hiring-manager match. Copy, edit and check outreach drafts yourself; the app does not send messages. Fictional demo content is explicitly fictional.
- **AI and CV:** the Gemini GenerateContent API (`gemini-2.5-flash`) or OpenAI Responses API (`gpt-4.1-mini`) runs only when an AI action is clicked. CV characteristics and job-review source quotes must occur verbatim in the source text or are omitted. A weak Apply becomes Review; a model Apply conflicting with a rule-based Skip becomes Review. Free-text model reasoning and outreach drafts can still be wrong. The tailored CV remains an extractive TXT draft; generated achievements are never inserted into it. Review before acting.
- **Compensation:** annual SGD or USD comparisons require an explicitly parseable range in the selected currency. Missing, ambiguous, hourly or other-currency values trigger Review. No currency conversion is attempted.
- **State and privacy:** searches add unique listings to a pool for each source and city within the browser session. A refreshed posting retains its status; the top ten open roles is ranked again each search. The live board feed is cached for 15 minutes. Pipeline review uses `New`, `KIV` (open), `Applied` (open pending update) and `Rejected` (filed away, reopenable). These user decisions differ from AI/rule fit recommendations. Export and restore the pipeline CSV for statuses and counts; export the outreach CSV separately. Contact records, model outputs and complete listing descriptions are not restored in a fresh session. AI calls send the data needed for that step to the selected provider; OpenAI requests set `store: false`. Gemini free-tier data handling follows Google’s terms. The app has no database. Use the fictional CV for a public interview demo.

The job board API does not require authentication for public GET operations. The app links to each posting; it does not submit applications or contact people.
