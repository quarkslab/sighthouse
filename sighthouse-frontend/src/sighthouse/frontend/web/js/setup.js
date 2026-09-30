/*
  +-----------------------------------------------------------------------+
  | DISCLAIMER: This file was generated with the assistance of a          |
  | Large Language Model (LLM) because I have poor web UI skills. The     |
  | rest of the code was written by humans. If this is a problem for you, |
  | feel free to use one of the other clients, or you are more than       |
  | welcome to propose a PR :)                                            |
  +-----------------------------------------------------------------------+ 
*/

// setup.html controller: create the first administrator, then go to "/" (login)

(function () {
  "use strict";

  const api = new SightHouseApi();
  const { $, setAlert, withBusy } = UI;
  const setError = (msg) => setAlert("setup-error", msg);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    const user = $("setup-user").value.trim();
    const password = $("setup-password").value;
    const confirm = $("setup-confirm").value;

    if (!user || !password) {
      setError("Please enter a username and password.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    try {
      await withBusy($("setup-submit"), "Creating...", () =>
        api.runSetup(user, password),
      );
      window.location.assign("/");
    } catch (err) {
      setError((err && err.message) || "Setup failed.");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("setup-form").addEventListener("submit", onSubmit);
    $("setup-user").focus();
  });
})();
