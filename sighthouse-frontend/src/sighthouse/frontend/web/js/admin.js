/*
  +-----------------------------------------------------------------------+
  | DISCLAIMER: This file was generated with the assistance of a          |
  | Large Language Model (LLM) because I have poor web UI skills. The     |
  | rest of the code was written by humans. If this is a problem for you, |
  | feel free to use one of the other clients, or you are more than       |
  | welcome to propose a PR :)                                            |
  +-----------------------------------------------------------------------+ 
*/

// admin.html controller: users and configuration management. The server
// enforces every rule (admin only, last admin guard), the UI mirrors them.

(function () {
  "use strict";

  const api = new SightHouseApi();
  const { $, escapeHtml, setAlert, ICON_EDIT, ICON_TRASH, modal, askConfirm } =
    UI;

  // ---- State ---------------------------------------------------------------
  let me = null;                // current user, to disable self-destructive actions
  let users = [];
  let config = {};              // last-saved configuration (from the server)
  let draft = {};               // working copy edited in the UI until "Save changes"
  let configEditField = null;   // CONFIG_FIELDS entry open in the edit modal
  let search = "";
  let editTarget = null;        // user name being edited

  const setError = (msg) => setAlert("admin-error", msg);

  // 401 (session died) or 403 (not an admin) both return to the app
  function handleAuthError(err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      window.location.assign("/");
      return true;
    }
    return false;
  }

  // ---- Data ----------------------------------------------------------------
  async function refresh() {
    try {
      const [u, c, who] = await Promise.all([
        api.listUsers(),
        api.getConfig(),
        api.getMe(),
      ]);
      users = u;
      config = c;
      draft = structuredClone(c);
      me = who;
      renderUsers();
      renderConfig();
    } catch (err) {
      if (handleAuthError(err)) return;
      setError((err && err.message) || "Failed to load admin data.");
    }
  }

  async function refreshUsers() {
    users = await api.listUsers();
    renderUsers();
  }

  function renderUsers() {
    $("admin-user-count").textContent = String(users.length);
    const q = search.trim().toLowerCase();
    const list = q
      ? users.filter(
          (u) =>
            u.name.toLowerCase().includes(q) ||
            u.role.toLowerCase().includes(q),
        )
      : users;
    const tbody = $("admin-users");

    if (!list.length) {
      tbody.innerHTML =
        '<tr><td colspan="3" class="text-body-secondary py-3">No users match.</td></tr>';
      return;
    }
    tbody.innerHTML = list
      .map((u) => {
        const self = me && u.id === me.id;
        const name = escapeHtml(u.name);
        const edit = `<button class="btn btn-sm btn-outline-secondary" data-action="edit" data-name="${name}" title="Edit user" aria-label="Edit ${name}">${ICON_EDIT}</button>`;
        const del = `<button class="btn btn-sm btn-outline-danger" data-action="delete" data-name="${name}"${
          self ? " disabled" : ""
        } title="Delete user" aria-label="Delete ${name}">${ICON_TRASH}</button>`;
        return (
          `<tr>` +
          `<td>${name}${self ? ' <span class="text-body-secondary">(you)</span>' : ""}</td>` +
          `<td><span class="badge text-bg-${u.role === "admin" ? "primary" : "secondary"}">${escapeHtml(u.role)}</span></td>` +
          `<td class="col-actions"><div class="d-inline-flex gap-1 justify-content-end">${edit}${del}</div></td>` +
          `</tr>`
        );
      })
      .join("");
  }

  // Editable fields (dot-paths into config), "restart" ones apply after a restart
  const CONFIG_FIELDS = [
    { key: "repo_url", label: "Repository URL", type: "text", restart: true },
    {
      key: "ghidra_dir",
      label: "Ghidra directory",
      type: "text",
      restart: true,
    },
    { key: "host", label: "Host", type: "text", restart: true },
    { key: "port", label: "Port", type: "int", restart: true },
    { key: "worker_url", label: "Worker URL", type: "text", restart: true },
    { key: "worker_count", label: "Worker count", type: "int", restart: true },
    { key: "bsim_config.urls", label: "BSIM URLs", type: "list" },
    {
      key: "bsim_config.min_instructions",
      label: "BSIM min instructions",
      type: "int",
    },
    {
      key: "bsim_config.max_instructions",
      label: "BSIM max instructions",
      type: "int",
    },
    {
      key: "bsim_config.number_of_matches",
      label: "BSIM number of matches",
      type: "int",
    },
    { key: "bsim_config.similarity", label: "BSIM similarity", type: "float" },
    { key: "bsim_config.confidence", label: "BSIM confidence", type: "float" },
    { key: "fidb_config.urls", label: "FIDB URLs", type: "list" },
    {
      key: "fidb_config.min_instructions",
      label: "FIDB min instructions",
      type: "int",
    },
    {
      key: "fidb_config.max_instructions",
      label: "FIDB max instructions",
      type: "int",
    },
  ];

  function getPath(obj, path) {
    return path
      .split(".")
      .reduce((o, k) => (o == null ? undefined : o[k]), obj);
  }
  function setPath(obj, path, value) {
    const keys = path.split(".");
    const last = keys.pop();
    const target = keys.reduce((o, k) => (o[k] = o[k] || {}), obj);
    target[last] = value;
  }
  function formatValue(field, v) {
    if (field && field.type === "list") return (v || []).join(", ");
    return v == null ? "" : String(v);
  }

  const setConfigError = (msg) => setAlert("config-error", msg);

  function renderConfig() {
    const tbody = $("admin-config");
    // Read-only rows first
    const readOnly = (k, v) =>
      `<tr><td class="font-monospace text-body-secondary">${escapeHtml(k)}</td>` +
      `<td class="font-monospace">${escapeHtml(v == null ? "" : String(v))}</td>` +
      `<td class="col-actions"></td></tr>`;

    const rows = [readOnly("database_uri", draft.database_uri)];
    if (draft.version != null) rows.push(readOnly("version", draft.version));

    CONFIG_FIELDS.forEach((f) => {
      const changed =
        JSON.stringify(getPath(draft, f.key)) !==
        JSON.stringify(getPath(config, f.key));
      const badge = f.restart
        ? ' <span class="badge text-bg-secondary">restart</span>'
        : "";
      rows.push(
        `<tr class="${changed ? "table-warning" : ""}">` +
          `<td class="font-monospace text-body-secondary">${escapeHtml(f.label)}${badge}</td>` +
          `<td class="font-monospace">${escapeHtml(formatValue(f, getPath(draft, f.key)))}</td>` +
          `<td class="col-actions"><button type="button" class="btn btn-sm btn-outline-secondary" data-config-edit="${escapeHtml(f.key)}" aria-label="Edit ${escapeHtml(f.label)}">${ICON_EDIT}</button></td>` +
          `</tr>`,
      );
    });

    tbody.innerHTML = rows.join("");
    $("config-save").disabled =
      JSON.stringify(draft) === JSON.stringify(config);
  }

  // ---- Config edit modal (stages a single field into `draft`) --------------
  const HINTS = {
    list: "Comma-separated list of URLs.",
    int: "Whole number.",
    float: "Number.",
  };

  function openConfigEdit(key) {
    const field = CONFIG_FIELDS.find((f) => f.key === key);
    if (!field) return;
    configEditField = field;
    setAlert("config-edit-error", "");
    $("config-edit-title").textContent = "Edit " + field.label;
    $("config-edit-label").textContent = field.label;
    $("config-edit-value").value = formatValue(field, getPath(draft, key));
    $("config-edit-hint").textContent = HINTS[field.type] || "";
    modal("config-edit-modal").show();
    setTimeout(() => $("config-edit-value").focus(), 200);
  }

  function onConfigEditSubmit(event) {
    event.preventDefault();
    setAlert("config-edit-error", "");
    const field = configEditField;
    if (!field) return;
    const raw = $("config-edit-value").value;
    let value;
    if (field.type === "list") {
      value = raw
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else if (field.type === "int") {
      if (raw.trim() === "" || !Number.isInteger(Number(raw))) {
        setAlert("config-edit-error", "Please enter a whole number.");
        return;
      }
      value = parseInt(raw, 10);
    } else if (field.type === "float") {
      if (raw.trim() === "" || Number.isNaN(Number(raw))) {
        setAlert("config-edit-error", "Please enter a number.");
        return;
      }
      value = Number(raw);
    } else {
      value = raw.trim();
    }
    setPath(draft, field.key, value);
    modal("config-edit-modal").hide();
    renderConfig();
  }

  async function onConfigSave() {
    setConfigError("");
    $("config-saved").classList.add("d-none");
    $("config-restart").classList.add("d-none");
    try {
      const payload = structuredClone(draft);
      delete payload.version; // informational only
      const result = await api.updateConfig(payload);
      config = result.configuration || {};
      draft = structuredClone(config);
      renderConfig();
      $("config-saved").classList.remove("d-none");
      const restart = result.restart_required || [];
      if (restart.length) {
        $("config-restart").textContent =
          "Restart the server for these changes to take effect: " +
          restart.join(", ");
        $("config-restart").classList.remove("d-none");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      setConfigError((err && err.message) || "Failed to save configuration.");
    }
  }

  // ---- Row actions ---------------------------------------------------------
  function onUsersClick(event) {
    const btn = event.target.closest("[data-action]");
    if (!btn || btn.disabled) return;
    const name = btn.dataset.name;
    if (btn.dataset.action === "edit") {
      openEdit(name);
    } else if (btn.dataset.action === "delete") {
      askConfirm(
        `Delete user “${name}”? This cannot be undone.`,
        async () => {
          setError("");
          try {
            await api.deleteUser(name);
            await refreshUsers();
          } catch (err) {
            if (handleAuthError(err)) return;
            setError((err && err.message) || "Failed to delete user.");
          }
        },
        "Delete",
      );
    }
  }

  // ---- Add user modal ------------------------------------------------------
  function openAdd() {
    setAlert("add-user-error", "");
    $("admin-new-user").value = "";
    $("admin-new-password").value = "";
    $("admin-new-role").value = "user";
    modal("add-user-modal").show();
    setTimeout(() => $("admin-new-user").focus(), 200);
  }

  async function onAddSubmit(event) {
    event.preventDefault();
    setAlert("add-user-error", "");
    const user = $("admin-new-user").value.trim();
    const password = $("admin-new-password").value;
    const role = $("admin-new-role").value;
    if (!user || !password) {
      setAlert("add-user-error", "Username and password are required.");
      return;
    }
    try {
      await api.createUser(user, password, role);
      modal("add-user-modal").hide();
      await refreshUsers();
    } catch (err) {
      if (handleAuthError(err)) return;
      setAlert(
        "add-user-error",
        (err && err.message) || "Failed to create user.",
      );
    }
  }

  // ---- Edit modal (role + optional password) -------------------------------
  function openEdit(name) {
    const user = users.find((u) => u.name === name);
    if (!user) return;
    editTarget = name;
    setAlert("edit-error", "");
    $("edit-target").textContent = name;
    $("admin-edit-role").value = user.role;
    $("admin-edit-password").value = "";
    modal("edit-modal").show();
  }

  async function onEditSubmit(event) {
    event.preventDefault();
    setAlert("edit-error", "");
    const patch = { role: $("admin-edit-role").value };
    const password = $("admin-edit-password").value;
    if (password) patch.password = password;
    try {
      await api.updateUser(editTarget, patch);
      modal("edit-modal").hide();
      await refreshUsers();
    } catch (err) {
      if (handleAuthError(err)) return;
      setAlert("edit-error", (err && err.message) || "Failed to update user.");
    }
  }

  // ---- Server tab ----------------------------------------------------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Wait for the restart then go to the login page (sessions are lost). On a port
  // change, keep the hostname since config.host is a bind address.
  async function waitForRestartThenRedirect() {
    await sleep(1500); // let the server begin shutting down before polling

    const newPort = config && config.port != null ? String(config.port) : null;
    const curPort =
      window.location.port ||
      (window.location.protocol === "https:" ? "443" : "80");
    const portChanged = newPort && newPort !== curPort;

    if (portChanged) {
      // Can't poll a cross-origin port (no CORS); wait a bit longer, then go.
      await sleep(3000);
      window.location.assign(
        `${window.location.protocol}//${window.location.hostname}:${newPort}/`,
      );
      return;
    }

    for (let i = 0; i < 60; i++) {
      if (await api.ping()) break;
      await sleep(1000);
    }
    window.location.assign("/");
  }

  function onRestart(force) {
    askConfirm(
      "Restart the server now? Active sessions and any in-progress analyses will be interrupted.",
      async () => {
        const box = $("server-message");
        try {
          await api.restartServer(force);
          box.className = "alert alert-info";
          box.textContent =
            "Server is restarting — you will be redirected to the login page once it is back.";
          waitForRestartThenRedirect();
        } catch (err) {
          if (handleAuthError(err)) return;
          box.className = "alert alert-danger";
          box.textContent =
            (err && err.message) || "Failed to restart the server.";
        }
      },
      "Restart",
    );
  }

  async function onLogout() {
    try {
      await api.logout();
    } catch (_) {
      /* ignore */
    }
    window.location.assign("/");
  }

  // ---- Wiring --------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-section]").forEach((b) => {
      b.addEventListener("click", () => {
        document.querySelectorAll("[data-section]").forEach((x) => {
          x.classList.toggle("active", x.dataset.section === b.dataset.section);
        });
        document.querySelectorAll("[data-panel]").forEach((p) => {
          p.classList.toggle("d-none", p.dataset.panel !== b.dataset.section);
        });
      });
    });

    $("admin-search").addEventListener("input", (e) => {
      search = e.target.value;
      renderUsers();
    });

    $("admin-users").addEventListener("click", onUsersClick);
    $("admin-add-open").addEventListener("click", openAdd);
    $("admin-add-form").addEventListener("submit", onAddSubmit);
    $("admin-edit-form").addEventListener("submit", onEditSubmit);

    $("admin-config").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-config-edit]");
      if (btn) openConfigEdit(btn.getAttribute("data-config-edit"));
    });
    $("config-edit-form").addEventListener("submit", onConfigEditSubmit);
    $("config-save").addEventListener("click", onConfigSave);

    $("server-restart").addEventListener("click", (e) => { onRestart("false"); });
    $("server-restart-force").addEventListener("click", (e) => { onRestart("true"); });
    $("admin-logout").addEventListener("click", onLogout);

    refresh();
  });
})();
