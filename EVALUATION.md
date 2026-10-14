# What the evaluation actually measures

## Current demo fixtures

`python evaluate.py` feeds each invented job description, short CV and preferences into the recommendation rules. It compares the resulting **Apply / Review / Skip** with a manually chosen `expected` label in `tests/development.json` or `tests/holdout.json`. Development cases catch regressions after edits. The separate holdout file models the workflow of reserving cases until the rules are settled, although these hand-written examples are not an independent study.

The script also checks invariants: negated experience does not support a keyword, remote/wrong-city roles fail the location filter, duplicate postings merge across searches while preserving status IDs, user decisions update the pipeline, and exported statuses can be restored without duplicate rows. **Mocked** model responses check CV quote filtering, batch job reviews, extractive CV selection, filtering of invented lead URLs, and a citation-backed LinkedIn web-search response. These checks cannot verify model accuracy, freshness of LinkedIn hits or people relevance.

## Evaluate the live model separately

`evaluate_ai.py --provider Gemini --split development` submits seven invented cases through the actual Gemini API; use `--split holdout` for four separate cases. You can also run `--provider OpenAI`. Set `GEMINI_API_KEY` or `OPENAI_API_KEY` in a **local environment variable**; each case incurs a real API call subject to provider quotas and billing. The script compares decisions to the manually written labels and reports guardrail flags. Holdout should be run only after the prompt is set. We have not run live-model tests without a key and make no claim about model accuracy. Independently labeled real listings and CVs are still needed.

## Turn this into a defensible evaluation

1. Gather 15–30 real job postings in the target city and a consented, redacted CV. Capture the original job URLs and dates.
2. **Before viewing the app's recommendation**, label each role Apply / Review / Skip with a reason. Use one rubric: Apply when location, function, domain, experience and evidenced core skills align and known pay clears the user's minimum; Review when important details are unknown or borderline; Skip for clear mismatch. Record a second reviewer's label when possible and resolve disagreements.
3. Put most labeled cases in development and reserve at least five in a separate holdout file. Tune only on development. Run the holdout once before the interview and report any failures, rather than silently editing the holdout labels.
4. Report the confusion table, especially **false Apply** (app says Apply for a labeled Skip) and **false Skip** (missed opportunity). Also report how many relevant local roles the selected company boards omitted. The number of cases must accompany every rate.
5. Audit each suggested CV keyword: can a reviewer point to the exact original line? Treat unsupported additions as failures. For outreach, inspect a handful of LinkedIn search results and rate whether current company, region, function and claimed shared background actually match. The app's search links alone do not identify people.

`tests/labeling_template.csv` gives you columns to fill. You can bring the labeled file back for a later scoring script; the current code does not ingest or score it automatically.
