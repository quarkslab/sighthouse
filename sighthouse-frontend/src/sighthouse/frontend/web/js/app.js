/*
  +-----------------------------------------------------------------------+
  | DISCLAIMER: This file was generated with the assistance of a          |
  | Large Language Model (LLM) because I have poor web UI skills. The     |
  | rest of the code was written by humans. If this is a problem for you, |
  | feel free to use one of the other clients, or you are more than       |
  | welcome to propose a PR :)                                            |
  +-----------------------------------------------------------------------+ 
*/

// SightHouse frontend UI controller

(function () {
  "use strict";

  const api = new SightHouseApi();
  const POLL_INTERVAL = 3500; // ms between analysis-status polls

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const state = {
    programs: [],
    fileHashById: new Map(),  // file id -> sha256 hash (from GET /uploads)
    languages: null,          // cached GET /languages result
    selectedId: null,
    pollToken: 0,             // bumped to cancel in-flight polling loops
    rows: [],                 // current program's flattened match rows
    sort: { key: "score", dir: "desc" },
  };

  const COLUMNS = [
    { key: "functionName", label: "Function", type: "str", width: "22%" },
    { key: "address", label: "Address", type: "num", width: "11%" },
    { key: "matchName", label: "Match", type: "str", width: "22%" },
    { key: "sdk", label: "SDK", type: null, width: "12%" },
    { key: "origin", label: "Origin", type: null, width: "17%" },
    { key: "score", label: "Score", type: "num", width: "8%" },
    { key: "nbMatch", label: "# Matches", type: "num", width: "8%" },
  ];

  // ---------------------------------------------------------------------------
  // Small DOM helpers
  // ---------------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    // @TODO: Probably not secure enough
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Visibility via Bootstrap's `d-none` utility
  function show(el) {
    el.classList.remove("d-none");
  }
  function hide(el) {
    el.classList.add("d-none");
  }

  const SPINNER = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';

  // Run an async action with `btn` in a busy state (disabled + spinner label),
  // always restoring it afterwards. Returns the action's result
  async function withBusy(btn, label, action) {
    btn.disabled = true;
    const original = btn.innerHTML;
    btn.innerHTML = `${SPINNER} ${label}`;
    try {
      return await action();
    } finally {
      btn.disabled = false;
      btn.innerHTML = original;
    }
  }

  // If `err` is an expired session (401), show the login gate and return true so
  // callers can bail. Centralizes the one auth-handling rule for every catch
  function handleAuthError(err) {
    if (err instanceof ApiError && err.status === 401) {
      showLogin();
      return true;
    }
    return false;
  }

  // ---------------------------------------------------------------------------
  // View switching
  // ---------------------------------------------------------------------------
  function showLogin() {
    hide($("app-view"));
    show($("login-view"));
    $("login-password").value = "";
    setTimeout(() => $("login-user").focus(), 0);
  }

  async function enterApp() {
    hide($("login-view"));
    show($("app-view"));
    renderPlaceholder();
    await refreshSidebar();
  }

  // ---------------------------------------------------------------------------
  // Login
  // ---------------------------------------------------------------------------
  function setLoginError(msg) {
    const box = $("login-error");
    if (!msg) {
      hide(box);
      return;
    }
    box.textContent = msg;
    show(box);
  }

  async function onLoginSubmit(event) {
    event.preventDefault();
    setLoginError("");
    const user = $("login-user").value.trim();
    const password = $("login-password").value;
    if (!user || !password) {
      setLoginError("Please enter a username and password.");
      return;
    }
    try {
      await withBusy($("login-submit"), "Signing in...", async () => {
        await api.login(user, password);
        await enterApp();
      });
    } catch (err) {
      // 401 here means bad credentials
      if (err instanceof ApiError && err.status === 401) {
        setLoginError("Invalid username or password.");
      } else {
        setLoginError(err.message || "Login failed.");
      }
    }
  }

  async function onLogout() {
    state.pollToken++; // cancel any polling
    state.selectedId = null;
    try {
      await api.logout();
    } catch (_) {
      /* ignore */
    }
    showLogin();
  }

  // ---------------------------------------------------------------------------
  // Sidebar
  // ---------------------------------------------------------------------------
  async function refreshSidebar() {
    try {
      const [programs, uploads] = await Promise.all([
        api.listPrograms(),
        api.listUploads(),
      ]);
      state.programs = programs;
      state.fileHashById = new Map(uploads.map((f) => [f.id, f.hash]));
      renderSidebar();
    } catch (err) {
      if (handleAuthError(err)) return;
      renderMainError(err.message || "Failed to load programs.");
    }
  }

  function renderSidebar() {
    $("program-count").textContent = String(state.programs.length);
    const list = $("program-list");
    if (state.programs.length === 0) {
      list.innerHTML =
        '<div class="p-3 text-body-secondary">No programs yet. Upload one to get started.</div>';
      return;
    }
    list.innerHTML = state.programs
      .map((p) => {
        const hash = state.fileHashById.get(p.file) || "";
        const shortHash = hash ? hash.slice(0, 10) : "-";
        const active = p.id === state.selectedId ? " active" : "";
        return (
          `<div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center program-item${active}" role="button" tabindex="0" data-id="${p.id}">` +
          `<span class="d-flex flex-column overflow-hidden">` +
          `<span class="text-truncate">${escapeHtml(p.name)}</span>` +
          `<span class="font-monospace text-body-secondary">${escapeHtml(shortHash)}</span>` +
          `</span>` +
          `<button class="btn btn-sm btn-link text-reset p-0 ms-2 program-delete" type="button" data-delete-id="${p.id}" title="Delete program" aria-label="Delete ${escapeHtml(
            p.name
          )}">` +
          `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>` +
          `</button>` +
          `</div>`
        );
      })
      .join("");
  }

  async function onDeleteProgram(id) {
    const program = state.programs.find((p) => p.id === id);
    const name = program ? program.name : "this program";
    if (!window.confirm(`Delete “${name}”? This cannot be undone.`)) return;

    try {
      await api.deleteProgram(id);
    } catch (err) {
      if (handleAuthError(err)) return;
      flashError(err.message || "Failed to delete program.");
      return;
    }

    // If the deleted program was open, stop polling and clear the main view
    if (state.selectedId === id) {
      state.pollToken++;
      state.selectedId = null;
      renderPlaceholder();
    }
    await refreshSidebar();
  }

  function highlightSidebar(id) {
    document.querySelectorAll("#program-list .program-item").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.id) === id);
    });
  }

  // ---------------------------------------------------------------------------
  // Result rendering
  // ---------------------------------------------------------------------------

  // Parse the `executable` metadata (a JSON string on each match) the same way
  // the Python client does (SightHouseClient.py Match), guarding against bad data
  function parseExecutable(raw) {
    const out = { sdk: [], origin: "" };
    if (!raw) return out;
    let data;
    try {
      data = typeof raw === "string" ? JSON.parse(raw) : raw;
    } catch (_) {
      return out;
    }
    if (!data || typeof data !== "object") return out;
    out.origin = data.origin || "";
    let md = data.metadata;
    if (!Array.isArray(md) || md.length === 0) {
      md = [[data.name, data.version]];
    }
    out.sdk = md
      .map((pair) => {
        if (Array.isArray(pair)) {
          const [n, v] = pair;
          return v ? `${n}@${v}` : n ? String(n) : "";
        }
        return String(pair);
      })
      .filter(Boolean);
    return out;
  }

  // Flatten sections -> functions -> matches into table rows
  function buildRows(program) {
    const rows = [];
    for (const section of program.sections || []) {
      const start = Number(section.start) || 0;
      for (const fn of section.functions || []) {
        const address = start + (Number(fn.offset) || 0);
        for (const match of fn.matches || []) {
          const meta = match.metadata || {};
          const exe = parseExecutable(meta.executable);
          rows.push({
            functionName: fn.name || "",
            address: address,
            matchName: match.name || "",
            sdk: exe.sdk,
            origin: exe.origin,
            score: typeof meta.score === "number" ? meta.score : null,
            nbMatch: typeof meta.nb_match === "number" ? meta.nb_match : null,
          });
        }
      }
    }
    return rows;
  }

  function sortRows(rows) {
    const { key, dir } = state.sort;
    const col = COLUMNS.find((c) => c.key === key);
    if (!col || col.type === null) return rows;
    const sign = dir === "asc" ? 1 : -1;
    return rows.slice().sort((a, b) => {
      let av = a[key];
      let bv = b[key];
      if (col.type === "num") {
        av = av == null ? -Infinity : av;
        bv = bv == null ? -Infinity : bv;
        return (av - bv) * sign;
      }
      av = String(av || "").toLowerCase();
      bv = String(bv || "").toLowerCase();
      if (av < bv) return -1 * sign;
      if (av > bv) return 1 * sign;
      return 0;
    });
  }

  function statusBannerMarkup(analysis) {
    if (!analysis || !analysis.info) return "";
    const { status, progress } = analysis.info;
    if (status === "finished") {
      // The worker reports failures as a "finished" status whose progress is the
      // error text (success messages contain "successfully")
      if (progress && !/successfully/i.test(progress)) {
        return `<div class="alert alert-danger" role="alert">Analysis failed: ${escapeHtml(
          progress
        )}</div>`;
      }
      return "";
    }
    return (
      `<div id="status-banner" class="alert alert-info d-flex align-items-center gap-2" role="status">` +
      `${SPINNER}` +
      `<span>Working...</span>` +
      `<span id="status-progress" class="ms-auto text-body-secondary">${escapeHtml(
        progress || ""
      )}</span>` +
      `</div>`
    );
  }

  function renderProgram(program, analysis) {
    const hash = state.fileHashById.get(program.file) || "";
    const banner = statusBannerMarkup(analysis);
    const status = analysis && analysis.info && analysis.info.status;
    const analyzing = Boolean(analysis) && status !== "finished";
    // "auto" is the sentinel for a not-yet-detected language
    const langSet = Boolean(program.language) && program.language !== "auto";
    const analyzeDisabled = analyzing || !langSet;
    const main = $("main");

    const langOptions = (state.languages || [])
      .map(
        (l) =>
          `<option value="${escapeHtml(l)}"${
            l === program.language ? " selected" : ""
          }>${escapeHtml(l)}</option>`
      )
      .join("");

    const languageControl =
      (langSet
        ? ""
        : `<div class="alert alert-warning py-2">Language not set - run autoload, or pick one and set it, before analyzing.</div>`) +
      `<div class="d-flex flex-wrap align-items-center gap-2 mb-3">` +
      `<label class="mb-0" for="language-select">Language</label>` +
      `<select id="language-select" class="form-select fs-6" style="width:auto">${
        langOptions || '<option value="">(languages unavailable)</option>'
      }</select>` +
      `<button id="set-language-btn" class="btn btn-outline-secondary btn-sm fs-6" type="button">Set</button>` +
      `<button id="autoload-btn" class="btn btn-outline-secondary btn-sm fs-6" type="button"${
        analyzing ? " disabled" : ""
      }>Run autoload</button>` +
      `</div>`;

    // Editable memory-layout card: language control + section editor + analyze
    const layoutCard =
      `<div class="card mb-3">` +
      `<div class="card-header d-flex align-items-center justify-content-between">` +
      `<span class="fw-semibold">Memory layout</span>` +
      `<button id="analyze-btn" class="btn btn-primary btn-sm fs-6" type="button"${
        analyzeDisabled ? " disabled" : ""
      }>${analyzing ? "Analyzing..." : "Save &amp; analyze"}</button>` +
      `</div>` +
      `<div class="card-body">` +
      languageControl +
      `<p class="text-body-secondary">Saving replaces the whole layout, then ` +
      `runs analysis. Use <code>-1</code> as the file offset for uninitialized ` +
      `(BSS) sections; values accept <code>0x</code> hex or decimal.</p>` +
      `<div id="program-sections"></div>` +
      `</div>` +
      `</div>`;

    main.innerHTML =
      // Header card
      `<div class="card mb-3">` +
      `<div class="card-body d-flex flex-wrap align-items-center justify-content-between gap-2">` +
      `<h4 class="mb-0 fs-6 fw-semibold">${escapeHtml(program.name)}</h4>` +
      `<div class="d-flex align-items-center gap-2">` +
      (langSet
        ? `<span class="badge text-bg-primary fs-6">${escapeHtml(program.language)}</span>`
        : `<span class="badge text-bg-warning fs-6">language not set</span>`) +
      `<span class="font-monospace text-body-secondary" title="${escapeHtml(hash)}">${escapeHtml(
        hash || "hash unavailable"
      )}</span>` +
      `</div>` +
      `</div>` +
      `</div>` +
      banner +
      layoutCard +
      // Matches card
      `<div class="card">` +
      `<div class="card-header d-flex align-items-center justify-content-between">` +
      `<span class="fw-semibold">Matches</span>` +
      `<span id="match-count" class="badge text-bg-secondary fs-6"></span>` +
      `</div>` +
      `<div class="overflow-auto" style="max-height: 60vh">` +
      `<table class="table table-hover table-striped align-middle mb-0 matches-table"><thead>${headMarkup()}</thead>` +
      `<tbody id="match-body"></tbody></table>` +
      `</div>` +
      `</div>`;


    // Populate the layout editor from the program's sections
    renderSectionsEditor($("program-sections"), program);
    const analyzeBtn = $("analyze-btn");
    if (analyzeBtn && !analyzeDisabled) {
      analyzeBtn.addEventListener("click", () => onAnalyzeProgram(program.id));
    }
    const setLangBtn = $("set-language-btn");
    if (setLangBtn) {
      setLangBtn.addEventListener("click", () => onSetLanguage(program.id));
    }
    const autoloadBtn = $("autoload-btn");
    if (autoloadBtn && !analyzing) {
      autoloadBtn.addEventListener("click", () => onRunAutoload(program.id));
    }

    renderRows();
  }

  // Set/override the program language, then re-render (enables Analyze).
  async function onSetLanguage(id) {
    const language = $("language-select").value;
    if (!language) {
      flashError("Pick a language first.");
      return;
    }
    try {
      await withBusy($("set-language-btn"), "Setting...", () =>
        api.setLanguage(id, language)
      );
      showProgram(id);
    } catch (err) {
      if (handleAuthError(err)) return;
      flashError(err.message || "Failed to set language.");
    }
  }

  // (Re-)run Ghidra's detect pass
  async function onRunAutoload(id) {
    try {
      await withBusy($("autoload-btn"), "Detecting...", () => api.startAutoload(id));
      showProgram(id); // enter the polling state
    } catch (err) {
      if (handleAuthError(err)) return;
      flashError(err.message || "Failed to start autoload.");
    }
  }

  // Persist the edited layout 
  async function onAnalyzeProgram(id) {
    const { sections, error } = rowsToSections(
      readSectionRows($("program-sections"))
    );
    if (error) {
      flashError(error);
      return;
    }
    try {
      await withBusy($("analyze-btn"), "Working...", () =>
        saveLayoutAndAnalyze(id, { sections })
      );
      showProgram(id); // re-render into the polling state
    } catch (err) {
      if (handleAuthError(err)) return;
      // Surfaces the 403 "being analyzed" guard and any validation error.
      flashError(err.message || "Failed to start analysis.");
    }
  }

  function headMarkup() {
    return (
      "<tr>" +
      COLUMNS.map((col) => {
        const sortable = col.type !== null;
        const isSorted = sortable && state.sort.key === col.key;
        const caret = isSorted ? (state.sort.dir === "asc" ? " ▲" : " ▼") : "";
        return (
          `<th class="${sortable ? "sortable" : ""}"${
            sortable ? ` data-key="${col.key}"` : ""
          }${col.width ? ` style="width:${col.width}"` : ""}>${escapeHtml(
            col.label
          )}${caret}</th>`
        );
      }).join("") +
      "</tr>"
    );
  }

  function renderRows() {
    const body = $("match-body");
    if (!body) return;
    const thead = body.closest("table").querySelector("thead");
    thead.innerHTML = headMarkup();
    thead.querySelectorAll("th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.key;
        if (state.sort.key === key) {
          state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
        } else {
          state.sort.key = key;
          state.sort.dir = key === "score" || key === "nbMatch" ? "desc" : "asc";
        }
        renderRows();
      });
    });

    const countBadge = $("match-count");
    if (countBadge)
      countBadge.textContent = `${state.rows.length} row${
        state.rows.length === 1 ? "" : "s"
      }`;

    if (state.rows.length === 0) {
      body.innerHTML = `<tr><td class="text-center text-body-secondary py-4" colspan="${COLUMNS.length}">No matches found for this program yet.</td></tr>`;
      return;
    }

    const rows = sortRows(state.rows);
    body.innerHTML = rows
      .map((r) => {
        const sdk = r.sdk.length
          ? r.sdk
              .map((s) => `<span class="badge text-bg-secondary fs-6 me-1">${escapeHtml(s)}</span>`)
              .join("")
          : '<span class="text-body-secondary">-</span>';
        const origin = r.origin
          ? /^https?:\/\//i.test(r.origin)
            ? `<a href="${escapeHtml(
                r.origin
              )}" target="_blank" rel="noopener noreferrer">${escapeHtml(
                r.origin
              )}</a>`
            : escapeHtml(r.origin)
          : '<span class="text-body-secondary">-</span>';
        const score =
          r.score == null
            ? '<span class="badge text-bg-secondary fs-6">-</span>'
            : `<span class="badge fs-6 text-bg-secondary">${r.score.toFixed(
                4
              )}</span>`;
        return (
          "<tr>" +
          `<td class="fw-semibold">${escapeHtml(r.functionName)}</td>` +
          `<td class="font-monospace text-body-secondary">${hex(r.address)}</td>` +
          `<td>${escapeHtml(r.matchName)}</td>` +
          `<td>${sdk}</td>` +
          `<td>${origin}</td>` +
          `<td>${score}</td>` +
          `<td class="font-monospace">${r.nbMatch == null ? "-" : r.nbMatch}</td>` +
          "</tr>"
        );
      })
      .join("");
  }

  // Centered full-area state (placeholder / loading / error).
  function centeredState(inner) {
    return (
      `<div class="d-flex flex-column align-items-center justify-content-center text-center text-body-secondary" style="min-height: 60vh">` +
      inner +
      `</div>`
    );
  }

  function renderPlaceholder() {
    $("main").innerHTML = centeredState(
      `<svg class="mb-3 text-secondary" viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>` +
        `<div class="fs-6 text-body">Select a program</div>` +
        `<div style="max-width: 360px">Pick a program from the sidebar to view its analysis matches, or upload a new one to analyze.</div>`
    );
  }

  function renderLoading() {
    $("main").innerHTML = centeredState(
      `<span class="spinner-border text-primary" role="status" aria-hidden="true"></span>` +
        `<div class="mt-2">Loading...</div>`
    );
  }

  // Full-area error state (used when a whole view fails to load).
  function renderMainError(message) {
    $("main").innerHTML = centeredState(
      `<svg class="mb-3 text-danger" viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>` +
        `<div class="fs-6 text-body">Something went wrong</div>` +
        `<div style="max-width: 360px">${escapeHtml(message)}</div>`
    );
  }

  // Transient inline error banner shown at the top of the content area (e.g. a
  // failed delete). Contextual, and auto-dismisses.
  function flashError(message) {
    const main = $("main");
    const box = document.createElement("div");
    box.className = "alert alert-danger";
    box.setAttribute("role", "alert");
    box.textContent = message;
    main.prepend(box);
    setTimeout(() => box.remove(), 6000);
  }

  // ---------------------------------------------------------------------------
  // Program view + analysis polling
  // ---------------------------------------------------------------------------
  async function showProgram(id) {
    id = Number(id);
    state.selectedId = id;
    highlightSidebar(id);
    const token = ++state.pollToken; // cancels any prior poll loop
    renderLoading();

    let program;
    try {
      program = await api.getProgram(id, true);
    } catch (err) {
      if (token !== state.pollToken) return;
      if (handleAuthError(err)) return;
      renderMainError(err.message || "Failed to load program.");
      return;
    }
    if (token !== state.pollToken) return;

    state.rows = buildRows(program);

    let analysis = null;
    try {
      analysis = await api.getAnalysis(id);
    } catch (_) {
      /* treat as no analysis */
    }
    if (token !== state.pollToken) return;

    // Languages power the program-view language <select>.
    try {
      await loadLanguages();
    } catch (_) {
      /* select falls back to a placeholder */
    }
    if (token !== state.pollToken) return;

    renderProgram(program, analysis);

    const status = analysis && analysis.info && analysis.info.status;
    if (analysis && status !== "finished") {
      pollAnalysis(id, {
        onProgress: (a) => {
          const el = $("status-progress");
          if (el && a.info.progress) el.textContent = a.info.progress;
        },
        isCancelled: () => token !== state.pollToken || state.selectedId !== id,
      }).then(() => {
        if (token !== state.pollToken || state.selectedId !== id) return;
        showProgram(id); // finished - re-fetch so matches/errors render
      });
    }
  }

  // Poll the analyze-status channel until the job finishes (or `isCancelled()`
  // returns true). `onProgress(analysis)` fires each pending tick. Resolves with
  // the final analysis (or null if cancelled)
  function pollAnalysis(id, { onProgress, isCancelled } = {}) {
    const cancelled = () => (isCancelled ? isCancelled() : false);
    return new Promise((resolve) => {
      const tick = async () => {
        if (cancelled()) return resolve(null);
        let analysis;
        try {
          analysis = await api.getAnalysis(id);
        } catch (_) {
          if (cancelled()) return resolve(null);
          setTimeout(tick, POLL_INTERVAL);
          return;
        }
        if (cancelled()) return resolve(null);
        const status = analysis && analysis.info && analysis.info.status;
        if (!analysis || status === "finished") return resolve(analysis);
        if (onProgress) onProgress(analysis);
        setTimeout(tick, POLL_INTERVAL);
      };
      tick();
    });
  }

  // ---------------------------------------------------------------------------
  // Memory-layout (sections) editor
  // ---------------------------------------------------------------------------

  // Accept "0x"-prefixed hex or plain decimal; returns NaN on anything else.
  function parseNum(value) {
    const s = String(value == null ? "" : value).trim();
    if (s === "") return NaN;
    if (/^[-+]?0x[0-9a-f]+$/i.test(s)) return parseInt(s, 16);
    if (/^[-+]?\d+$/.test(s)) return parseInt(s, 10);
    return NaN;
  }

  function hex(n) {
    if (typeof n !== "number" || !isFinite(n)) return "-";
    return "0x" + n.toString(16);
  }

  // Editor rows hold display strings; readSectionRows parses them back to numbers
  function defaultRow(fileSize) {
    return {
      name: "raw",
      start: "0x0",
      size: fileSize ? hex(fileSize) : "",
      offset: "0",
      r: true,
      w: true,
      x: true,
    };
  }

  // Map an API Section (start/end/file_offset/perms) onto an editor row
  function rowFromSection(s) {
    const start = Number(s.start) || 0;
    const end = Number(s.end) || 0;
    const perms = String(s.perms || "");
    const off = Number(s.file_offset);
    return {
      name: s.name || "",
      start: hex(start),
      size: hex(Math.max(0, end - start)),
      offset: String(Number.isFinite(off) ? off : 0),
      r: perms.charAt(0) === "R",
      w: perms.charAt(1) === "W",
      x: perms.charAt(2) === "X",
    };
  }

  // One text-input cell
  function sectionCell(field, value, placeholder) {
    return (
      `<td>` +
      `<input class="form-control form-control-sm font-monospace fs-6" ` +
      `data-f="${field}" value="${escapeHtml(value)}" placeholder="${placeholder}" ` +
      `spellcheck="false" />` +
      `</td>`
    );
  }

  // One R/W/X checkbox cell
  function permCell(field, checked) {
    return (
      `<td class="col-perm">` +
      `<input class="form-check-input" type="checkbox" data-f="${field}"${
        checked ? " checked" : ""
      } aria-label="${field.toUpperCase()}" />` +
      `</td>`
    );
  }

  function sectionRowMarkup(row) {
    return (
      `<tr data-section-row>` +
      sectionCell("name", row.name, "name") +
      sectionCell("start", row.start, "0x0") +
      sectionCell("size", row.size, "0x0") +
      sectionCell("offset", row.offset, "0") +
      permCell("r", row.r) +
      permCell("w", row.w) +
      permCell("x", row.x) +
      `<td class="col-actions">` +
      `<button type="button" class="btn btn-sm btn-link text-danger p-0" data-remove-row ` +
      `title="Remove section" aria-label="Remove section">` +
      `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>` +
      `</button>` +
      `</td>` +
      `</tr>`
    );
  }

  // Render the editor into `container` and wire add/remove-row (event delegation
  // survives innerHTML rebuilds because the listener lives on the container)
  function initSectionsEditor(container, rows) {
    container.innerHTML =
      `<div class="overflow-auto" style="max-height: 300px">` +
      `<table class="table table-sm sections-table align-middle mb-2">` +
      `<thead><tr>` +
      `<th style="width: 26%">Name</th>` +
      `<th>Start VA</th>` +
      `<th>Size</th>` +
      `<th>File offset</th>` +
      `<th class="col-perm">R</th>` +
      `<th class="col-perm">W</th>` +
      `<th class="col-perm">X</th>` +
      `<th class="col-actions"></th>` +
      `</tr></thead>` +
      `<tbody class="sections-editor__rows">${rows.map(sectionRowMarkup).join("")}</tbody>` +
      `</table>` +
      `</div>` +
      `<button type="button" class="btn btn-outline-secondary btn-sm fs-6" data-add-row>+ Add section</button>`;
    if (container.dataset.wired) return;
    container.dataset.wired = "1";
    container.addEventListener("click", (event) => {
      if (event.target.closest("[data-add-row]")) {
        container
          .querySelector(".sections-editor__rows")
          .insertAdjacentHTML("beforeend", sectionRowMarkup(defaultRow(0)));
        return;
      }
      const remove = event.target.closest("[data-remove-row]");
      if (remove) remove.closest("[data-section-row]").remove();
    });
  }

  // Fill the editor in `container` from a program's sections, or one default row
  // when it has none. Used by both the modal and the program view
  function renderSectionsEditor(container, program) {
    const rows =
      program.sections && program.sections.length
        ? program.sections.map(rowFromSection)
        : [defaultRow(0)];
    initSectionsEditor(container, rows);
  }

  function readSectionRows(container) {
    return Array.from(container.querySelectorAll("[data-section-row]")).map((el) => {
      const val = (f) => el.querySelector(`[data-f="${f}"]`).value;
      const checked = (f) => el.querySelector(`[data-f="${f}"]`).checked;
      return {
        name: val("name").trim(),
        start: parseNum(val("start")),
        size: parseNum(val("size")),
        offset: parseNum(val("offset")),
        r: checked("r"),
        w: checked("w"),
        x: checked("x"),
      };
    });
  }

  // Validate editor rows and convert them to API sections. Returns {sections} or
  // {error}. `perms` is the 3-char R/W/X string the custom loader expects, and
  // `end = start + size` (the loader skips sections whose size is <= 0).
  function rowsToSections(rows) {
    if (rows.length === 0) return { error: "Add at least one section." };
    const sections = [];
    const names = new Set();
    for (const row of rows) {
      const where = row.name ? `Section “${row.name}”` : "A section";
      if (!row.name) return { error: "Every section needs a name." };
      if (names.has(row.name))
        return { error: `Duplicate section name “${row.name}”.` };
      names.add(row.name);
      if (!Number.isInteger(row.start) || row.start < 0)
        return { error: `${where}: invalid start address.` };
      if (!Number.isInteger(row.size) || row.size <= 0)
        return { error: `${where}: size must be greater than 0.` };
      if (!Number.isInteger(row.offset))
        return { error: `${where}: invalid file offset.` };
      const perms =
        (row.r ? "R" : "-") + (row.w ? "W" : "-") + (row.x ? "X" : "-");
      sections.push({
        name: row.name,
        file_offset: row.offset,
        start: row.start,
        end: row.start + row.size,
        perms,
        kind: "",
      });
    }
    return { sections };
  }

  // ---------------------------------------------------------------------------
  // Upload modal (Bootstrap Modal)
  // ---------------------------------------------------------------------------
  let uploadModal = null;
  function getUploadModal() {
    if (!uploadModal) uploadModal = new bootstrap.Modal($("upload-modal"));
    return uploadModal;
  }

  // Per-modal-session state
  const upload = { programId: null, fileId: null, committed: false, token: 0 };

  // Upload (once) + resolve the target program: reuse the cached upload, replace
  // a same-named program when `force`, else create a new one. Returns its id.
  async function ensureProgram({ name, file, language, force }) {
    const existing = state.programs.find((p) => p.name === name);
    if (existing && !force) {
      throw new ApiError(
        `A program named “${name}” already exists - enable Force submission or pick another name.`,
        409,
        null
      );
    }
    if (!upload.fileId) upload.fileId = await api.uploadFile(name, file);
    if (existing) await api.deleteProgram(existing.id);
    return (await api.createProgram(name, upload.fileId, language)).id;
  }

  // Persist a reviewed layout onto a program and (re-)run analysis
  async function saveLayoutAndAnalyze(id, { sections, options, language } = {}) {
    if (language) await api.setLanguage(id, language);
    await api.deleteAllSections(id);
    await api.createSections(id, sections);
    await api.startAnalysis(id, options || { autoAnalysis: true });
  }

  function setUploadError(msg) {
    const box = $("upload-error");
    if (!msg) {
      hide(box);
      return;
    }
    box.textContent = msg;
    show(box);
  }

  // Fetch + cache the Ghidra language list 
  async function loadLanguages() {
    if (!state.languages) {
      state.languages = await api.getLanguages();
    }
    return state.languages;
  }

  async function ensureLanguages() {
    const select = $("upload-language");
    try {
      await loadLanguages();
    } catch (err) {
      select.innerHTML =
        '<option value="" disabled selected>Failed to load languages</option>';
      setUploadError(err.message || "Failed to load languages.");
      return;
    }
    select.innerHTML =
      '<option value="" disabled selected>Select a language...</option>' +
      (state.languages || [])
        .map((l) => `<option value="${escapeHtml(l)}">${escapeHtml(l)}</option>`)
        .join("");
  }

  // Auto-detect: upload + create an "auto" program, run Ghidra's detect pass,
  // then fill the language select + section editor in place 
  async function onAutodetect() {
    setUploadError("");
    const name = $("upload-name").value.trim();
    const file = $("upload-file").files[0];
    if (!name || !file) {
      setUploadError("Provide a name and a file first.");
      return;
    }
    const force = $("opt-force").checked;
    const token = upload.token; // detection is abandoned if the modal closes

    try {
      await withBusy($("autodetect-btn"), "Detecting...", async () => {
        if (!upload.programId) {
          upload.programId = await ensureProgram({ name, file, language: "auto", force });
          // Name + file are now committed to this program
          $("upload-name").disabled = true;
          $("upload-file").disabled = true;
        }

        await api.startAutoload(upload.programId);
        await pollAnalysis(upload.programId, {
          isCancelled: () => upload.token !== token,
        });
        if (upload.token !== token) return; // modal closed/reopened mid-detect

        const program = await api.getProgram(upload.programId, true);
        await refreshSidebar(); // the "auto" program now exists - keep state fresh

        if (program.language && program.language !== "auto") {
          $("upload-language").value = program.language;
          renderSectionsEditor($("upload-sections"), program);
        } else {
          setUploadError(
            "Couldn't detect the format - set the language and layout manually."
          );
        }
      });
    } catch (err) {
      if (handleAuthError(err)) {
        getUploadModal().hide();
        return;
      }
      setUploadError(err.message || "Auto-detect failed.");
    }
  }

  function openUploadModal() {
    $("upload-form").reset();
    setUploadError("");
    upload.programId = null;
    upload.fileId = null;
    upload.committed = false;
    upload.token += 1; // start a fresh detection session
    $("upload-name").disabled = false;
    $("upload-file").disabled = false;
    ensureLanguages();
    // Start with one section = whole file @ 0x0, RWX (size filled on file pick).
    initSectionsEditor($("upload-sections"), [defaultRow(0)]);
    $("opt-auto").checked = true; // default auto-analysis on
    getUploadModal().show();
  }

  function closeUploadModal() {
    getUploadModal().hide();
  }

  async function onUploadSubmit(event) {
    event.preventDefault();
    setUploadError("");

    const name = $("upload-name").value.trim();
    const file = $("upload-file").files[0];
    const language = $("upload-language").value;
    const force = $("opt-force").checked;
    const options = {
      bobRoss: $("opt-bobross").checked,
      autoAnalysis: $("opt-auto").checked,
    };

    if (!name || !file) {
      setUploadError("Please provide a name and a file.");
      return;
    }
    if (!language) {
      setUploadError("Please choose a language, or run Auto-detect.");
      return;
    }
    const parsed = rowsToSections(readSectionRows($("upload-sections")));
    if (parsed.error) {
      setUploadError(parsed.error);
      return;
    }

    let programId;
    try {
      programId = await withBusy($("upload-submit"), "Working...", async () => {
        // Auto-detect already created the program; otherwise create it now.
        const id =
          upload.programId || (await ensureProgram({ name, file, language, force }));
        await saveLayoutAndAnalyze(id, {
          sections: parsed.sections,
          options,
          // Persist a possible language override only when reusing an auto program.
          language: upload.programId ? language : undefined,
        });
        upload.committed = true; // keep the program when the modal closes
        return id;
      });
    } catch (err) {
      if (handleAuthError(err)) {
        closeUploadModal();
        return;
      }
      setUploadError(err.message || "Upload failed.");
      return;
    }

    closeUploadModal();
    await refreshSidebar();
    showProgram(programId);
  }

  // ---------------------------------------------------------------------------
  // Wiring
  // ---------------------------------------------------------------------------
  function bindEvents() {
    $("login-form").addEventListener("submit", onLoginSubmit);
    $("logout-btn").addEventListener("click", onLogout);

    $("program-list").addEventListener("click", (event) => {
      const del = event.target.closest(".program-delete");
      if (del) {
        event.stopPropagation();
        onDeleteProgram(Number(del.dataset.deleteId));
        return;
      }
      const item = event.target.closest(".program-item");
      if (item) showProgram(item.dataset.id);
    });

    // Keyboard selection for the program rows.
    $("program-list").addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const item = event.target.closest(".program-item");
      if (item && event.target === item) {
        event.preventDefault();
        showProgram(item.dataset.id);
      }
    });

    $("upload-open").addEventListener("click", openUploadModal);
    $("upload-form").addEventListener("submit", onUploadSubmit);
    $("autodetect-btn").addEventListener("click", onAutodetect);
    $("upload-modal").addEventListener("shown.bs.modal", () =>
      $("upload-name").focus()
    );

    // On close: invalidate any in-flight autoload poll
    $("upload-modal").addEventListener("hidden.bs.modal", () => {
      upload.token += 1;
      if (upload.programId && !upload.committed) {
        const orphan = upload.programId;
        upload.programId = null;
        api.deleteProgram(orphan).then(refreshSidebar).catch(() => {});
      }
    });

    $("upload-file").addEventListener("change", (event) => {
      upload.fileId = null; // a newly chosen file must be re-uploaded
      const file = event.target.files[0];
      if (!file) return;
      const rows = $("upload-sections").querySelectorAll("[data-section-row]");
      if (rows.length === 1) {
        const sizeInput = rows[0].querySelector('[data-f="size"]');
        const cur = sizeInput.value.trim();
        if (cur === "" || cur === "0" || cur === "0x0") {
          sizeInput.value = hex(file.size);
        }
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------------
  async function boot() {
    bindEvents();
    let authed = false;
    try {
      authed = await api.checkAuth();
    } catch (err) {
      showLogin();
      setLoginError(err.message || "Cannot reach the server.");
      return;
    }
    if (authed) {
      await enterApp();
    } else {
      showLogin();
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
