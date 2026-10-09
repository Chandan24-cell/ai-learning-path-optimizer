// ==========================================================================
// Config
// ==========================================================================
const API = "";
// ==========================================================================
// State
// ==========================================================================
let TOKEN = localStorage.getItem("token") || null;
let REFRESH_TOKEN = localStorage.getItem("refresh_token") || null;
let USERNAME = localStorage.getItem("username") || "";
let CURRENT_RECS = [];
let CURRENT_ACTION = null;
let CURRENT_QUESTIONS = [];
let CURRENT_SESSION_ID = null;
let CURRENT_SUBJECT_ID = null;
let CURRENT_PROGRESS = null;
let IS_DIAGNOSTIC = false;
let ACTIVITY_START = null;
let QUIZ_COMPLETE = false;
let MASTERY_CHART = null;
let PROFILE_OPTIONS = null;
let ENROLLED_SUBJECTS = [];
let SELECTED_SUBJECTS = [];
let PENDING_BOOK_REFERENCES = {};
let PROFILE_FOR_SUBJECTS = null;
let PROFILE_EDITING = false;
let AVAILABLE_PACKS = [];
let MANUAL_PATH_CANDIDATES = [];
let MANUAL_PATH_FAILURES = {};

// ==========================================================================
// Auth
// ==========================================================================
function showMsg(elId, text, cls = "") {
  const el = document.getElementById(elId);
  el.textContent = text;
  el.className = "msg " + cls;
}

async function fetchWithFeedback(url, options) {
  try {
    return await fetch(url, options);
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The request timed out. Check your connection and try again.");
    }
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
}

function responseError(body, status) {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => item.msg).filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return `The request failed (HTTP ${status}). Please try again.`;
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  let res = await fetchWithFeedback(API + path, { ...opts, headers });
  if (res.status === 401 && TOKEN && REFRESH_TOKEN && path !== "/api/auth/refresh") {
    try {
      const refreshed = await fetchWithFeedback(API + "/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: REFRESH_TOKEN }),
      });
      if (!refreshed.ok) throw new Error("Refresh refused");
      const auth = await refreshed.json();
      storeAuth(auth);
      headers.Authorization = "Bearer " + TOKEN;
      res = await fetchWithFeedback(API + path, { ...opts, headers });
    } catch (error) {
      clearAuth();
      if (error.message.startsWith("Could not reach") || error.message.includes("timed out")) {
        throw error;
      }
      throw new Error("Your session expired. Please log in again.");
    }
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(responseError(body, res.status));
  return body;
}

async function doLogin() {
  const username = document.getElementById("login-user").value.trim();
  const password = document.getElementById("login-pass").value;
  if (!username || !password) return showMsg("auth-msg", "Enter username and password", "error");
  try {
    const r = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    saveAuth(r);
  } catch (e) {
    showMsg("auth-msg", e.message, "error");
  }
}

async function doRegister() {
  const username = document.getElementById("reg-user").value.trim();
  const password = document.getElementById("reg-pass").value;
  if (username.length < 3) return showMsg("auth-msg", "Username must be ≥ 3 chars", "error");
  if (password.length < 10) return showMsg("auth-msg", "Password must be at least 10 characters", "error");
  try {
    const r = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username,
        password,
        role: document.getElementById("reg-role").value,
      }),
    });
    saveAuth(r);
  } catch (e) {
    showMsg("auth-msg", e.message, "error");
  }
}

function storeAuth(auth) {
  TOKEN = auth.token;
  REFRESH_TOKEN = auth.refresh_token;
  USERNAME = auth.username;
  localStorage.setItem("token", TOKEN);
  localStorage.setItem("refresh_token", REFRESH_TOKEN);
  localStorage.setItem("username", USERNAME);
}

function saveAuth(auth) {
  storeAuth(auth);
  enterApp();
}

function clearAuth() {
  TOKEN = null; USERNAME = "";
  REFRESH_TOKEN = null;
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("username");
  document.getElementById("auth-view").hidden = false;
  document.getElementById("app-view").hidden = true;
}

async function logout() {
  const refreshToken = REFRESH_TOKEN;
  clearAuth();
  if (refreshToken) {
    await fetch(API + "/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).catch(() => {});
  }
}

async function deleteAccount() {
  if (!window.confirm("Delete your account and all saved learning data? This cannot be undone.")) return;
  const password = window.prompt("Enter your password to confirm account deletion:");
  if (password === null) return;
  try {
    await api("/api/account", { method: "DELETE", body: JSON.stringify({ password }) });
    clearAuth();
    window.alert("Your account and saved learning data were deleted.");
  } catch (e) {
    window.alert(e.message);
  }
}

// ==========================================================================
// Dashboard
// ==========================================================================
async function enterApp() {
  document.getElementById("auth-view").hidden = true;
  document.getElementById("app-view").hidden = false;
  document.getElementById("user-label").textContent = "Signed in as " + USERNAME;
  let profileStatus;
  try {
    profileStatus = await api("/api/me/profile");
  } catch (e) {
    showMsg("subject-message", e.message, "error");
    return;
  }
  if (profileStatus.required && !profileStatus.completed) {
    document.getElementById("dashboard-content").hidden = true;
    document.getElementById("onboarding-card").hidden = false;
    document.getElementById("edit-profile-button").hidden = true;
    document.getElementById("learner-profile-form").hidden = false;
    document.getElementById("subject-step").hidden = true;
    await renderProfileForm(null, false);
    return;
  }
  try {
    const subjects = await api("/api/me/subjects");
    if (!subjects.subjects.length) {
      document.getElementById("dashboard-content").hidden = true;
      document.getElementById("onboarding-card").hidden = false;
      document.getElementById("edit-profile-button").hidden = true;
      await beginSubjectStep(profileStatus.profile, true);
      return;
    }
  } catch (e) {
    showMsg("subject-message", e.message, "error");
    return;
  }
  document.getElementById("onboarding-card").hidden = true;
  document.getElementById("dashboard-content").hidden = false;
  document.getElementById("learner-profile-form").hidden = true;
  document.getElementById("subject-step").hidden = true;
  document.getElementById("edit-profile-button").hidden = !profileStatus.required;
  await loadSubjects();
}

function fillProfileSelect(id, items, selected, includeEmpty = false) {
  const select = document.getElementById(id);
  select.replaceChildren();
  if (includeEmpty) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select (optional)";
    select.appendChild(placeholder);
  }
  items.forEach(item => {
    const option = document.createElement("option");
    option.value = typeof item === "string" ? item : item.id;
    option.textContent = typeof item === "string" ? item : item.label;
    option.selected = option.value === selected;
    select.appendChild(option);
  });
}

async function renderProfileForm(profile, editing) {
  try {
    const options = await api("/api/onboarding/options");
    PROFILE_OPTIONS = options;
    document.getElementById("privacy-notice").textContent = options.privacy_notice;
    fillProfileSelect(
      "profile-country",
      options.countries,
      profile?.country || options.countries[0]?.id
    );
    fillProfileSelect("profile-language", options.languages, profile?.language || "English");
    fillProfileSelect(
      "profile-education-level",
      options.education_levels,
      profile?.education_level || "middle_school"
    );
    fillProfileSelect(
      "profile-institution-type",
      options.institution_types,
      profile?.institution_type || "self_study"
    );
    fillProfileSelect("profile-goal", options.learning_goals, profile?.learning_goal || "skill");
    fillProfileSelect(
      "profile-style",
      options.learning_styles,
      profile?.learning_style || "mixed"
    );
    fillProfileSelect(
      "profile-experience",
      options.prior_experience_options,
      profile?.prior_experience || "new"
    );
    document.getElementById("profile-grade-year").value = profile?.grade_year || "";
    document.getElementById("profile-field").value = profile?.field_of_study || "";
    document.getElementById("profile-weekly-time").value = profile?.weekly_time_hours || "3";
    document.getElementById("profile-consent").checked = editing;
    document.getElementById("onboarding-title").textContent =
      editing ? "Edit your learner profile" : "Set up your learner profile";
    document.getElementById("save-profile-button").textContent =
      editing ? "Save changes" : "Save profile and continue";
    document.getElementById("cancel-profile-edit").hidden = !editing;
    document.getElementById("delete-profile-button").hidden = !editing;
    updateCurriculumOptions(options, profile?.curriculum_program || "");
  } catch (e) {
    showMsg("profile-message", e.message, "error");
  }
}

function updateCurriculumOptions(options, selected = "") {
  const countryId = document.getElementById("profile-country").value;
  const country = options.countries.find(item => item.id === countryId);
  fillProfileSelect("profile-curriculum", country?.curricula || [], selected, true);
}

async function beginSubjectStep(profile, required) {
  PROFILE_FOR_SUBJECTS = profile || PROFILE_FOR_SUBJECTS;
  const includeSamples = document.getElementById("include-sample-subjects").checked;
  const [mine, packs] = await Promise.all([
    api("/api/me/subjects"),
    api(`/api/subjects${includeSamples ? "?include_samples=true" : ""}`),
  ]);
  ENROLLED_SUBJECTS = mine.subjects;
  SELECTED_SUBJECTS = mine.subjects.map(subject => ({ ...subject }));
  AVAILABLE_PACKS = packs.subjects;
  PENDING_BOOK_REFERENCES = {};
  document.getElementById("onboarding-title").hidden = true;
  document.getElementById("profile-intro").hidden = true;
  document.getElementById("learner-profile-form").hidden = true;
  document.getElementById("subject-step").hidden = false;
  document.getElementById("onboarding-card").hidden = false;
  document.getElementById("dashboard-content").hidden = true;
  document.getElementById("edit-profile-button").hidden = required;
  document.getElementById("finish-subject-step").textContent = required
    ? "Choose subjects and continue"
    : "Save subjects";
  document.getElementById("cancel-subject-step").hidden = required;
  document.getElementById("cancel-profile-edit").hidden = true;
  document.getElementById("delete-profile-button").hidden = true;
  const currentDepth = mine.subjects[0]?.target_depth;
  const education = PROFILE_FOR_SUBJECTS?.education_level || "middle_school";
  const defaultDepth = ["phd", "postgraduate", "professional"].includes(education)
    ? "advanced"
    : education === "undergraduate"
      ? "intermediate"
      : "beginner";
  document.getElementById("subject-target-depth").value = currentDepth || defaultDepth;
  const packErrors = packs.errors || [];
  const packErrorMessage = document.getElementById("pack-catalog-errors");
  packErrorMessage.hidden = packErrors.length === 0;
  packErrorMessage.textContent = packErrors
    .map(error => `Pack folder "${error.directory}" could not be loaded: ${error.message}`)
    .join(" ");
  document.getElementById("onboarding-pack-select").replaceChildren();
  if (!AVAILABLE_PACKS.length && !packErrors.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No content packs found";
    option.disabled = true;
    option.selected = true;
    document.getElementById("onboarding-pack-select").appendChild(option);
  }
  AVAILABLE_PACKS.forEach(subject => {
    const option = document.createElement("option");
    option.value = subject.id;
    option.textContent = `${subject.name} (${subject.installed ? "installed" : "not installed"})`;
    document.getElementById("onboarding-pack-select").appendChild(option);
  });
  renderSelectedSubjects();
  renderReferenceSubjectSelect();
  showMsg("subject-step-message", "");
}

function addSelectedSubject(subject) {
  if (SELECTED_SUBJECTS.some(item => item.id === subject.id)) {
    showMsg("subject-step-message", "That subject is already in your list.", "error");
    return false;
  }
  if (SELECTED_SUBJECTS.length >= 8) {
    showMsg("subject-step-message", "You can choose up to 8 subjects. Remove one to add another.", "error");
    return false;
  }
  SELECTED_SUBJECTS.push(subject);
  renderSelectedSubjects();
  renderReferenceSubjectSelect();
  showMsg("subject-step-message", "");
  return true;
}

function renderSelectedSubjects() {
  const chips = document.getElementById("chosen-subjects");
  chips.replaceChildren();
  SELECTED_SUBJECTS.forEach(subject => {
    const item = document.createElement("li");
    item.className = "subject-chip";
    const name = document.createElement("span");
    name.textContent = subject.name;
    if (subject.status === "draft") {
      const badge = document.createElement("b");
      badge.className = "draft-badge";
      badge.textContent = "Draft / unreviewed";
      item.append(name, badge);
    } else {
      item.appendChild(name);
    }
    const reference = PENDING_BOOK_REFERENCES[subject.id];
    if (reference) {
      const book = document.createElement("span");
      book.className = "muted small";
      book.textContent = `Reference: ${reference.title}`;
      item.appendChild(book);
    }
    const remove = document.createElement("button");
    remove.className = "btn ghost small";
    remove.type = "button";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove ${subject.name}`);
    remove.addEventListener("click", () => {
      SELECTED_SUBJECTS = SELECTED_SUBJECTS.filter(item => item.id !== subject.id);
      renderSelectedSubjects();
      renderReferenceSubjectSelect();
      showMsg(
        "subject-step-message",
        `${subject.name} removed from your selection. ${SELECTED_SUBJECTS.length} of 8 selected.`,
        "ok"
      );
    });
    item.appendChild(remove);
    chips.appendChild(item);
  });
  document.getElementById("subject-count").textContent = `${SELECTED_SUBJECTS.length} of 8`;
  const atLimit = SELECTED_SUBJECTS.length >= 8;
  document.getElementById("subject-limit-message").hidden = !atLimit;
  document.getElementById("add-pack-subject").disabled = atLimit || !AVAILABLE_PACKS.length;
  document.getElementById("add-manual-subject").disabled = atLimit;
  document.getElementById("search-subjects").disabled = atLimit;
  document.querySelectorAll("[data-subject-add]").forEach(button => {
    button.disabled = atLimit;
  });
  const enrichSelect = document.getElementById("enrich-manual-select");
  enrichSelect.replaceChildren();
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "No empty manual subject selected";
  enrichSelect.appendChild(emptyOption);
  SELECTED_SUBJECTS.filter(subject => subject.source === "manual" && !subject.topic_count)
    .forEach(subject => {
      const option = document.createElement("option");
      option.value = subject.id;
      option.textContent = subject.name;
      enrichSelect.appendChild(option);
    });
}

function renderReferenceSubjectSelect() {
  const select = document.getElementById("book-subject-select");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Choose a subject";
  select.appendChild(placeholder);
  SELECTED_SUBJECTS.forEach(subject => {
    const option = document.createElement("option");
    option.value = subject.id;
    option.textContent = subject.name;
    select.appendChild(option);
  });
}

function safeExternalUrl(value) {
  try {
    const parsed = new URL(value);
    const permittedHosts = new Set([
      "en.wikipedia.org",
      "en.wikibooks.org",
      "www.wikidata.org",
      "openlibrary.org",
      "api.openalex.org",
      "openalex.org",
      "openstax.org",
      "ocw.mit.edu",
    ]);
    return parsed.protocol === "https:" && permittedHosts.has(parsed.hostname)
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}

function makeExternalLink(label, url) {
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) return document.createTextNode(label);
  const link = document.createElement("a");
  link.href = safeUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label;
  return link;
}

function renderQuestion(container, item, index) {
  const question = document.createElement("div");
  question.className = "question";
  question.dataset.questionId = item.id;
  const prompt = document.createElement("p");
  prompt.textContent = `Q${index + 1}. ${item.question}`;
  question.appendChild(prompt);
  if (item.status) {
    const status = document.createElement("p");
    status.className = "muted small";
    status.textContent = item.status;
    question.appendChild(status);
  }
  item.options.forEach((option, optionIndex) => {
    const label = document.createElement("label");
    label.className = "option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = `q${index}`;
    input.value = String(optionIndex);
    const text = document.createElement("span");
    text.textContent = option;
    label.append(input, text);
    question.appendChild(label);
  });
  const report = document.createElement("button");
  report.type = "button";
  report.className = "btn btn-small";
  report.textContent = "Report this question";
  report.addEventListener("click", async () => {
    report.disabled = true;
    try {
      await api(
        `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/questions/${encodeURIComponent(item.id)}/report`,
        { method: "POST", body: JSON.stringify({ reason: "other" }) }
      );
      report.textContent = "Question reported";
    } catch (error) {
      report.disabled = false;
      showMsg("modal-msg", error.message, "error");
    }
  });
  question.appendChild(report);
  container.appendChild(question);
}

function renderQuestionFeedback(container, feedback) {
  const result = document.createElement("section");
  result.className = "question-feedback";
  const status = document.createElement("p");
  status.textContent = feedback.correct
    ? "Correct."
    : `Not quite. The correct answer is ${feedback.correct_answer}.`;
  result.appendChild(status);
  const sentence = document.createElement("p");
  sentence.textContent = feedback.source_sentence || feedback.explanation || "";
  result.appendChild(sentence);
  if (feedback.source_url) {
    result.appendChild(makeExternalLink("View source", feedback.source_url));
  }
  if (feedback.attribution) {
    const attribution = document.createElement("p");
    attribution.className = "muted small";
    attribution.textContent = feedback.attribution;
    result.appendChild(attribution);
  }
  container.appendChild(result);
}

async function searchDiscoveredSubjects() {
  const query = document.getElementById("discovery-query").value.trim();
  const results = document.getElementById("discovery-results");
  const preview = document.getElementById("path-preview");
  results.replaceChildren();
  preview.replaceChildren();
  if (query.length < 2) {
    showMsg("subject-step-message", "Enter at least 2 characters to search.", "error");
    return;
  }
  showMsg("subject-step-message", "Searching public sources…");
  try {
    const level = PROFILE_FOR_SUBJECTS?.education_level || "middle_school";
    const data = await api(`/api/discovery/search?q=${encodeURIComponent(query)}&level=${encodeURIComponent(level)}`);
    data.results.forEach(candidate => {
      const card = document.createElement("article");
      card.className = "discovery-result";
      const title = document.createElement("strong");
      title.textContent = candidate.name;
      const source = document.createElement("p");
      source.className = "muted small";
      source.append(
        document.createTextNode(`${candidate.source} · confidence ${Math.round(candidate.confidence * 100)}% · `),
        makeExternalLink("Source", candidate.source_url)
      );
      const summary = document.createElement("p");
      summary.textContent = candidate.summary || "No short summary was supplied by this source.";
      const previewButton = document.createElement("button");
      previewButton.type = "button";
      previewButton.className = "btn ghost small";
      previewButton.textContent = "Preview topic path";
      const path = document.createElement("ol");
      const addButton = document.createElement("button");
      addButton.type = "button";
      addButton.className = "btn primary";
      addButton.textContent = "Add subject";
      addButton.dataset.subjectAdd = "true";
      addButton.disabled = true;
      const enrichButton = document.createElement("button");
      enrichButton.type = "button";
      enrichButton.className = "btn ghost small";
      enrichButton.textContent = "Enrich selected manual subject";
      enrichButton.disabled = true;
      enrichButton.addEventListener("click", async () => {
        const manualSubjectId = document.getElementById("enrich-manual-select").value;
        if (!manualSubjectId) return;
        enrichButton.disabled = true;
        try {
          const subject = await api("/api/discovery/subjects", {
            method: "POST",
            body: JSON.stringify({
              name: candidate.name,
              source_url: candidate.source_url,
              manual_subject_id: manualSubjectId,
              target_depth: document.getElementById("subject-target-depth").value,
            }),
          });
          SELECTED_SUBJECTS = SELECTED_SUBJECTS.map(item =>
            item.id === manualSubjectId ? { ...item, ...subject } : item
          );
          renderSelectedSubjects();
          showMsg("subject-step-message", `${subject.name} enriched with a draft path. Draft / unreviewed.`, "ok");
        } catch (error) {
          showMsg("subject-step-message", error.message, "error");
          enrichButton.disabled = false;
        }
      });
      previewButton.addEventListener("click", async () => {
        path.replaceChildren();
        addButton.disabled = true;
        try {
          const params = new URLSearchParams({
            name: candidate.name,
            source_url: candidate.source_url,
            level,
          });
          const result = await api(`/api/discovery/preview?${params}`);
          if (!result.topics.length) {
            path.textContent = result.message || "No topic path could be previewed.";
            return;
          }
          result.topics.forEach(topic => {
            const line = document.createElement("li");
            line.textContent = `${topic.name} · ${topic.depth}`;
            path.appendChild(line);
          });
          addButton.disabled = SELECTED_SUBJECTS.length >= 8;
          enrichButton.disabled =
            !document.getElementById("enrich-manual-select").value;
        } catch (error) {
          path.textContent = error.message;
        }
      });
      addButton.addEventListener("click", async () => {
        if (SELECTED_SUBJECTS.length >= 8) {
          renderSelectedSubjects();
          return;
        }
        if (SELECTED_SUBJECTS.some(item => item.name === candidate.name)) {
          showMsg("subject-step-message", "That subject is already in your list.", "error");
          return;
        }
        addButton.disabled = true;
        try {
          const subject = await api("/api/discovery/subjects", {
            method: "POST",
            body: JSON.stringify({
              name: candidate.name,
              source_url: candidate.source_url,
              target_depth: document.getElementById("subject-target-depth").value,
            }),
          });
          if (addSelectedSubject(subject)) {
            ENROLLED_SUBJECTS = [
              ...ENROLLED_SUBJECTS.filter(item => item.id !== subject.id),
              subject,
            ];
          }
          showMsg("subject-step-message", `${subject.name} added. Draft / unreviewed.`, "ok");
        } catch (error) {
          showMsg("subject-step-message", error.message, "error");
          addButton.disabled = SELECTED_SUBJECTS.length >= 8;
        }
      });
      card.append(title, source, summary, previewButton, path, addButton, enrichButton);
      results.appendChild(card);
    });
    if (!data.results.length) {
      const message = document.createElement("p");
      message.className = "muted";
      message.textContent = data.message || data.errors?.join(" ") || "No subjects were found.";
      results.appendChild(message);
      showMsg(
        "subject-step-message",
        data.errors?.length
          ? `Search is unavailable: ${data.errors.join(" ")}`
          : data.message || "No subjects were found. Try another search.",
        data.errors?.length ? "error" : ""
      );
    } else if (data.errors?.length) {
      const warning = document.createElement("p");
      warning.className = "muted small";
      warning.textContent = data.errors.join(" ");
      results.appendChild(warning);
      showMsg(
        "subject-step-message",
        `Found ${data.results.length} subjects, but some sources are unavailable: ${data.errors.join(" ")}`,
        "ok"
      );
    } else {
      showMsg("subject-step-message", `Found ${data.results.length} subjects.`, "ok");
    }
  } catch (error) {
    results.textContent = `Subject search is unavailable: ${error.message}`;
    showMsg("subject-step-message", `Search failed: ${error.message}`, "error");
  }
}

async function searchReferenceBooks() {
  const query = document.getElementById("book-query").value.trim();
  const results = document.getElementById("book-results");
  results.replaceChildren();
  if (query.length < 2) {
    showMsg("subject-step-message", "Enter at least 2 characters to search for books.", "error");
    return;
  }
  try {
    const data = await api(`/api/discovery/books?q=${encodeURIComponent(query)}`);
    data.results.forEach(book => {
      const card = document.createElement("article");
      card.className = "discovery-result";
      const title = document.createElement("strong");
      title.textContent = book.title;
      const details = document.createElement("p");
      details.textContent = [
        book.authors.join(", "),
        book.edition,
        book.publisher,
        book.year,
        book.isbn.length ? `ISBN ${book.isbn.join(", ")}` : "",
      ].filter(Boolean).join(" · ");
      const source = document.createElement("p");
      source.appendChild(makeExternalLink("Open Library record", book.link));
      const attach = document.createElement("button");
      attach.className = "btn ghost small";
      attach.type = "button";
      attach.textContent = "Use as reference";
      attach.disabled = !SELECTED_SUBJECTS.length;
      attach.addEventListener("click", () => {
        const subjectId = document.getElementById("book-subject-select").value;
        if (!subjectId) {
          showMsg("subject-step-message", "Choose a subject for this reference first.", "error");
          return;
        }
        PENDING_BOOK_REFERENCES[subjectId] = book;
        renderSelectedSubjects();
        showMsg("subject-step-message", "Reference book saved with that subject.", "ok");
      });
      card.append(title, details, source, attach);
      results.appendChild(card);
    });
    if (!data.results.length) {
      const message = document.createElement("p");
      message.className = "muted";
      message.textContent = data.message || data.errors?.join(" ") || "No books were found.";
      results.appendChild(message);
    }
  } catch (error) {
    results.textContent = `Book search is unavailable: ${error.message}`;
  }
}

async function finishSubjectStep() {
  if (SELECTED_SUBJECTS.length < 1 || SELECTED_SUBJECTS.length > 8) {
    showMsg("subject-step-message", "Choose between 1 and 8 subjects to continue.", "error");
    return;
  }
  const keep = new Set(SELECTED_SUBJECTS.map(subject => subject.id));
  const targetDepth = document.getElementById("subject-target-depth").value;
  try {
    for (const subject of ENROLLED_SUBJECTS) {
      if (!keep.has(subject.id)) {
        await api(`/api/subjects/${encodeURIComponent(subject.id)}/enroll`, { method: "DELETE" });
      }
    }
    for (const subject of SELECTED_SUBJECTS) {
      await api(`/api/subjects/${encodeURIComponent(subject.id)}/enroll`, {
        method: "POST",
        body: JSON.stringify({ target_depth: targetDepth }),
      });
      const referenceBook = PENDING_BOOK_REFERENCES[subject.id];
      if (referenceBook) {
        await api(`/api/subjects/${encodeURIComponent(subject.id)}/reference`, {
          method: "PUT",
          body: JSON.stringify(referenceBook),
        });
      }
    }
    document.getElementById("onboarding-card").hidden = true;
    document.getElementById("subject-step").hidden = true;
    document.getElementById("dashboard-content").hidden = false;
    document.getElementById("edit-profile-button").hidden = false;
    await loadSubjects();
  } catch (error) {
    showMsg("subject-step-message", error.message, "error");
  }
}

async function submitLearnerProfile(event) {
  event.preventDefault();
  const form = document.getElementById("learner-profile-form");
  const values = Object.fromEntries(new FormData(form).entries());
  values.curriculum_program = values.curriculum_program || null;
  values.weekly_time_hours = Number(values.weekly_time_hours);
  values.consent = document.getElementById("profile-consent").checked;
  try {
    const result = await api("/api/me/profile", {
      method: "PUT",
      body: JSON.stringify(values),
    });
    PROFILE_FOR_SUBJECTS = result.profile;
    if (PROFILE_EDITING) {
      PROFILE_EDITING = false;
      document.getElementById("onboarding-card").hidden = true;
      document.getElementById("dashboard-content").hidden = false;
      document.getElementById("edit-profile-button").hidden = false;
      await loadSubjects();
    } else {
      await beginSubjectStep(result.profile, true);
    }
  } catch (e) {
    showMsg("profile-message", e.message, "error");
  }
}

async function editLearnerProfile() {
  try {
    const result = await api("/api/me/profile");
    document.getElementById("dashboard-content").hidden = true;
    document.getElementById("onboarding-card").hidden = false;
    document.getElementById("learner-profile-form").hidden = false;
    document.getElementById("subject-step").hidden = true;
    document.getElementById("onboarding-title").hidden = false;
    document.getElementById("profile-intro").hidden = false;
    PROFILE_EDITING = true;
    await renderProfileForm(result.profile, true);
  } catch (e) {
    showMsg("subject-message", e.message, "error");
  }
}

async function deleteLearnerProfile() {
  if (!window.confirm("Delete your learner profile? You will need to complete onboarding again.")) {
    return;
  }
  try {
    await api("/api/me/profile", { method: "DELETE" });
    await enterApp();
  } catch (e) {
    showMsg("profile-message", e.message, "error");
  }
}

async function loadSubjects() {
  try {
    const [mine, available] = await Promise.all([
      api("/api/me/subjects"),
      api("/api/subjects"),
    ]);
    const mySubjects = mine.subjects;
    ENROLLED_SUBJECTS = mySubjects;
    CURRENT_SUBJECT_ID = mine.active_subject_id || mySubjects[0]?.id || null;
    const activeSelect = document.getElementById("subject-select");
    activeSelect.replaceChildren();
    mySubjects.forEach(subject => {
      const option = document.createElement("option");
      option.value = subject.id;
      option.textContent = subject.name;
      option.selected = subject.id === CURRENT_SUBJECT_ID;
      activeSelect.appendChild(option);
    });
    const availableSelect = document.getElementById("available-subjects");
    availableSelect.replaceChildren();
    available.subjects
      .filter(subject => !mySubjects.some(enrolled => enrolled.id === subject.id))
      .forEach(subject => {
        const option = document.createElement("option");
        option.value = subject.id;
        option.textContent = subject.name;
        availableSelect.appendChild(option);
      });
    document.getElementById("enroll-subject").disabled = !availableSelect.value;
    if (CURRENT_SUBJECT_ID) {
      await api("/api/me/subject", {
        method: "PUT",
        body: JSON.stringify({ subject_id: CURRENT_SUBJECT_ID }),
      });
      await refreshAll();
    } else {
      showMsg("subject-message", "Choose or add a subject to get started.", "");
      document.getElementById("topic-map").replaceChildren();
      document.getElementById("top-rec").textContent = "Choose a subject to see recommendations.";
      document.getElementById("alt-recs").replaceChildren();
      document.getElementById("improvement-list").replaceChildren();
    }
  } catch (e) {
    showMsg("subject-message", e.message, "error");
    document.getElementById("top-rec").textContent =
      "Your subjects could not be loaded. Check your connection and try again.";
  }
}

function setPathRecoveryMessage(message, isError = false) {
  const element = document.getElementById("empty-path-message");
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function updateEmptyPathRecovery(progress) {
  const recovery = document.getElementById("empty-path-recovery");
  const hasTopics = progress.topics.length > 0;
  const canBuildPath = ["manual", "discovered"].includes(progress.subject.source);
  recovery.hidden = hasTopics || !canBuildPath;
  if (hasTopics) delete MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID];
  if (hasTopics || !canBuildPath) return;

  const description =
    MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] || progress.subject.description || "";
  const needsRetry = /search again|pick from results/i.test(description);
  setPathRecoveryMessage(
    needsRetry
      ? description
      : "This subject has no topics yet. Build a learning path from the internet to start."
  );
  document.getElementById("build-subject-path").hidden = needsRetry;
  document.getElementById("retry-subject-discovery").hidden = !needsRetry;
  document.getElementById("pick-discovery-results").hidden = !needsRetry;
  document.getElementById("manual-path-results").replaceChildren();
}

async function runManualPathBuild() {
  const buttons = [
    document.getElementById("build-subject-path"),
    document.getElementById("retry-subject-discovery"),
    document.getElementById("pick-discovery-results"),
  ];
  buttons.forEach(button => { button.disabled = true; });
  setPathRecoveryMessage("Building your learning path...");
  try {
    const result = await api(
      `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/build-path`,
      { method: "POST" }
    );
    if (result.path_status === "built") {
      delete MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID];
      await loadSubjects();
      showMsg("subject-message", result.message, "ok");
      return;
    }
    MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] = result.message;
    setPathRecoveryMessage(result.message, true);
    document.getElementById("build-subject-path").hidden = true;
    document.getElementById("retry-subject-discovery").hidden = false;
    document.getElementById("pick-discovery-results").hidden = false;
  } catch (error) {
    const message =
      `The learning path could not be built: ${error.message}. Search again or pick from results.`;
    MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] = message;
    setPathRecoveryMessage(message, true);
    document.getElementById("build-subject-path").hidden = true;
    document.getElementById("retry-subject-discovery").hidden = false;
    document.getElementById("pick-discovery-results").hidden = false;
  } finally {
    buttons.forEach(button => { button.disabled = false; });
  }
}

async function pickManualPathFromResults() {
  const results = document.getElementById("manual-path-results");
  results.replaceChildren();
  document.getElementById("pick-discovery-results").disabled = true;
  setPathRecoveryMessage("Searching public sources...");
  try {
    const name = CURRENT_PROGRESS?.subject?.name;
    const data = await api(`/api/discovery/search?q=${encodeURIComponent(name)}`);
    MANUAL_PATH_CANDIDATES = data.results || [];
    if (!MANUAL_PATH_CANDIDATES.length) {
      const message =
        data.message || "No results were found. Search again later or try another subject name.";
      MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] = message;
      setPathRecoveryMessage(message, true);
      return;
    }
    setPathRecoveryMessage("Choose a public-source result to build this subject's path.");
    MANUAL_PATH_CANDIDATES.forEach(candidate => {
      const card = document.createElement("article");
      card.className = "discovery-result";
      const title = document.createElement("strong");
      title.textContent = candidate.name;
      const summary = document.createElement("p");
      summary.textContent = candidate.summary || "No short summary was supplied.";
      const source = document.createElement("p");
      source.className = "muted small";
      source.append(
        document.createTextNode(`${candidate.source} · `),
        makeExternalLink("Source", candidate.source_url)
      );
      const useButton = document.createElement("button");
      useButton.className = "btn primary";
      useButton.type = "button";
      useButton.textContent = "Use this result";
      useButton.addEventListener("click", async () => {
        useButton.disabled = true;
        setPathRecoveryMessage("Building your learning path...");
        try {
          const path = await api("/api/discovery/subjects", {
            method: "POST",
            body: JSON.stringify({
              name: candidate.name,
              source_url: candidate.source_url,
              manual_subject_id: CURRENT_SUBJECT_ID,
            }),
          });
          delete MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID];
          results.replaceChildren();
          await loadSubjects();
          showMsg(
            "subject-message",
            `Draft learning path built with ${path.topic_count} topics. Quiz questions are prepared when you open a topic.`,
            "ok"
          );
        } catch (error) {
          const message = `This result could not be used: ${error.message}`;
          MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] = message;
          setPathRecoveryMessage(message, true);
          useButton.disabled = false;
        }
      });
      card.append(title, summary, source, useButton);
      results.appendChild(card);
    });
  } catch (error) {
    const message =
      `Public-source search failed: ${error.message}. Search again later or try another subject name.`;
    MANUAL_PATH_FAILURES[CURRENT_SUBJECT_ID] = message;
    setPathRecoveryMessage(message, true);
  } finally {
    document.getElementById("pick-discovery-results").disabled = false;
  }
}

async function refreshAll() {
  try {
    const [progress, history, improvement] = await Promise.all([
      api(`/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/progress`),
      api(`/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/history?limit=15`),
      api(`/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/improvement`),
    ]);
    CURRENT_PROGRESS = progress;
    const draftBadge = document.getElementById("subject-status-badge");
    draftBadge.hidden = progress.subject.status !== "draft";
    if (!draftBadge.hidden) {
      draftBadge.textContent = "Draft / unreviewed";
    }
    showMsg(
      "subject-message",
      progress.subject.reference_book
        ? `Reference: ${progress.subject.reference_book.title}`
        : "",
      ""
    );
    const needsDiagnostic = !progress.diagnostic_completed;
    const hasTopics = progress.topics.length > 0;
    const recs = needsDiagnostic || !hasTopics
      ? { recommendations: [], message: null }
      : await api(
        `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/recommendations?top_k=5`
      );
    document.getElementById("diagnostic-card").hidden = !needsDiagnostic;
    updateEmptyPathRecovery(progress);
    const allLocked = hasTopics && progress.topics.every(topic => !topic.prerequisites_met);
    const noQuestionsYet = hasTopics && progress.topics.every(
      topic => !topic.has_quiz && topic.quiz_status === "not_generated"
    );
    const limitedTopics = hasTopics && progress.topics.some(
      topic => topic.quiz_status === "limited"
    );
    const howToStart = !hasTopics
      ? ["manual", "discovered"].includes(progress.subject.source)
        ? "How to start: build this subject's learning path from the internet."
        : "This subject has no topics configured yet. Ask a teacher to add its learning path."
      : needsDiagnostic
        ? "Start learning with a short diagnostic. Limited quiz topics are skipped."
        : allLocked
          ? "How to start: review prerequisite topics to unlock the next topics."
          : noQuestionsYet
            ? "How to start: source questions are being prepared. Try refreshing in a moment."
            : limitedTopics && !recs.recommendations.length
              ? recs.message || "No source questions passed the quality checks. Try another subject from search."
            : "How to start: choose an unlocked topic from the topic map.";
    renderMastery(progress.topics);
    renderTopicMap(progress.topics);
    renderRecommendations(
      recs.recommendations,
      recs.message || howToStart,
      needsDiagnostic ? "Start learning to unlock alternatives." : undefined
    );
    renderStats(progress);
    renderHistory(history.history);
    renderImprovements(improvement);
  } catch (e) {
    if (e.message.includes("session expired") || e.message.includes("401")) clearAuth();
    else {
      showMsg("subject-message", e.message, "error");
      document.getElementById("top-rec").textContent =
        "Your dashboard could not be refreshed. Check your connection and try again.";
    }
  }
}

function renderMastery(topics) {
  const canvas = document.getElementById("mastery-chart");
  const chartStatus = document.getElementById("chart-status");
  try {
    if (MASTERY_CHART) {
      MASTERY_CHART.destroy();
      MASTERY_CHART = null;
    }
    if (typeof Chart === "undefined") {
      throw new Error("Chart.js is unavailable");
    }
    const data = {
      labels: topics.map(topic => topic.name),
      datasets: [{
        label: "Mastery",
        data: topics.map(topic => +(topic.mastery * 100).toFixed(1)),
        backgroundColor: "#3182ce",
        borderRadius: 6,
      }],
    };
    const opts = {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { min: 0, max: 100, ticks: { callback: v => v + "%" } },
      },
      plugins: { legend: { display: false } },
    };
    MASTERY_CHART = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data,
      options: opts,
    });
    canvas.hidden = false;
    chartStatus.hidden = true;
  } catch {
    canvas.hidden = true;
    chartStatus.hidden = false;
    chartStatus.textContent =
      "The mastery chart could not be displayed. Topic progress is still available in the topic map.";
    MASTERY_CHART = null;
  }
}

function explainAnswers(feedback) {
  return feedback.map((item, index) =>
    `${index + 1}. ${item.correct ? "Correct." : "Review this answer."} ${item.explanation}`
  ).join("\n");
}

function renderTopicMap(topics) {
  const map = document.getElementById("topic-map");
  map.replaceChildren();
  topics.forEach(topic => {
    const card = document.createElement("article");
    card.className = "topic-node";
    const title = document.createElement("strong");
    title.textContent = topic.name;
    const mastery = document.createElement("span");
    mastery.textContent = `${Math.round(topic.mastery * 100)}% mastery`;
    const prereqs = document.createElement("span");
    prereqs.textContent = topic.prerequisites.length
      ? `${topic.prerequisites_met ? "Unlocked" : "Locked"} · prerequisites: ${topic.prerequisites.join(", ")}`
      : "No prerequisites";
    card.append(title, mastery, prereqs);
    if (topic.quiz_status === "limited") {
      const noQuiz = document.createElement("span");
      noQuiz.textContent = topic.question_count
        ? `Limited quiz · ${topic.question_count} quality-checked question(s)`
        : "Limited quiz · no questions passed source and quality checks";
      card.appendChild(noQuiz);
    } else if (!topic.has_quiz) {
      const noQuiz = document.createElement("span");
      noQuiz.textContent = "No quiz yet · self-rating is an optional weak signal";
      card.appendChild(noQuiz);
    }
    topic.resources.forEach(resource => {
      const source = document.createElement("span");
      source.appendChild(makeExternalLink(resource.title, resource.source_url || resource.url));
      card.appendChild(source);
    });
    map.appendChild(card);
  });
}

function renderImprovements(data) {
  const list = document.getElementById("improvement-list");
  list.replaceChildren();
  if (!data.topics.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = data.message || "No topic-specific learning data yet.";
    list.appendChild(empty);
    return;
  }
  data.topics.forEach(topic => {
    const item = document.createElement("li");
    const card = document.createElement("article");
    const heading = document.createElement("strong");
    heading.textContent = topic.topic;
    const facts = document.createElement("p");
    facts.className = "muted small";
    const signals = [];
    if (topic.mastery !== null) signals.push(`${Math.round(topic.mastery * 100)}% mastery`);
    if (topic.self_rating !== null) signals.push(`self-rating ${topic.self_rating}/5 (not a quiz score)`);
    signals.push(`${topic.attempts} quiz attempts`);
    if (topic.score_trend.length) {
      signals.push(`score trend: ${topic.score_trend.join(" → ")}`);
    }
    facts.textContent = signals.join(" · ");
    const actions = document.createElement("ul");
    topic.how_to_improve.forEach(suggestion => {
      const line = document.createElement("li");
      if (typeof suggestion === "string") {
        line.textContent = suggestion;
      } else {
        line.appendChild(makeExternalLink(suggestion.resource, suggestion.source_url));
      }
      actions.appendChild(line);
    });
    card.append(heading, facts);
    if (actions.children.length) card.appendChild(actions);
    item.appendChild(card);
    list.appendChild(item);
  });
}

function renderRecommendations(
  recs,
  emptyMessage = "No recommendations available.",
  emptyAlternativesMessage = "No other topics are unlocked yet."
) {
  CURRENT_RECS = recs;
  const top = recs[0];
  const topEl = document.getElementById("top-rec");
  topEl.replaceChildren();
  const altEl = document.getElementById("alt-recs");
  altEl.replaceChildren();
  const showEmptyAlternatives = () => {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = emptyAlternativesMessage;
    altEl.appendChild(empty);
  };
  if (!top) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = emptyMessage;
    topEl.appendChild(empty);
    showEmptyAlternatives();
    return;
  }
  const topic = document.createElement("div");
  topic.className = "topic";
  topic.textContent = top.topic;
  const type = document.createElement("div");
  type.className = "type";
  type.textContent = `${top.resource_type} · difficulty ${top.difficulty}/5`;
  const explanation = document.createElement("p");
  explanation.className = "small";
  const why = top.explanation || {};
  explanation.textContent =
    `Why: predicted score ${why.predicted_score ?? "n/a"}%; difficulty fit ${why.difficulty_fit ?? "n/a"}; ` +
    `engagement ${why.engagement ?? "n/a"}; prerequisites ${why.prerequisites_met ? "met" : "not met"}.`;
  const meta = document.createElement("div");
  meta.className = "meta";
  const duration = document.createElement("div");
  const durationStrong = document.createElement("b");
  durationStrong.textContent = String(top.duration_min);
  duration.append(durationStrong, document.createTextNode(" min"));
  const utility = document.createElement("div");
  const utilityStrong = document.createElement("b");
  utilityStrong.textContent = (top.utility * 100).toFixed(0);
  utility.append(utilityStrong, document.createTextNode(" utility"));
  meta.append(duration, utility);
  const start = document.createElement("button");
  start.className = "btn primary";
  start.type = "button";
  start.dataset.action = String(top.resource_id);
  start.textContent = "Start activity";
  topEl.append(topic, type, explanation, meta, start);

  const alternatives = recs.slice(1);
  if (!alternatives.length) showEmptyAlternatives();
  alternatives.forEach(r => {
    const li = document.createElement("li");
    const label = document.createElement("span");
    const strong = document.createElement("b");
    strong.textContent = r.topic;
    label.append(
      strong,
      document.createTextNode(` · ${r.resource_type} · difficulty ${r.difficulty}/5`)
    );
    const button = document.createElement("button");
    button.className = "btn ghost small";
    button.type = "button";
    button.dataset.action = String(r.resource_id);
    button.textContent = "Start";
    li.append(label, button);
    altEl.appendChild(li);
  });
}

function renderStats(state) {
  const el = document.getElementById("stats");
  const mastered = state.topics.filter(topic => topic.mastery >= 0.6).length;
  el.replaceChildren();
  const values = [
    ["Activities completed", state.n_interactions],
    ["Total time", `${state.total_time_min.toFixed(1)} min`],
    ["Topics mastered", `${mastered} / ${state.topics.length}`],
    ["Avg engagement", `${(state.engagement_ma * 100).toFixed(0)}%`],
    ["Last score", state.last_score.toFixed(1)],
  ];
  values.forEach(([label, value]) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = label;
    const strong = document.createElement("b");
    strong.textContent = String(value);
    li.append(name, strong);
    el.appendChild(li);
  });
}

function renderHistory(rows) {
  const tbody = document.querySelector("#history-table tbody");
  tbody.replaceChildren();
  document.getElementById("history-empty").hidden = Boolean(rows.length);
  rows.forEach(r => {
    const tr = document.createElement("tr");
    const cls = r.score >= 70 ? "score-ok" : (r.score < 50 ? "score-low" : "");
    const when = r.timestamp ? new Date(r.timestamp).toLocaleString() : "—";
    const values = [when, r.topic, r.resource_type, r.difficulty, r.score,
      `${r.gain >= 0 ? "+" : ""}${(r.gain * 100).toFixed(2)}%`];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      if (index === 4) cell.className = cls;
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
}

// ==========================================================================
// Activity modal
// ==========================================================================
async function openActivity(resourceId) {
  const rec = CURRENT_RECS.find(r => r.resource_id === resourceId);
  if (!rec) return;
  CURRENT_ACTION = rec;
  IS_DIAGNOSTIC = false;
  CURRENT_QUESTIONS = [];
  CURRENT_SESSION_ID = null;
  QUIZ_COMPLETE = false;
  ACTIVITY_START = null;

  document.getElementById("modal-title").textContent = `${rec.topic} · ${rec.resource_type}`;
  document.getElementById("modal-desc").textContent =
    `Difficulty ${rec.difficulty}/5 · ~${rec.duration_min} min. Answer the questions below.`;

  const box = document.getElementById("quiz-questions");
  box.textContent = "Loading questions…";
  showMsg("modal-msg", "");
  document.getElementById("modal").hidden = false;

  try {
    const quiz = await api(
      `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/resources/${encodeURIComponent(resourceId)}/quiz`
    );
    if (CURRENT_ACTION?.resource_id !== resourceId) return;
    CURRENT_ACTION.topic_id = quiz.topic_id;
    CURRENT_SESSION_ID = quiz.session_id;
    CURRENT_QUESTIONS = quiz.questions;
    box.replaceChildren();
    if (quiz.message) showMsg("modal-msg", quiz.message, "warning");
    if (!CURRENT_QUESTIONS.length) {
      const noQuiz = document.createElement("p");
      noQuiz.textContent =
        quiz.message || "No source-backed questions passed the quality checks for this topic.";
      box.appendChild(noQuiz);
      if (quiz.resource_url) {
        box.appendChild(makeExternalLink(quiz.resource_title || "Open learning resource", quiz.resource_url));
      }
      document.getElementById("submit-activity").disabled = true;
      document.getElementById("submit-activity").textContent = "No questions available";
      return;
    }
    document.getElementById("submit-activity").disabled = false;
    document.getElementById("submit-activity").textContent = "Submit answers";
    CURRENT_QUESTIONS.forEach((item, index) => renderQuestion(box, item, index));
    ACTIVITY_START = Date.now();
  } catch (e) {
    box.textContent = "Questions could not be loaded.";
    showMsg("modal-msg", e.message, "error");
  }
}

async function openDiagnostic() {
  IS_DIAGNOSTIC = true;
  CURRENT_ACTION = { resource_id: "diagnostic" };
  CURRENT_QUESTIONS = [];
  CURRENT_SESSION_ID = null;
  QUIZ_COMPLETE = false;
  ACTIVITY_START = Date.now();
  document.getElementById("modal-title").textContent = "Subject diagnostic";
  document.getElementById("modal-desc").textContent =
    "Answer one available, source-backed question per topic. Topics with limited quizzes are skipped.";
  const box = document.getElementById("quiz-questions");
  box.textContent = "Loading diagnostic…";
  showMsg("modal-msg", "");
  document.getElementById("submit-activity").textContent = "Submit diagnostic";
  document.getElementById("submit-activity").disabled = false;
  document.getElementById("modal").hidden = false;
  try {
    const diagnostic = await api(`/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/diagnostic`);
    CURRENT_SESSION_ID = diagnostic.session_id;
    CURRENT_QUESTIONS = diagnostic.questions;
    box.replaceChildren();
    if (diagnostic.message) {
      const note = document.createElement("p");
      note.className = "muted small";
      note.textContent = diagnostic.message;
      box.appendChild(note);
    }
    CURRENT_QUESTIONS.forEach((item, index) => {
      const question = document.createElement("div");
      question.className = "question";
      if (item.quiz_available) question.dataset.questionId = item.id;
      const prompt = document.createElement("p");
      prompt.textContent = `${item.topic} · Q${index + 1}. ${item.question}`;
      question.appendChild(prompt);
      item.options.forEach((option, optionIndex) => {
        const label = document.createElement("label");
        label.className = "option";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `q${index}`;
        input.value = String(optionIndex);
        const text = document.createElement("span");
        text.textContent = option;
        label.append(input, text);
        question.appendChild(label);
      });
      const report = document.createElement("button");
      report.type = "button";
      report.className = "btn btn-small";
      report.textContent = "Report this question";
      report.addEventListener("click", async () => {
        report.disabled = true;
        try {
          await api(
            `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/questions/${encodeURIComponent(item.id)}/report`,
            { method: "POST", body: JSON.stringify({ reason: "other" }) }
          );
          report.textContent = "Question reported";
        } catch (error) {
          report.disabled = false;
          showMsg("modal-msg", error.message, "error");
        }
      });
      question.appendChild(report);
      box.appendChild(question);
    });
    document.getElementById("submit-activity").textContent = "Submit diagnostic";
    if (!CURRENT_QUESTIONS.length) {
      document.getElementById("submit-activity").disabled = false;
      if (diagnostic.session_id === null) {
        document.getElementById("submit-activity").disabled = false;
      }
    }
  } catch (e) {
    box.textContent = "Diagnostic could not be loaded.";
    showMsg("modal-msg", e.message, "error");
  }
}

function closeModal() {
  document.getElementById("modal").hidden = true;
  CURRENT_ACTION = null;
  CURRENT_QUESTIONS = [];
  CURRENT_SESSION_ID = null;
  ACTIVITY_START = null;
  IS_DIAGNOSTIC = false;
  document.getElementById("submit-activity").textContent = "Submit answers";
  document.getElementById("submit-activity").disabled = false;
}

async function submitActivity() {
  if (!CURRENT_ACTION || ACTIVITY_START === null || QUIZ_COMPLETE) return;
  const answers = [];
  for (let i = 0; i < CURRENT_QUESTIONS.length; i++) {
    const question = CURRENT_QUESTIONS[i];
    const selected = document.querySelector(`input[name="q${i}"]:checked`);
    if (!selected) {
      return showMsg("modal-msg", "Answer every quiz question before submitting.", "error");
    }
    answers.push(Number(selected.value));
  }

  const elapsedMin = Math.min(Math.max((Date.now() - ACTIVITY_START) / 60000, 0.5), 120);
  const submitButton = document.getElementById("submit-activity");
  submitButton.disabled = true;
  try {
    if (IS_DIAGNOSTIC) {
      let answerIndex = 0;
      const mappedAnswers = {};
      CURRENT_QUESTIONS.forEach(question => {
        if (question.quiz_available) {
          mappedAnswers[question.id] = answers[answerIndex++];
        }
      });
      const result = await api(`/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/diagnostic`, {
        method: "POST",
          body: JSON.stringify({
            answers: mappedAnswers,
            self_ratings: {},
            session_id: CURRENT_SESSION_ID,
          }),
        });
      CURRENT_PROGRESS = result.progress;
      document.getElementById("diagnostic-card").hidden = true;
      renderMastery(result.progress.topics);
      renderTopicMap(result.progress.topics);
      renderStats(result.progress);
      const box = document.getElementById("quiz-questions");
      box.replaceChildren();
      result.feedback.forEach(item => renderQuestionFeedback(box, item));
      showMsg(
        "modal-msg",
        result.feedback.length
          ? `Diagnostic complete (${result.score ?? 0}/100).`
            : "No diagnostic question was available. Limited topics were skipped.",
        "ok"
      );
    } else {
      if (!CURRENT_SESSION_ID) {
        throw new Error("This quiz session is no longer available. Open the activity again.");
      }
      const currentQuestion = CURRENT_QUESTIONS[0];
      const chosen = document.querySelector('input[name="q0"]:checked');
      if (!chosen) return showMsg("modal-msg", "Choose an answer before continuing.", "error");
      const r = await api(
        `/api/subjects/${encodeURIComponent(CURRENT_SUBJECT_ID)}/quiz-sessions/${encodeURIComponent(CURRENT_SESSION_ID)}/answer`,
        {
          method: "POST",
          body: JSON.stringify({
            question_id: currentQuestion.id,
            answer: Number(chosen.value),
            duration: elapsedMin,
          }),
        }
      );
      const box = document.getElementById("quiz-questions");
      box.replaceChildren();
      renderQuestionFeedback(box, r.feedback);
      if (r.reuse_message) {
        const reused = document.createElement("p");
        reused.className = "muted small";
        reused.textContent = r.reuse_message;
        box.appendChild(reused);
      }
      if (r.prerequisite_mistake) {
        const prereq = document.createElement("p");
        prereq.textContent = r.prerequisite_mistake;
        box.appendChild(prereq);
      }
      if (r.message) {
        const note = document.createElement("p");
        note.className = "muted small";
        note.textContent = r.message;
        box.appendChild(note);
      }
      if (r.next_question) {
        const nextHeading = document.createElement("h3");
        nextHeading.textContent = `Next: ${r.next_topic}`;
        box.appendChild(nextHeading);
        CURRENT_QUESTIONS = [r.next_question];
        renderQuestion(box, r.next_question, 0);
        const submit = document.getElementById("submit-activity");
        submit.textContent = "Next answer";
        submit.disabled = false;
        ACTIVITY_START = Date.now();
      } else {
        QUIZ_COMPLETE = true;
        CURRENT_QUESTIONS = [];
        CURRENT_SESSION_ID = null;
        const final = document.createElement("p");
        final.textContent = `Quiz complete: ${r.score ?? 0}/100 across ${r.question_count} question(s).`;
        box.appendChild(final);
        if (r.weak_topics.length) {
          const weak = document.createElement("p");
          weak.textContent = `Topics to improve: ${r.weak_topics.join(", ")}`;
          box.appendChild(weak);
        }
        showMsg("modal-msg", "Your score is based on graded answers only.", "ok");
        setTimeout(() => refreshAll(), 0);
      }
      return;
    }
    QUIZ_COMPLETE = true;
    setTimeout(() => {
      closeModal();
      refreshAll();
    }, 800);
  } catch (e) {
    showMsg("modal-msg", e.message, "error");
  } finally {
    submitButton.disabled = false;
  }
}

// ==========================================================================
// Bootstrap
// ==========================================================================
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById("tab-" + t.dataset.tab).classList.add("active");
  });
});

document.getElementById("login-button").addEventListener("click", doLogin);
document.getElementById("register-button").addEventListener("click", doRegister);
document.getElementById("logout-button").addEventListener("click", logout);
document.getElementById("edit-profile-button").addEventListener("click", editLearnerProfile);
document.getElementById("add-pack-subject").addEventListener("click", async () => {
  const button = document.getElementById("add-pack-subject");
  const subject = AVAILABLE_PACKS.find(
    item => item.id === document.getElementById("onboarding-pack-select").value
  );
  if (!subject) {
    showMsg("subject-step-message", "Choose a valid content pack first.", "error");
    return;
  }
  if (SELECTED_SUBJECTS.some(item => item.id === subject.id)) {
    showMsg("subject-step-message", `${subject.name} is already in your list.`, "error");
    return;
  }
  if (SELECTED_SUBJECTS.length >= 8) {
    renderSelectedSubjects();
    return;
  }
  button.disabled = true;
  showMsg("subject-step-message", `Building ${subject.name}'s learning path...`);
  try {
    const enrolled = subject.installed
      ? await api(`/api/subjects/${encodeURIComponent(subject.id)}/enroll`, {
        method: "POST",
        body: JSON.stringify({
          target_depth: document.getElementById("subject-target-depth").value,
        }),
      })
      : await api(`/api/subjects/${encodeURIComponent(subject.id)}/install`, {
        method: "POST",
        body: JSON.stringify({
          target_depth: document.getElementById("subject-target-depth").value,
        }),
      });
    const added = { ...subject, installed: true, source: "pack" };
    if (addSelectedSubject(added)) {
      ENROLLED_SUBJECTS = [...ENROLLED_SUBJECTS.filter(item => item.id !== added.id), added];
      AVAILABLE_PACKS = AVAILABLE_PACKS.map(item =>
        item.id === added.id ? { ...item, installed: true } : item
      );
      showMsg(
        "subject-step-message",
        enrolled.message ||
          `${subject.name} ${subject.installed ? "enrolled" : "installed and enrolled"} successfully.`,
        enrolled.path_status === "built" ? "ok" : "error"
      );
    } else if (enrolled.status !== "enrolled") {
      showMsg("subject-step-message", `${subject.name} could not be added.`, "error");
    }
  } catch (error) {
    showMsg("subject-step-message", `Could not add ${subject.name}: ${error.message}`, "error");
  } finally {
    button.disabled = SELECTED_SUBJECTS.length >= 8 || !AVAILABLE_PACKS.length;
  }
});
document.getElementById("include-sample-subjects").addEventListener("change", async () => {
  try {
    const include = document.getElementById("include-sample-subjects").checked;
    const packs = await api(`/api/subjects${include ? "?include_samples=true" : ""}`);
    AVAILABLE_PACKS = packs.subjects;
    const select = document.getElementById("onboarding-pack-select");
    select.replaceChildren();
    AVAILABLE_PACKS.forEach(subject => {
      const option = document.createElement("option");
      option.value = subject.id;
      option.textContent = `${subject.name} (${subject.installed ? "installed" : "not installed"})`;
      select.appendChild(option);
    });
    renderSelectedSubjects();
    const errors = packs.errors || [];
    const errorElement = document.getElementById("pack-catalog-errors");
    errorElement.hidden = errors.length === 0;
    errorElement.textContent = errors
      .map(error => `Pack folder "${error.directory}" could not be loaded: ${error.message}`)
      .join(" ");
  } catch (error) {
    showMsg("subject-step-message", `Pack list could not be loaded: ${error.message}`, "error");
  }
});
document.getElementById("learner-profile-form").addEventListener("submit", submitLearnerProfile);
document.getElementById("add-manual-subject").addEventListener("click", async () => {
  const input = document.getElementById("manual-subject-name");
  const name = input.value.trim();
  if (name.length < 2) {
    showMsg("subject-step-message", "Enter a subject name with at least 2 characters.", "error");
    return;
  }
  const button = document.getElementById("add-manual-subject");
  button.disabled = true;
  showMsg("subject-step-message", "Building your learning path...");
  try {
    const subject = await api("/api/subjects/manual", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    if (addSelectedSubject(subject)) {
      ENROLLED_SUBJECTS = [...ENROLLED_SUBJECTS.filter(item => item.id !== subject.id), subject];
      input.value = "";
      showMsg(
        "subject-step-message",
        subject.message || `${subject.name} was added.`,
        subject.path_status === "built" ? "ok" : "error"
      );
    }
  } catch (error) {
    showMsg("subject-step-message", error.message, "error");
  } finally {
    button.disabled = SELECTED_SUBJECTS.length >= 8;
  }
});
document.getElementById("search-subjects").addEventListener("click", searchDiscoveredSubjects);
document.getElementById("discovery-query").addEventListener("keydown", event => {
  if (event.key === "Enter") searchDiscoveredSubjects();
});
document.getElementById("search-books").addEventListener("click", searchReferenceBooks);
document.getElementById("book-query").addEventListener("keydown", event => {
  if (event.key === "Enter") searchReferenceBooks();
});
document.getElementById("finish-subject-step").addEventListener("click", finishSubjectStep);
document.getElementById("cancel-subject-step").addEventListener("click", async () => {
  document.getElementById("onboarding-card").hidden = true;
  document.getElementById("dashboard-content").hidden = false;
  await loadSubjects();
});
document.getElementById("manage-subjects-button").addEventListener("click", async () => {
  try {
    const profile = await api("/api/me/profile");
    await beginSubjectStep(profile.profile, false);
  } catch (error) {
    showMsg("subject-message", error.message, "error");
  }
});
document.getElementById("profile-country").addEventListener("change", () => {
  if (PROFILE_OPTIONS) updateCurriculumOptions(PROFILE_OPTIONS);
});
document.getElementById("cancel-profile-edit").addEventListener("click", () => {
  PROFILE_EDITING = false;
  document.getElementById("onboarding-card").hidden = true;
  document.getElementById("dashboard-content").hidden = false;
});
document.getElementById("delete-profile-button").addEventListener("click", deleteLearnerProfile);
document.getElementById("delete-account-button").addEventListener("click", deleteAccount);
document.getElementById("start-diagnostic").addEventListener("click", openDiagnostic);
document.getElementById("enroll-subject").addEventListener("click", async () => {
  const subjectId = document.getElementById("available-subjects").value;
  if (!subjectId) return;
  try {
    await api(`/api/subjects/${encodeURIComponent(subjectId)}/enroll`, { method: "POST" });
    await loadSubjects();
    showMsg("subject-message", "Enrolled. Complete the diagnostic to get recommendations.", "ok");
  } catch (e) {
    showMsg("subject-message", e.message, "error");
  }
});
document.getElementById("build-subject-path").addEventListener("click", runManualPathBuild);
document.getElementById("retry-subject-discovery").addEventListener("click", runManualPathBuild);
document.getElementById("pick-discovery-results").addEventListener(
  "click",
  pickManualPathFromResults
);
document.getElementById("subject-select").addEventListener("change", async event => {
  if (!event.target.value) return;
  try {
    const subjectId = event.target.value;
    await api("/api/me/subject", {
      method: "PUT",
      body: JSON.stringify({ subject_id: subjectId }),
    });
    CURRENT_SUBJECT_ID = subjectId;
    await refreshAll();
  } catch (e) {
    showMsg("subject-message", e.message, "error");
  }
});
document.getElementById("cancel-activity").addEventListener("click", closeModal);
document.getElementById("submit-activity").addEventListener("click", submitActivity);
document.addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (button) openActivity(button.dataset.action);
});

document.getElementById("login-pass").addEventListener("keydown", e => {
  if (e.key === "Enter") doLogin();
});
document.getElementById("reg-pass").addEventListener("keydown", e => {
  if (e.key === "Enter") doRegister();
});

if (TOKEN && USERNAME) {
  enterApp();
} else {
  document.getElementById("auth-view").hidden = false;
  document.getElementById("app-view").hidden = true;
}
