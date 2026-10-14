# GitHub and Streamlit setup

## Upload the code

1. Download `job_search_buddy_app.zip` and unzip it on your computer.
2. Sign in to GitHub. Use **+ → New repository** and call it `job-search-buddy`. Public is easiest to share; a private repository needs the appropriate Streamlit access. Create the repository without starter files.
3. In the repository, use **Add file → Upload files**. Drag the **contents** of the unzipped folder. `app.py`, `ai_review.py`, `ai_workflow.py`, `gemini_client.py`, `requirements.txt`, `jobs.py`, `outreach.py` and `tests/` must be at the repository root. Commit the files. Do not upload the ZIP as the application. If updating an earlier deployment, upload the new and changed files in the same way; Streamlit rebuilds after your commit.
4. Do not upload your personal CV or any API key. The included CV and jobs are fictional.

## Deploy and rehearse

1. At https://share.streamlit.io, connect GitHub and choose **Create app → Yup, I have an app**.
2. Pick the repository and branch (normally `main`); select `app.py` as the main file path. Deploy. Streamlit installs packages from `requirements.txt`.
3. Select **Fictional demo**, keep the example CV and click **AI extract CV profile** after setting up AI access below. Then click **Search and update pipeline** and **AI analyse top 10 jobs**. Show the AI/rule recommendations on the dashboard and mark one role **KIV**, **Applied**, or **Rejected**. Switch to **Role details & outreach** for AI-selected CV highlights, AI lead-search plans and a fictional AI-written note. It is fine if the batch returns fewer than ten eligible roles.
4. For live jobs, select **Live local openings**, keep city `Singapore`, and query the Greenhouse boards or add Lever site tokens. To bring in LinkedIn, click **AI search public LinkedIn job links**, open a cited result, and manually paste its URL, title, company, local location and job text into the import form. These search hits may be old or irrelevant.
5. Open AI-discovered or manual LinkedIn people searches. Verify each real person's current employer, city, role and any claimed commonality yourself. Enter the profile URL and verified details; click **AI rank verified leads** and **AI write a note**. Review and copy the draft manually. Export the outreach CSV before closing the tab.
6. In a fresh browser session, expand **Restore an earlier pipeline**, upload the downloaded `job_pipeline.csv`, and click **Restore pipeline CSV**. The dashboard returns; re-run the search to inspect matching listings. Contacts need their separate CSV, which this version can export but cannot reload.

## Add Gemini to your existing live app

1. In [Google AI Studio](https://aistudio.google.com/apikey), create a Gemini API key. Google offers a limited free tier for Gemini 2.5 Flash, including a limited allowance for Google Search grounding. Availability and usage limits depend on your project and region; enabling paid billing can incur charges. Streamlit does not provide this API key or pay for Gemini usage.
2. Upload the updated source files to your existing GitHub repository. In the repository click **Add file → Upload files**, choose the changed files including `gemini_client.py`, and commit. If GitHub shows duplicate-name conflicts, use the GitHub file editor to replace each existing file instead. Streamlit should redeploy from your commit.
3. At [Streamlit Community Cloud](https://share.streamlit.io), open the app **⋮ → Settings → Secrets**. Add these TOML lines, choosing your own private access code:

   ```toml
   GEMINI_API_KEY = "paste-your-Google-AI-Studio-key"
   AI_DEMO_PASSCODE = "choose-a-private-code"
   ```

4. Select **Gemini** in the app sidebar and enter the private access code. Try **Fictional demo → AI extract CV profile → Search and update pipeline → AI analyse top 10 jobs**. If you already had `OPENAI_API_KEY` in Secrets, you can keep it and choose **OpenAI** instead. Keys belong only in Streamlit Secrets, never GitHub or slides.
5. Without Secrets, the sidebar offers a password field for a session API key. For a public demo, prefer Secrets and the passcode. The passcode protects the configured key from anonymous app visitors.

Google Search grounding sometimes returns opaque citation redirects instead of direct LinkedIn URLs. The app ignores links it cannot validate as LinkedIn job/profile URLs and keeps manual LinkedIn search links available. Users must still verify listings and people; the app does not scrape or import LinkedIn details automatically. AI calls send source data to the selected provider, including CV excerpts on CV/job actions.

The optional local `evaluate_ai.py --provider Gemini --split development` reads `GEMINI_API_KEY` from your environment and makes actual model calls. Run `--split holdout` only after the prompt is settled. Mocked regression tests in `evaluate.py` do not require an API key.

## Run tests or the app locally

In a terminal inside the unzipped folder:

```bash
python -m pip install -r requirements.txt
python evaluate.py
streamlit run app.py
```

The current synthetic fixtures have seven development labels and four separate holdout labels. These checks are not production accuracy.
