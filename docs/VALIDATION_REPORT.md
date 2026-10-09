# Phase 4.5 Validation Report

**Run date:** 2026-10-10

**Historical verdict at Phase 4.5:** **Not ready to deploy.** The original run found a security-control gap, known vulnerable dependencies, recommendation repetition, mobile layout overflow, weak failure feedback, and severe latency at 100 simulated users. Security findings were addressed in a separate follow-up; Phase S has since improved recommendations, layout, and failure feedback. High-load latency and some recommendation repetition remain open; see the Phase S results below.

**Current Phase F verdict:** **Not ready for public deployment or real-student decisions.** The latest local checks passed the tested browser/accessibility scenarios and found no known dependency vulnerabilities or active Bandit findings. High-load response time, open teacher self-registration, and the simulation-only evidence remain limitations. Current results and the final use-by-use verdict are in the [Phase F section](#phase-f-final-validation).

## What was tested

All API and load tests used temporary SQLite databases. Browser screenshots and the seeded browser account were created against another temporary database. `outputs/app.db` was not opened or modified.

| Area | Result |
|---|---|
| Functional/API cases | 14 validation tests passed with 81.94% total app coverage. Invalid bodies, wrong types, long inputs, Unicode/emoji, SQL-like text, numeric boundaries, missing/expired/tampered/wrong-type tokens, duplicate and empty quiz submissions, wrong methods, and malformed content did not produce HTTP 500 responses in the exercised cases. |
| Protected routes | Missing, expired, tampered, and refresh-type tokens received HTTP 401 on the tested protected routes. |
| Authentication abuse | Five bad login attempts were accepted as failed logins; the sixth was rate-limited with HTTP 429. Six consecutive account-deletion password guesses all returned 401; that route did not return a rate-limit response. |
| Cross-account access | Unknown user/history paths returned 404. Adding another user's ID as a query parameter to the current-user state endpoint returned only the caller's own state. |
| SQLite concurrent writes | Sixty concurrent quiz submissions through the API produced no HTTP 5xx responses. The load server log contained zero `database is locked` lines. |
| Missing/corrupt model artifacts | Both cases returned five recommendations using the `zpd-fallback` mode. The tests used temporary artifact paths and did not alter bundled model files. |
| Browser and accessibility | Chromium captured four screens and axe-core ran on sign-in, dashboard, and quiz states. See the browser results below. |
| Load and restart | Locust ran 10, 50, and 100-user flows. At 50 users the server was intentionally restarted mid-run; the registered probe user could log in and retrieve its saved history afterward. |
| Dependency/static scans | `pip-audit` reported two distinct vulnerable packages/advisories (one appears twice because the two input requirement files overlap). Bandit reported two medium-severity pickle-deserialization findings and five low-severity findings. The bounded Git-history secret-pattern scan found no matches. |

These checks exercise software behavior. They do **not** demonstrate real learner benefit or learning gains: training and evaluation use simulated learners, resource types are labels rather than real videos or articles, and each simulated submission below supplied the correct answers.

## Functional and security details

The API edge tests sent empty or incomplete JSON, wrong field types, a one-megabyte password value, oversized usernames and answer lists, malformed JSON, Unicode and emoji usernames, SQL-like strings, negative and very large numeric values, and wrong HTTP methods. The checked responses were validation errors, authorization errors, not-found errors, or rate limits rather than server errors.

The quiz API has no topic field in its submission schema. The “wrong-topic” case therefore submitted answer indexes for a different quiz action. The server graded those indexes against the selected action and returned a normal result; it did not accept a client-supplied score.

An invalid username containing an HTML-shaped string is echoed in FastAPI's JSON validation details. The response has JSON content type, and the current browser UI displays dynamic text with `textContent`; this test did not demonstrate script execution. Other clients must still render API text as text, not HTML. Extra SQL-like fields on a quiz submission were ignored and did not change the stored topic or resource label.

### Security findings

| Severity | Finding | Evidence and reproduction |
|---|---|---|
| Medium | Account deletion password confirmation has no rate limit. | A valid access token is required, followed by a password confirmation. Repeatedly send `DELETE /api/account` with incorrect passwords; the handler verifies each attempt and returns 401. The login route is rate-limited, but the deletion route is not. Source review: [auth.py](../app/routes/auth.py), deletion handler around lines 104–109. This phase did not issue a high-volume destructive-endpoint attack. |
| Medium, provisional | Vulnerable dependency versions are present. | `pip-audit` reported `python-jose 3.5.0` / `CVE-2026-85394` and `ecdsa 0.19.2` / `PYSEC-2026-1325`. The scanner output did not include severity scores or fixed-version recommendations; the medium label is a triage placeholder, not a CVSS rating. `python-jose` is pinned in [requirements.txt](../requirements.txt). |
| Medium | Pickle deserialization requires trusted model artifacts. | Bandit B301, medium severity/high confidence, flagged `pickle.load` in [recommender.py](../app/services/recommender.py) around line 52 and [task5_optimizer.py](../src/task5_optimizer.py) around line 241. A malicious artifact supplied before loading could execute code. The runtime artifacts are local project files; no remote artifact-upload path was tested. |

The account-deletion observation came from source review; the other listed scanner findings came from automated tools. No finding was fixed in this phase.

Bandit also reported five low-severity findings: one hardcoded-secret-pattern match on an old constant in [config.py](../app/config.py) (the current code uses a random process-only development key and rejects that constant in production), three pickle-import warnings that overlap with the deserialization findings above, and a swallowed exception in [utils.py](../src/utils.py) around line 23. These are scanner findings, not proof that a usable credential is exposed.

Additional security checks:

- Wrong, expired, altered, and missing tokens were rejected on the exercised protected routes.
- Login brute force was rate-limited after five failed attempts.
- Changing account IDs in unsupported URL paths did not reveal another user's records.
- The Git scan searched textual diffs reachable from local Git refs for a bounded set of key, token, API-key, and bcrypt patterns. It found no matches. It excluded generated `outputs/` files and binary artifacts and is not a full secret-scanning product.
- SlowAPI emitted a Python deprecation warning during pytest: `asyncio.iscoroutinefunction` is deprecated and is scheduled for removal in Python 3.16.
- Ruff passed on all scripts in `tests/validation/`.

## Recommendation sanity simulation

The validation seeded eight hand-made profiles and made 30 recommendation-and-quiz submissions per profile through the real API. Each submission used the correct answer key for the chosen action. Mastery values remained within 0–1 after every submission. The starting and ending mastery vectors below use this topic order: **Algebra, Geometry, Probability, Calculus, Statistics, Linear Algebra**. Changes are behavior under this artificial, all-correct-answer test, not evidence that a learner would improve.

The top-five lists show `topic (difficulty, resource-type label)`. The types such as `video` and `article` are labels only; these are not links to learning materials.

### New learner

- Hybrid top five: Algebra (1.51, project); Algebra (1.74, interactive); Geometry (2.29, project); Geometry (2.00, interactive); Statistics (2.25, video).
- ZPD fallback top five: Geometry (2.00, interactive); Algebra (1.89, quiz); Geometry (2.12, quiz); Statistics (2.25, video); Algebra (1.74, interactive).
- Mastery: `[0.25, 0.25, 0.25, 0.25, 0.25, 0.25]` → `[0.7469, 0.7490, 0.9717, 0.2500, 0.9180, 0.9999]`.
- Overlap: 3 of 5 actions. Visited 5 of 6 topics; 13 distinct actions; longest same-action run 6; 86.00% of returned action slots repeated an action ID already seen in the 30 top-five lists.
- Assessment: starts with low difficulty and weak topics, but Calculus never appears in the 30 chosen submissions.

### Weak in Algebra

- Hybrid top five: Algebra (1.89, quiz); Statistics (2.96, interactive); Probability (3.28, interactive); Calculus (2.89, video); Geometry (2.29, project).
- ZPD fallback top five: Algebra (1.00, article); Algebra (1.00, video); Algebra (1.51, project); Algebra (1.74, interactive); Algebra (1.89, quiz).
- Mastery: `[0.05, 0.50, 0.50, 0.50, 0.50, 0.50]` → `[0.6822, 0.5000, 0.7144, 0.5000, 1.0000, 0.9439]`.
- Overlap: 1 of 5 actions. Visited 4 of 6 topics; 7 distinct actions; longest same-action run 21; repeated-action-slot fraction 90.00%.
- Assessment: both recommend Algebra initially, but the hybrid list shifts most of its five slots away from the only weak topic and includes Probability at difficulty 3.28 for this low-ability profile. The same action was selected 21 times in a row in the simulation.

### Strong everywhere

- Hybrid top five: Probability (3.28, interactive); Calculus (4.02, interactive); Linear Algebra (4.01, project); Linear Algebra (3.50, interactive); Calculus (4.29, project).
- ZPD fallback top five: Calculus (4.29, project); Calculus (4.02, interactive); Linear Algebra (4.01, project); Calculus (3.76, quiz); Linear Algebra (3.69, quiz).
- Mastery: `[0.92, 0.92, 0.92, 0.92, 0.92, 0.92]` → `[0.9200, 0.9200, 0.9529, 1.0000, 0.9723, 0.9200]`.
- Overlap: 3 of 5 actions. Visited 3 of 6 topics; 4 distinct actions; longest same-action run 17; repeated-action-slot fraction 94.67%.
- Assessment: higher difficulty is plausible for this seeded profile, but only three topics are visited and the same action repeats 17 times.

### Low motivation

- Hybrid top five: Linear Algebra (2.61, video); Statistics (2.96, interactive); Probability (2.52, video); Geometry (2.29, project); Probability (2.89, article).
- ZPD fallback top five: Linear Algebra (2.61, video); Probability (2.52, video); Probability (2.89, article); Statistics (2.96, interactive); Algebra (1.89, quiz).
- Mastery: `[0.35, 0.45, 0.40, 0.30, 0.50, 0.40]` → `[0.7777, 0.6845, 0.8003, 0.3000, 0.5000, 1.0000]`.
- Overlap: 4 of 5 actions. Visited 4 of 6 topics; 5 distinct actions; longest same-action run 23; repeated-action-slot fraction 90.00%.
- Assessment: hybrid and fallback are nearly identical, but Calculus and Statistics do not improve or appear in the selected sequence.

### Stuck on low scores

- Hybrid top five: Algebra (1.89, quiz); Algebra (1.51, project); Geometry (2.00, interactive); Algebra (1.74, interactive); Geometry (2.29, project).
- ZPD fallback top five: Algebra (1.51, project); Algebra (1.74, interactive); Geometry (1.73, article); Algebra (1.89, quiz); Geometry (2.00, interactive).
- Mastery: `[0.15, 0.20, 0.18, 0.22, 0.17, 0.19]` → `[0.7160, 0.7326, 0.9934, 0.2200, 0.9093, 0.9993]`.
- Overlap: 4 of 5 actions. Visited 5 of 6 topics; 11 distinct actions; longest same-action run 4; repeated-action-slot fraction 85.33%.
- Assessment: initially focuses on lower-mastery Algebra and Geometry. Calculus remains unchanged and is not visited.

### Near mastery

- Hybrid top five: Probability (3.28, interactive); Calculus (4.02, interactive); Linear Algebra (4.01, project); Linear Algebra (3.50, interactive); Calculus (4.29, project).
- ZPD fallback top five: Calculus (4.29, project); Linear Algebra (4.01, project); Calculus (4.02, interactive); Linear Algebra (3.69, quiz); Calculus (3.76, quiz).
- Mastery: `[0.97, 0.94, 0.96, 0.95, 0.98, 0.93]` → `[0.9700, 0.9400, 0.9764, 1.0000, 0.9800, 0.9300]`.
- Overlap: 3 of 5 actions. Visited 2 of 6 topics; 3 distinct actions; longest same-action run 16; repeated-action-slot fraction 95.33%.
- Assessment: higher difficulty is plausible, but the list excludes the already high-mastery Geometry and Statistics only because it concentrates on Calculus, Probability, and Linear Algebra; only two topics are visited over 30 submissions.

### Uneven learner

- Hybrid top five: Statistics (3.39, project); Probability (3.62, project); Statistics (3.51, quiz); Probability (3.28, interactive); Statistics (2.96, interactive).
- ZPD fallback top five: Geometry (1.73, article); Geometry (2.00, interactive); Geometry (2.12, quiz); Geometry (1.00, video); Geometry (2.29, project).
- Mastery: `[0.90, 0.15, 0.80, 0.20, 0.75, 0.10]` → `[0.9000, 0.8338, 1.0000, 0.2000, 0.9940, 0.1000]`.
- Overlap: 0 of 5 actions. Visited 3 of 6 topics; 4 distinct actions; longest same-action run 5; repeated-action-slot fraction 93.33%.
- Assessment: fallback targets weak Geometry, but hybrid initially recommends already-strong Probability and Statistics. Neither list includes weak Calculus or Linear Algebra in its top five.

### Mid-course learner

- Hybrid top five: Linear Algebra (2.61, video); Statistics (2.25, video); Probability (2.52, video); Calculus (2.89, video); Geometry (2.12, quiz).
- ZPD fallback top five: Probability (2.52, video); Statistics (2.53, article); Statistics (2.25, video); Statistics (2.96, interactive); Probability (2.89, article).
- Mastery: `[0.45, 0.55, 0.35, 0.60, 0.40, 0.50]` → `[0.4500, 0.5500, 0.9998, 0.9973, 0.8041, 0.9463]`.
- Overlap: 2 of 5 actions. Visited 4 of 6 topics; 9 distinct actions; longest same-action run 12; repeated-action-slot fraction 90.00%.
- Assessment: the lists cover several topics, but Algebra and Geometry do not change in the 30 submissions and the recommendation sequence repeatedly selects one action.

Across all eight profiles, **none visited all six topics** during the 30 selected submissions. Repeated action IDs accounted for 85.33%–95.33% of the 150 returned top-five slots per profile. The hybrid and ZPD top-five action overlap ranged from 0 to 4. These results flag repetition and uneven topic coverage; they do not prove the ranking is harmful or beneficial for real learners.

## Load, persistence, and robustness

Each Locust virtual user registered, logged in, requested recommendations, fetched a quiz, submitted it, and fetched history. The temporary load server assigned a separate local client identity per virtual user so the application's per-IP authentication limits would not reject benchmark setup requests. The 50-user result includes the planned server restart and is therefore not a clean steady-state load measurement.

| Concurrent users | Requests | Requests/second | Median | p95 | Errors |
|---:|---:|---:|---:|---:|---:|
| 10 | 2,996 | 103.10 | 10 ms | 29 ms | 0 / 0.00% |
| 50, including restart | 3,513 | 120.90 | 180 ms | 750 ms | 372 / 10.59% |
| 100 | 251 | 18.21 | 4,500 ms | 5,300 ms | 0 / 0.00% |

The 50-user failures were requests receiving no HTTP status during the intentional server stop/start window: 348 recommendation, 11 history, 7 quiz, and 6 interaction requests. They are counted rather than hidden. The 100-user run had no HTTP errors, but latency rose sharply and throughput fell; this is the observed degradation point on this single local test machine. The result should not be treated as a capacity guarantee.

Other measurements:

- First `/api/meta` request, which triggered recommender initialization: **4,561.7 ms**.
- Peak server process RSS observed during the run: **568.8 MiB**.
- After the mid-run restart, the probe user's login returned **200**, history returned **200**, and the pre-restart history item was still present.
- Load server log: **0** `database is locked` lines. The 60-write test also produced no HTTP 5xx responses.
- SQLite was sufficient for these local tests, but the high 100-user latency and single-process setup do not establish that SQLite is suitable for production concurrency. The results alone do not prove PostgreSQL is required; run a representative deployment benchmark before choosing.

## Browser and accessibility

Playwright used Chromium and downloaded axe-core 4.10.3 for this run. The desktop, tablet, and phone screenshots are:

- [Desktop dashboard](../tests/validation/screenshots/desktop-dashboard.png)
- [Tablet dashboard](../tests/validation/screenshots/tablet-dashboard.png)
- [Phone dashboard](../tests/validation/screenshots/phone-dashboard.png)
- [Desktop quiz](../tests/validation/screenshots/desktop-quiz.png)

| Viewport | Size | Document width | Horizontal overflow |
|---|---:|---:|---:|
| Phone | 390 × 844 | 774 px | 384 px |
| Tablet | 768 × 1024 | 774 px | 6 px |
| Desktop | 1440 × 1000 | 1440 px | 0 px |

The phone layout has substantial horizontal overflow; the tablet has a small overflow. Desktop had none.

axe-core found moderate-impact violations:

- Sign-in: no `<main>` landmark and four content nodes outside a landmark (`landmark-one-main`, `region`).
- Dashboard: no level-one heading (`page-has-heading-one`).
- Quiz: three modal/content nodes outside a landmark (`region`).

These are automated checks, not a full screen-reader or keyboard usability review.

Failure-mode observations:

- Blocking `/api/recommend` left the recommendation area showing **“Loading…”** with no visible alert.
- Blocking the local Chart.js asset produced an uncaught `ReferenceError: Chart is not defined`; the chart canvas remained in the page.
- A reload while every API request was delayed by 750 ms completed in 2.812 seconds. The check did not emulate a full mobile carrier or packet loss.

## Rerunning the checks

From the repository root, activate the project's virtual environment. Install validation-only tools if they are not already present; no dependency manifest was changed for this phase.

```sh
source .venv/bin/activate
python -m pip install locust pip-audit bandit playwright psutil requests
python -m playwright install chromium
python -m pytest -q tests/validation
VALIDATION_LOAD_SECONDS=30 python tests/validation/run_load_validation.py
python -m tests.validation.browser_validation
python tests/validation/security_scan.py
```

The load and browser scripts create their own temporary databases. The tests in `tests/validation/` also use pytest's temporary SQLite fixture. Do not point `DATABASE_URL` at `outputs/app.db` when changing these scripts.

## Limits of this validation

- Simulated profiles and correct-answer submissions cannot establish real learning gains, fairness for real populations, or educational suitability.
- The recommender simulation used eight hand-authored states and one local model/artifact set. It is not a statistically representative evaluation.
- Load results came from one macOS development machine, one local process, and a short 30-second run per level. The interrupted 50-user run includes deliberate downtime.
- Browser testing covered Chromium at three viewport sizes, not multiple browsers, real phones/tablets, assistive technology, or a formal WCAG audit.
- The secret scan was a bounded pattern search of local Git history, not a full repository or host scan.
- Production TLS, reverse-proxy behavior, multi-worker rate limiting, backups, monitoring, and recovery were not tested.
- `pip-audit` did not provide CVSS scores or fix versions in its output. Recheck current advisories and supported upgrade paths before deployment.
- At the time of the Phase 4.5 run, no fixes were made; that phase only added validation scripts and this report. The later security follow-up is recorded below.

## Follow-up: security remediation

After the validation run, the security findings above were addressed in a separate change. The historical results above are retained as evidence of what the original test run found.

| Original finding | Follow-up change and verification |
|---|---|
| Account deletion accepted unlimited password guesses. | Added the same five-per-minute SlowAPI limit used by the authentication endpoints. The regression test supplied five wrong passwords and received HTTP 401 each time; the sixth request returned HTTP 429. |
| `python-jose` and its `ecdsa` dependency had advisories in the original manifest scan. | Replaced `python-jose` with PyJWT 2.15.1 in both requirement files, migrated token encoding/decoding, and removed the obsolete packages from the development environment. A fresh `pip-audit` run reported no known vulnerabilities. |
| Runtime Q-table loading used unsafe pickle deserialization. | Replaced the Q-table format and runtime/training/optimizer paths with validated JSON. Added checks for state and action dimensions, finite values, and duplicate states. Regenerated the 1,218-state Q-table at `outputs/models/q_table.json` and removed the obsolete `q_table.pkl` artifact. Missing or invalid Q-table files continue to use the ZPD fallback. |
| Bandit reported a swallowed exception and a hardcoded-secret-pattern match in addition to pickle warnings. | Narrowed the exception handling to the expected `ImportError` and changed production rejection of the old development secret to compare its digest rather than retaining the secret literal. The follow-up Bandit run reported zero findings. |

**Follow-up verification:** the complete suite passed: **45 passed**, **94.88% total coverage**, and three SlowAPI `asyncio.iscoroutinefunction` deprecation warnings. Ruff passed. The security scan script reported no known vulnerable packages, zero Bandit findings across 2,494 lines, and no matches in its bounded Git-history secret-pattern scan. The warnings remain a dependency issue; they were not suppressed.

These changes addressed the security findings listed in this report. The Phase S follow-up below retests the non-security findings and preserves the original results as historical evidence.

## Phase S follow-up validation

**Run date:** 2026-02-18
**Verdict:** **Not ready to deploy.** Phone/tablet overflow and the most obvious immediate recommendation loop were improved, and a larger SQLite connection pool removed the reproduced 100-user pool-timeout 500s. However, latency remains high at 100 users, some profiles still receive only two eligible recommendations, and axe-core still reports moderate landmark/region violations.

All new server and load checks used temporary SQLite databases. The browser script imported the three content packs into its temporary database. `outputs/app.db` was not used.

### Changes and test results

- Recommendation ranking now avoids the immediately previous resource when alternatives are eligible, applies decaying recency penalties, and favors less-recently-covered topics. It uses the most recent 12 history rows. `subject_learning` reuses the topic query, and migration `0003` adds the `(user_id, subject_id, id)` interaction-history index.
- The initial 100-user trace found HTTP 500 responses caused by SQLAlchemy's default pool capacity (5 pooled plus 10 overflow connections); the error was `QueuePool limit of size 5 overflow 10 reached`. File-backed SQLite now uses a 40-connection pool, no overflow, and a 30-second SQLite lock wait. The post-change 30-second 100-user run and a separate 60-second run had zero HTTP errors and zero `database is locked` log lines. This does not establish safety for multiple production workers.
- `pytest -q`: **49 passed**, **81.53% app coverage**. Three SlowAPI `asyncio.iscoroutinefunction` deprecation warnings and one SQLite connection `ResourceWarning` remain.
- Ruff lint and format checks passed after formatting the changed tests and load script. `mypy` passed.
- `pip-audit -r requirements.txt -r requirements-dev.txt`: no known vulnerabilities.
- Bandit reported **two low-severity findings**: B403 for importing `pickle.UnpicklingError` to catch invalid trusted model artifacts, and B101 for an internal invariant assertion in `app/services/recommender.py`. It reported no medium- or high-severity findings. The bounded Git-history secret-pattern scan found no matches.
- A fresh Alembic upgrade reached head and the new interaction index was present. `/ready` returned `{"status":"ready","database":"ok","recommender_mode":"hybrid"}` after retraining.

### Recommendation sanity after Phase S changes

Eight hand-made Mathematics profiles each requested up to five recommendations and completed 30 API quiz submissions using the test database's answer key. The fallback comparison was a separate initial top-five request per profile; the 30-step loop exercised the hybrid recommender. Topic order in the mastery vectors below is Algebra, Geometry, Probability, Calculus, Statistics, Linear Algebra.

| Profile | Initial hybrid recommendations | Mastery before → after 30 submissions | Coverage and assessment |
|---|---|---|---|
| New learner | Algebra article (2); Algebra video (1). Only two eligible resources were returned. | `[.25,.25,.25,.25,.25,.25]` → `[.8468,.9702,.9837,.9105,.9162,.9729]` | All six topics were reached. The low starting mastery aligns with easier Algebra choices, but the initial list has little variety. |
| Weak in Algebra | Algebra video (1); Algebra article (2). Only two eligible resources were returned. | `[.05,.5,.5,.5,.5,.5]` → `[.812,.9655,.9896,.9629,.9426,.9821]` | All six topics were reached. Easier Algebra choices fit the weak area; two choices are still a narrow starting set. |
| Strong everywhere | Linear Algebra quiz (4); Probability interactive (4); Probability video (3); Linear Algebra video (3); Calculus project (2). | `[.92,.92,.92,.92,.92,.92]` → `[.952,.9832,.9996,.9897,.9832,.9994]` | All six topics were reached. The 2–4 difficulty range is plausible for this strong simulated profile; it is not evidence of suitable challenge for real students. |
| Low motivation | Algebra article (2); Algebra video (1). Only two eligible resources were returned. | `[.35,.45,.4,.3,.5,.4]` → `[.7773,.9627,.9875,.9497,.9419,.9872]` | All six topics were reached. Accessible initial difficulty is plausible, but engagement is not enough to create a broader eligible list. |
| Stuck on low scores | Algebra article (2); Algebra video (1). Only two eligible resources were returned. | `[.15,.2,.18,.22,.17,.19]` → `[.8957,.9473,.9824,.9072,.9077,.9706]` | All six topics were reached. Easier initial choices fit the profile; the large simulated mastery changes reflect the simulator and correct-answer submissions only. |
| Near mastery | Linear Algebra quiz (4); Probability interactive (4); Linear Algebra video (3); Calculus project (2); Probability video (3). | `[.97,.94,.96,.95,.98,.93]` → `[.982,.9874,.9998,.9892,.9957,.9997]` | All six topics were reached. More difficult activities appear, but some difficulty-2 content may be easy for this profile. |
| Uneven learner | Geometry video (2); Probability interactive (4); Calculus project (2); Geometry quiz (3); Calculus video (1). | `[.9,.15,.8,.2,.75,.1]` → `[.9871,.9798,.9975,.9651,.9816,.1]` | Five of six topics were reached; Linear Algebra stayed at `.1`. The mix includes easy Calculus and harder Probability, but this profile did not receive full topic coverage in 30 steps. |
| Mid-course learner | Algebra article (2); Algebra video (1). Only two eligible resources were returned. | `[.45,.55,.35,.6,.4,.5]` → `[.8094,.9691,.9921,.9496,.9317,.9893]` | All six topics were reached. The initial list is again limited to two Algebra choices despite mixed mastery. |

Every profile's mastery values remained within `[0,1]`. The longest run of selecting the same resource consecutively was **one** for each profile, so the tested sequence did not get stuck on an endless immediate repeat. However, selected-action duplicate fractions over 30 steps were still **63.33%–76.67%**, and repeated resource slots across the 150 returned top-five positions were **91.61%–92.67%**. These repeated positions are partly a consequence of a small catalog and prerequisite filtering; repetition is reduced, not eliminated.

Hybrid/fallback initial top-five overlap ranged from **2/5 to 5/5**. Five profiles with only two eligible initial activities returned the same two Algebra resources in both modes. The other profiles had overlap of 3/5, 4/5, or 5/5. In this sample, weak profiles got difficulty-1 or difficulty-2 Algebra activities, and high-mastery profiles got some difficulty-3 or difficulty-4 choices. These checks measure software behavior only. Training, learner profiles, and outcomes are simulated; this is not evidence of real learning gains.

### Load and persistence after pool tuning

The 30-second runs attempted a full register → login → recommend → quiz → submit → history loop. These results are local to this machine and are not a capacity guarantee.

| Concurrent users | Requests | Requests/second | Median | p95 | Errors |
|---:|---:|---:|---:|---:|---:|
| 10 | 1,991 | 68.53 | 44 ms | 170 ms | 0 / 0.00% |
| 50, including intentional restart | 1,389 | 47.81 | 330 ms | 3,600 ms | 494 / 35.57% |
| 100 | 892 | 30.73 | 2,100 ms | 7,200 ms | 0 / 0.00% |

The 50-user errors were requests with no HTTP status during the planned stop/start interval: 452 recommendations, 13 quizzes, 19 histories, and 10 submissions. They are restart failures, not steady-state 50-user error rates. After restart, the probe account logged in with HTTP 200 and retrieved its saved history with HTTP 200; the seeded history row remained.

The 100-user failure was reproduced before pool tuning in a 60-second run: the default 5+10 SQLAlchemy pool timed out, producing HTTP 500s. After tuning, a separate 60-second 100-user run completed **2,108 requests** at **35.62 requests/second**, with **2,000 ms median**, **7,800 ms p95**, and **0 errors**. In the final 30-second matrix run, each endpoint completed without an error; registration and login remained the slowest at 5,600/6,500 ms median and 8,000/7,500 ms p95 respectively. SQLite logged zero lock errors.

The updated load script reports endpoint-level timings and error traces and accepts `VALIDATION_LOAD_USERS` and per-level `VALIDATION_LOAD_SECONDS_10`, `_50`, or `_100` overrides. Its default run remains 30 seconds per level.

Before the changes, a cProfile of 100 warm, direct recommendation-service calls took **0.200 seconds total** in ZPD-fallback mode; repeated topic/catalog/prerequisite queries were visible in that profile. Query reuse and the history index address those inexpensive query costs. The full 100-user HTTP run then exposed pool starvation; sizing the SQLite pool removed the observed 500s. After tuning, authentication is the main measured latency: concurrent register/login used bcrypt and remained several seconds per request. Do not reduce password-hash strength as a quick performance workaround. Overall p95 remains poor at 100 users, so the capacity problem is not solved.

The first `/api/meta` request, which initialized the trained model, took **6,896 ms** in the final matrix run. Peak server RSS was **581.5 MiB**. The app loaded in `hybrid` mode. There were no SQLite lock errors; these results do not show that PostgreSQL is required, but they also do not qualify SQLite for multi-worker production.

### Browser and accessibility after changes

The rerun used Chromium, Playwright, and axe-core 4.10.3. Updated screenshots are:

- [Desktop dashboard](../tests/validation/screenshots/desktop-dashboard.png)
- [Tablet dashboard](../tests/validation/screenshots/tablet-dashboard.png)
- [Phone dashboard](../tests/validation/screenshots/phone-dashboard.png)
- [Desktop quiz](../tests/validation/screenshots/desktop-quiz.png)

| Viewport | Size | Document width | Horizontal overflow |
|---|---:|---:|---:|
| Phone | 390 × 844 | 390 px | 0 px |
| Tablet | 768 × 1024 | 768 px | 0 px |
| Desktop | 1440 × 1000 | 1440 px | 0 px |

The original phone overflow was 384 px and tablet overflow was 6 px. Both were absent in this run.

axe-core still reported one moderate-impact `region` violation on sign-in (2 nodes) and dashboard/quiz (4 nodes). Examples were the sign-in username/password and registration controls, which axe reported as content outside landmarks. This is not a full WCAG or assistive-technology audit.

Failure-mode checks showed:

- With the recommendation API blocked, the dashboard displays **“Your dashboard could not be refreshed. Check your connection and try again.”** The message is visible in the recommendation area; the script did not find a `role=alert` node.
- When Chart.js failed to load, the chart is hidden and the page says **“The chart could not load. Your topic progress is still available in the topic map.”** No uncaught JavaScript error occurred; the recommendation remained visible.
- Delaying each API request by 750 ms made the full reload take **5.475 seconds**.
- The wrong-answer browser-flow test displayed the server-provided explanation.

## Phase S rerun commands

From the repository root with validation dependencies and Chromium installed:

```sh
python -m pytest -q --no-cov
ruff check .
ruff format --check .
mypy
bandit -q -r app src
python -m pip_audit -r requirements.txt -r requirements-dev.txt
python tests/validation/security_scan.py
VALIDATION_LOAD_SECONDS=30 python tests/validation/run_load_validation.py
python -c 'import runpy; runpy.run_path("tests/validation/browser_validation.py", run_name="__main__")'
```

The browser validation uses the `runpy` invocation above because direct script invocation did not find the Playwright module in this environment. The scripts create temporary databases and import packs into those temporary databases. Do not set `DATABASE_URL` to `outputs/app.db`.

## Historical Phase S verdict

The following verdict described the state at the end of Phase S. It is retained as history and superseded by the Phase F validation below.

At that point the project was **not ready to deploy**. The original UI overflow and immediate-repeat behavior improved, the trained model loaded, and the pool-timeout 500s were not observed after tuning. However, 100-user p95 remained 7.2–7.8 seconds, five profiles initially received only two eligible activities, one profile missed a topic during the 30-step simulation, moderate axe violations remained, teacher self-registration was public, and no real learner outcomes or production deployment conditions were tested.

## Phase F final validation

**Run date:** 2026-10-10  
**Verdict:** **Not ready for public deployment or real-student decisions.** This phase improves the local demo and documents the remaining risks; it does not qualify the app for production or prove learning benefit. All database checks below used temporary SQLite databases. `outputs/app.db` was excluded.

### Tests and static checks

- Full suite: **53 passed**, with **82.35% application line coverage**.
- The suite emitted three SlowAPI `asyncio.iscoroutinefunction` deprecation warnings and one intermittent SQLite connection `ResourceWarning` while running the learner-profile test. A focused rerun with `ResourceWarning` treated as an error passed; the full-suite warning was not conclusively traced.
- `ruff check .`, `ruff format --check .`, project-configured `mypy`, and `pre-commit run --all-files` passed.
- The broader `mypy app src` check reported **34 diagnostics** across 10 files. The exact per-line list is in [PROJECT_STATE.md](../PROJECT_STATE.md); most involve missing third-party stubs or optional-value inference in the offline pipeline.
- `pip-audit` found **no known vulnerabilities** in the pinned runtime and development requirements.
- Bandit found **no active findings** in 4,471 scanned lines. One narrow B403 warning is suppressed at the `pickle.UnpicklingError` import because that symbol is used only to catch a trusted joblib-load failure; no model file is accepted from users.
- The bounded Git-history secret-pattern scan found **no matches** in scanned text diffs. It is not a dedicated full secret scanner.

### Browser and accessibility

The isolated Playwright/Chromium validation checked sign-in, dashboard, and quiz states. axe-core reported **zero violations** on these screens. Document width matched viewport width at 390 × 844, 768 × 1024, and 1440 × 1000, with zero measured horizontal overflow.

- Blocking the recommendation API showed the message “Your dashboard could not be refreshed. Check your connection and try again.” The text was visible in the recommendation area; the test did not find a `role=alert` element.
- Blocking Chart.js hid the chart and displayed “The chart could not load. Your topic progress is still available in the topic map.” Recommendations remained visible.
- The wrong-answer flow showed the server-provided explanation.
- Delaying API requests by 750 ms made the reload take **5.977 seconds**.
- The first `/ready` request took **9.291 seconds** and returned HTTP 200 with `recommender_mode: hybrid`.
- Two console `ERR_FAILED` messages were produced by the intentional network-failure probes. A browser run attempted while independent checks were running first hit the 10-second registration wait; an isolated rerun completed successfully.
- `python -m scripts.capture_screenshots` captured sign-in, onboarding, diagnostic, dashboard, and quiz screens against its temporary database.

These browser checks are not a screen-reader, keyboard-only, formal WCAG, or multi-browser audit.

### Phase F steady-state load results

The 10-user run lasted 30 seconds; the 50- and 100-user steady-state runs lasted 60 seconds. All tests used one local server process and temporary SQLite data. These values are not directly comparable with longer or differently configured tests and are not capacity guarantees.

| Concurrent users | Requests | Requests/second | Median response | p95 response | Errors |
|---:|---:|---:|---:|---:|---:|
| 10 | 274 | 9.63 | 440 ms | 3,500 ms | 0 / 0.00% |
| 50 | 2,895 | 48.96 | 700 ms | 2,400 ms | 0 / 0.00% |
| 100 | 2,245 | 37.95 | 2,000 ms | 5,800 ms | 0 / 0.00% |

At 100 users, the run completed 453 history reads, 499 quiz reads, 514 recommendation requests, and 479 submissions, in addition to 100 registrations, 100 logins, and 100 profile writes. Authentication remained the slowest stage: registration median/p95 was 6,400/9,000 ms and login was 5,700/6,900 ms. Do not reduce bcrypt strength as a performance workaround.

The 100-user run's first `/api/meta` request, which initializes model assets, took **9,717 ms**. Peak process RSS was **565.4 MiB**. `/ready` and the load report both indicated hybrid mode. The server log had **zero** `database is locked` lines and no captured ASGI error excerpts.

The separate 30-second 50-user interruption test recorded **950 requests, 820 connection failures (86.32%), 40 ms median and 6,100 ms p95** while the server was deliberately stopped and restarted. These failures are not a steady-state 50-user error rate. The post-restart probe login returned HTTP 200, history returned HTTP 200, and its one pre-restart history row remained. A separate 60-second 50-user run without restart had zero errors.

The earlier default SQLite pool produced `QueuePool limit of size 5 overflow 10 reached` errors under a 100-user test. Increasing the file-backed pool to 40 connections removed those observed 500s. The recommender cache and interaction-history index are already in place; direct recommendation profiling did not identify model reloads as a per-request cost. Current 100-user p95 is still 5.8 seconds, so high-load capacity remains unresolved. These results show neither that PostgreSQL is required nor that SQLite is suitable for production.

### Before and after notes

| Area | Before stabilization | Latest Phase F evidence |
|---|---|---|
| 100-user database pool | Default 5 plus 10 overflow timed out and returned HTTP 500 errors. | 40-connection SQLite pool: 2,245 requests in 60 seconds, 0 HTTP errors, 0 lock-log lines; p95 5,800 ms. |
| 100-user response time | Earlier post-pool 60-second run: 35.62 requests/second, 2,000 ms median, 7,800 ms p95. | Latest 60-second run: 37.95 requests/second, 2,000 ms median, 5,800 ms p95. This is a local run-to-run comparison, not proof that documentation/accessibility work caused the difference. |
| Phone/tablet layout | Earlier document overflow was 384 px on phone and 6 px on tablet. | 0 px overflow at 390, 768, and 1440 px. |
| axe checks | Earlier tests reported landmark/region violations. | 0 violations in the latest sign-in, dashboard, and quiz checks. |
| Dependency/static security scans | Earlier scans identified vulnerable packages and Bandit findings. | No known dependency vulnerabilities and no active Bandit findings; one narrowly explained B403 suppression remains. |

### How to rerun

From the repository root with the development environment installed:

```sh
pytest
playwright install chromium
ruff check .
ruff format --check .
mypy
pre-commit run --all-files
bandit -q -r app src
python -m pip_audit -r requirements.txt -r requirements-dev.txt
python tests/validation/security_scan.py
python -m scripts.capture_screenshots
python -c 'import runpy; runpy.run_path("tests/validation/browser_validation.py", run_name="__main__")'
VALIDATION_LOAD_SECONDS=30 python tests/validation/run_load_validation.py
VALIDATION_LOAD_USERS=50 VALIDATION_RESTART_50=0 VALIDATION_LOAD_SECONDS_50=60 python tests/validation/run_load_validation.py
VALIDATION_LOAD_USERS=100 VALIDATION_LOAD_SECONDS_100=60 python tests/validation/run_load_validation.py
```

The default load command intentionally restarts the server during the 50-user test to check persistence. Set `VALIDATION_RESTART_50=0` for a separate steady-state 50-user measurement. Every validation script creates temporary databases. Do not point any of them at `outputs/app.db`.

### Remaining release risks and use verdict

- **Personal/local use:** Suitable for a local demo with synthetic or disposable data, a private secret, and database backups. The learner level and recommendation outputs are not validated assessments.
- **Classroom demo:** Suitable only as a supervised local demonstration with draft questions, synthetic accounts, and no sensitive real-student data. Do not use it to make real educational decisions.
- **Public internet deployment:** **Not ready.** Restrict teacher provisioning, complete deployment security and operational work, and test the actual hosting stack first.
- **Real students with real decisions:** **Not ready.** There is no evidence of real learning gains or fairness, and consent, privacy, content quality, and educational validation are incomplete.

The load numbers exercise software behavior only. All model training, learner profiles, recommendations, and reported gains remain simulated.
