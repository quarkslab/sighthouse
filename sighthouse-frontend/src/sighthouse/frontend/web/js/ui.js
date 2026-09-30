/*
  +-----------------------------------------------------------------------+
  | DISCLAIMER: This file was generated with the assistance of a          |
  | Large Language Model (LLM) because I have poor web UI skills. The     |
  | rest of the code was written by humans. If this is a problem for you, |
  | feel free to use one of the other clients, or you are more than       |
  | welcome to propose a PR :)                                            |
  +-----------------------------------------------------------------------+
*/

// DOM helpers shared by every page

const UI = (function () {
  "use strict";

  const SPINNER =
    '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
  const ICON_EDIT =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>';
  const ICON_TRASH =
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';

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

  // Show `msg` in the alert box `id`, hide it when empty
  function setAlert(id, msg) {
    const box = $(id);
    box.textContent = msg || "";
    if (msg) show(box);
    else hide(box);
  }

  // Run an async action with `btn` disabled and showing a spinner, returns its result
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

  const modal = (id) => bootstrap.Modal.getOrCreateInstance($(id));

  // Confirmation dialog (#confirm-modal), runs `action` when accepted
  let pendingConfirm = null;
  function askConfirm(message, action, okLabel) {
    $("confirm-message").textContent = message;
    if (okLabel) $("confirm-ok").textContent = okLabel;
    pendingConfirm = action;
    modal("confirm-modal").show();
  }

  document.addEventListener("DOMContentLoaded", () => {
    const ok = $("confirm-ok");
    if (!ok) return;
    ok.addEventListener("click", () => {
      const action = pendingConfirm;
      pendingConfirm = null;
      modal("confirm-modal").hide();
      if (action) action();
    });
  });

  return {
    $,
    escapeHtml,
    show,
    hide,
    setAlert,
    withBusy,
    SPINNER,
    ICON_EDIT,
    ICON_TRASH,
    modal,
    askConfirm,
  };
})();
