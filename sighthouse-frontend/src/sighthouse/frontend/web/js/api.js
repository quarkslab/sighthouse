/*
  +-----------------------------------------------------------------------+
  | DISCLAIMER: This file was generated with the assistance of a          |
  | Large Language Model (LLM) because I have poor web UI skills. The     |
  | rest of the code was written by humans. If this is a problem for you, |
  | feel free to use one of the other clients, or you are more than       |
  | welcome to propose a PR :)                                            |
  +-----------------------------------------------------------------------+ 
*/

// SightHouseApi - a small JavaScript mirror of sighthouse-client's SightHouseClient.py.

const API_BASE = "/api/v1/";

class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

class SightHouseApi {
  constructor(baseUrl = API_BASE) {
    this.baseUrl = baseUrl;
  }

  // Request helper
  async _request(path, { method = "GET", json, form, allow = [] } = {}) {
    const options = {
      method,
      credentials: "same-origin",
      headers: {},
    };

    if (json !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(json);
    } else if (form !== undefined) {
      // Let the browser set the multipart boundary automatically
      options.body = form;
    }

    let resp;
    try {
      resp = await fetch(this.baseUrl + path, options);
    } catch (err) {
      throw new ApiError(`Network error: ${err.message}`, 0, null);
    }

    let body = null;
    const text = await resp.text();
    if (text) {
      try {
        body = JSON.parse(text);
      } catch (_) {
        body = text;
      }
    }

    if (!resp.ok && !allow.includes(resp.status)) {
      const message =
        (body && typeof body === "object" && body.error) ||
        `Request failed (${resp.status})`;
      throw new ApiError(message, resp.status, body);
    }

    return { status: resp.status, body };
  }

  // POST /login (sets the session cookie)
  async login(user, password) {
    await this._request("login", { method: "POST", json: { user, password } });
    return true;
  }

  // POST /logout
  async logout() {
    await this._request("logout", { method: "POST", allow: [401] });
    return true;
  }

  // POST /setup {user, password} (creates the first admin; only on an empty DB)
  async runSetup(user, password) {
    await this._request("setup", { method: "POST", json: { user, password } });
    return true;
  }

  // GET /me -> {id, name, role} for the current session
  async getMe() {
    const { body } = await this._request("me");
    return (body && body.user) || null;
  }

  // GET /users -> [{id, name, role}] (admin only)
  async listUsers() {
    const { body } = await this._request("users");
    return (body && body.users) || [];
  }

  // POST /users {user, password, role} (admin only)
  async createUser(user, password, role) {
    await this._request("users", {
      method: "POST",
      json: { user, password, role },
    });
    return true;
  }

  // DELETE /users {user} (admin only; user identified by name)
  async deleteUser(user) {
    await this._request("users", { method: "DELETE", json: { user } });
    return true;
  }

  // PUT /users {user, role?, password?} (admin only)
  async updateUser(user, { role, password } = {}) {
    // undefined fields are dropped by JSON.stringify
    await this._request("users", {
      method: "PUT",
      json: { user, role, password },
    });
    return true;
  }

  // GET /config -> { key: value } curated server configuration (admin only)
  async getConfig() {
    const { body } = await this._request("config");
    return (body && body.configuration) || {};
  }

  // PUT /config {partial config} -> { configuration, restart_required } (admin only)
  async updateConfig(config) {
    const { body } = await this._request("config", {
      method: "PUT",
      json: config,
    });
    return body || {};
  }

  // POST /restart {force} -> triggers a full server restart (admin only)
  async restartServer(force) {
    await this._request("restart", { 
      method: "POST", 
      json: { 
        "force": force || "false"
      }});
    return true;
  }

  // GET /ping -> true when the server is up and responding.
  async ping() {
    try {
      const { status } = await this._request("ping");
      return status === 200;
    } catch (_) {
      return false;
    }
  }

  // GET /languages -> string[]
  async getLanguages() {
    const { body } = await this._request("languages");
    return (body && body.languages) || [];
  }

  // GET /programs -> [{id, name, user, language, file}]
  async listPrograms() {
    const { body } = await this._request("programs");
    return (body && body.programs) || [];
  }

  // GET /uploads -> [{id, name, user, hash}]
  async listUploads() {
    const { body } = await this._request("uploads");
    return (body && body.files) || [];
  }

  // POST /uploads (multipart, field name "filename") -> file id
  // Mirrors SightHouseClient.upload: 409 (already uploaded)
  async uploadFile(name, file) {
    const form = new FormData();
    form.append("filename", file, name);
    const { body } = await this._request("uploads", {
      method: "POST",
      form,
      allow: [409],
    });
    const fileId = body && body.file;
    if (!Number.isInteger(fileId)) {
      throw new ApiError("Server returned an invalid file id", 0, body);
    }
    return fileId;
  }

  // POST /programs {programs:[{name, file, language}]} -> program
  async createProgram(name, fileId, language) {
    const { body } = await this._request("programs", {
      method: "POST",
      json: { programs: [{ name, file: fileId, language }] },
    });
    const programs = (body && body.programs) || [];
    if (programs.length !== 1 || !Number.isInteger(programs[0].id)) {
      throw new ApiError("Server returned an invalid program", 0, body);
    }
    return programs[0];
  }

  // DELETE /programs/{id}
  async deleteProgram(id) {
    await this._request(`programs/${id}`, { method: "DELETE", json: {} });
    return true;
  }

  // POST /programs/{id}/analyze {bob_ross, auto_analysis}
  async startAnalysis(id, { bobRoss = false, autoAnalysis = false } = {}) {
    await this._request(`programs/${id}/analyze`, {
      method: "POST",
      json: { bob_ross: bobRoss, auto_analysis: autoAnalysis },
    });
    return true;
  }

  // POST /programs/{id}/autoload
  async startAutoload(id) {
    await this._request(`programs/${id}/autoload`, { method: "POST" });
    return true;
  }

  // PUT /programs/{id}/language {language}
  async setLanguage(id, language) {
    await this._request(`programs/${id}/language`, {
      method: "PUT",
      json: { language },
    });
    return true;
  }

  // GET /programs/{id}/analyze -> {program, user, info:{status, progress}} | null.
  // 404 means "no analysis for this program yet"
  async getAnalysis(id) {
    const { status, body } = await this._request(`programs/${id}/analyze`, {
      allow: [404],
    });
    if (status === 404) {
      return null;
    }
    return (body && body.analysis) || null;
  }

  // GET /programs/{id}?recursive=true -> program/sections/functions/matches
  async getProgram(id, recursive = true) {
    const query = recursive ? "?recursive=true" : "";
    const { body } = await this._request(`programs/${id}${query}`);
    return body;
  }

  // GET /programs/{id}/sections -> [{id, name, file_offset, start, end, perms, kind}]
  async listSections(id) {
    const { body } = await this._request(`programs/${id}/sections`);
    return (body && body.sections) || [];
  }

  // POST /programs/{id}/sections {sections:[{name, file_offset, start, end, perms, kind}]}
  async createSections(id, sections) {
    const { body } = await this._request(`programs/${id}/sections`, {
      method: "POST",
      json: { sections },
    });
    return (body && body.sections) || [];
  }

  // DELETE /programs/{id}/sections/
  async deleteAllSections(id) {
    await this._request(`programs/${id}/sections/`, { method: "DELETE" });
    return true;
  }

  // Convenience: are we authenticated? A protected endpoint returns 401 when not.
  async checkAuth() {
    try {
      await this.listPrograms();
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        return false;
      }
      throw err;
    }
  }
}

window.SightHouseApi = SightHouseApi;
window.ApiError = ApiError;
