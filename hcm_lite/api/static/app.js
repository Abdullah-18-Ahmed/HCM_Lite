/* HCM Lite SPA — talks to the FastAPI backend at /api/v1 */
"use strict";
const API = "/api/v1";
const TOKEN_KEY = "hcm_token";
let token = sessionStorage.getItem(TOKEN_KEY) || null;
let me = null;
let cid = null;            // assistant conversation id
let chatBusy = false;
let editingUserId = null;  // Users tab: null = create mode

const ROLE_LABEL = { admin: "Admin", hr_admin: "HR", employee: "Employee", manager: "Manager" };
const roleLabel = (r) => ROLE_LABEL[r] || r;

/* ---------- DOM helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
function el(tag, attrs = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const kid of [].concat(kids)) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(kid));
  return n;
}
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 2600);
}
const titleCase = (s) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const money = (v) => "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ---------- API ---------- */
async function api(path, { method, body, form } = {}) {
  method = method || (form || body ? "POST" : "GET");
  const headers = {};
  if (token) headers["Authorization"] = "Bearer " + token;
  let payload;
  if (form) { payload = new URLSearchParams(form).toString(); headers["Content-Type"] = "application/x-www-form-urlencoded"; }
  else if (body) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(API + path, { method, headers, body: payload });
  if (res.status === 401 && me) { logout(); throw new Error("Session expired — please sign in again."); }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(data?.detail?.error?.message || data?.error?.message || data?.detail?.error?.code || data?.error?.code || ("HTTP " + res.status));
    err.code = data?.detail?.error?.code || data?.error?.code; err.field = data?.detail?.error?.field || data?.error?.field; err.status = res.status;
    throw err;
  }
  return data;
}

/* ---------- auth / boot ---------- */
async function login(email, password) {
  const data = await api("/auth/token", { form: { username: email, password } });
  token = data.access_token; sessionStorage.setItem(TOKEN_KEY, token);
  me = await api("/me");
  enterApp();
}
async function logout() {
  try { if (token) await api("/auth/logout", { method: "POST" }); } catch { /* ignore */ }
  token = null; me = null; sessionStorage.removeItem(TOKEN_KEY);
  resetAppState();
  $("#app").hidden = true; $("#setup").hidden = true; $("#login").hidden = false;
  $("#password").value = ""; $("#login-error").hidden = true;
}
function resetAppState() {
  cid = null; chatBusy = false; editingUserId = null;
  for (const id of ["#chat-log", "#dash-grid", "#dash-notes", "#leave-grid", "#users-table", "#profile-info"]) { const n = $(id); if (n) n.innerHTML = ""; }
  const sug = $("#suggested"); if (sug) { sug.innerHTML = ""; delete sug.dataset.done; }
  const ct = $("#chat-text"); if (ct) { ct.value = ""; ct.style.height = "auto"; }
}
async function boot() {
  // 1) first-run? show setup. 2) token? try resume. 3) else login.
  try {
    const st = await api("/setup/status");
    if (st.needs_admin) { showScreen("setup"); return; }
  } catch { /* fall through to login */ }
  if (token) { try { me = await api("/me"); enterApp(); return; } catch { token = null; sessionStorage.removeItem(TOKEN_KEY); } }
  showScreen("login");
}
function showScreen(which) {
  $("#setup").hidden = which !== "setup";
  $("#login").hidden = which !== "login";
  $("#app").hidden = which !== "app";
}

/* ---------- app shell ---------- */
function enterApp() {
  resetAppState();
  showScreen("app");
  $("#user-name").textContent = me.display_name;
  $("#user-role").textContent = roleLabel(me.role);
  for (const t of document.querySelectorAll(".tab[data-roles]")) {
    const roles = t.dataset.roles.split(",");
    t.hidden = !roles.includes(me.role);
  }
  showView("dashboard");
  loadDashboard();
}
function showView(name) {
  for (const t of document.querySelectorAll(".tab")) t.classList.toggle("is-active", t.dataset.view === name);
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== "view-" + name;
  if (name === "assistant") initAssistant();
  if (name === "leave") loadLeave();
  if (name === "users") loadUsers();
  if (name === "profile") loadProfile();
}

/* ---------- dashboard ---------- */
const DASH_TITLE = { employee: "My dashboard", manager: "Team dashboard", hr_admin: "Organisation dashboard", admin: "Organisation dashboard" };
async function loadDashboard() {
  const grid = $("#dash-grid"), notes = $("#dash-notes");
  $("#dash-title").textContent = DASH_TITLE[me.role] || "Dashboard";
  $("#dash-sub").textContent = `Signed in as ${me.display_name} · ${roleLabel(me.role)}${me.department ? " · " + me.department : ""}`;
  grid.innerHTML = ""; notes.innerHTML = "";
  for (let i = 0; i < 4; i++) grid.append(el("div", { class: "skeleton" }));
  let dash;
  try { dash = await api("/dashboard"); }
  catch (e) { grid.innerHTML = ""; grid.append(card("Dashboard unavailable", el("p", { class: "card-empty", text: e.message }), "col-12")); return; }
  grid.innerHTML = "";
  const sections = Object.entries(dash.sections);
  if (!sections.length) grid.append(card("Nothing to show yet", el("p", { class: "card-empty", text: "No data for your account yet." }), "col-12"));
  for (const [key, tr] of sections) grid.append(renderSection(key, tr));
  for (const w of dash.withheld || []) notes.append(el("div", { class: "note note--warn", text: `${titleCase(w)} is hidden for your role.` }));
  for (const u of dash.unavailable || []) notes.append(el("div", { class: "note", text: `${titleCase(u)} is currently unavailable.` }));
}
function card(title, bodyNode, extraClass = "", _src = null) {
  // _src (the internal data source, e.g. "hr-db:attendance") is intentionally NOT rendered —
  // it's an implementation detail and should never be shown to users.
  const head = el("div", { class: "card-head" }, [el("span", { class: "card-title", text: title })]);
  return el("div", { class: "card " + extraClass }, [head, bodyNode]);
}
function renderSection(key, tr) {
  const title = titleCase(key);
  // Half-width (col-6) by default so cards tile 2-up at equal size. Only genuinely wide
  // content (a multi-department table, a pending-leave table, payroll breakdown) spans full width.
  if (!tr.ok || !tr.data) return card(title, el("p", { class: "card-empty", text: tr.error?.message || "No data available." }), "col-6", tr.source);
  const d = tr.data;
  if (Array.isArray(d.balances)) return card(title, balancesBody(d), "col-6", tr.source);
  if (Array.isArray(d.requests)) return card(title, requestsBody(d), "col-6", tr.source);
  if (d.total_active != null) return card(title, headcountBody(d), "col-6", tr.source);
  if (d.present != null && d.records != null) {
    const wide = Array.isArray(d.by_department) && d.by_department.length > 1;
    return card(title, attendanceBody(d), wide ? "col-12" : "col-6", tr.source);
  }
  if (d.by_status || Array.isArray(d.pending)) {
    const wide = Array.isArray(d.pending) && d.pending.length > 0;
    return card(title, leaveSummaryBody(d), wide ? "col-12" : "col-6", tr.source);
  }
  if (d.gross_total != null) return card(title, payrollBody(d), "col-12", tr.source);
  if (d.full_name) return card(title, profileBody(d), "col-6", tr.source);
  return card(title, el("pre", { class: "card-empty", text: JSON.stringify(d, null, 2) }), "col-6", tr.source);
}
function kvRows(rows) { return el("div", {}, rows.map(([k, v]) => el("div", { class: "draft-row" }, [el("span", { class: "bar-label", text: k }), el("b", { text: String(v) })]))); }
function profileBody(d) { return kvRows([["Name", d.full_name], ["Employee ID", d.employee_id], ["Department", d.department], ["Job title", d.job_title], ["Manager", d.manager_name || "—"], ["Hired", d.hire_date]]); }
function headcountBody(d) {
  const wrap = el("div", {}, [el("div", { class: "big-num", text: String(d.total_active) }), el("div", { class: "big-sub", text: "active employees · as of " + d.as_of })]);
  const dept = d.by_department || {}, max = Math.max(1, ...Object.values(dept));
  wrap.append(el("div", { style: "margin-top:14px" }, Object.entries(dept).map(([name, n]) => bar(name, n, max))));
  return wrap;
}
function attendanceBody(d) {
  const tiles = [["present", d.present], ["remote", d.remote], ["absent", d.absent], ["on leave", d.on_leave], ["late", d.late]];
  const row = el("div", { class: "stat-row" }, tiles.map(([l, n]) => el("div", { class: "stat" }, [el("div", { class: "stat__num", text: String(n) }), el("div", { class: "stat__label", text: l })])));
  const rate = Number(d.attendance_rate);
  const gauge = el("div", { class: "gauge" }, [
    el("div", { class: "gauge__wrap" }, [el("div", { class: "gauge__ring", style: `--v:${rate}` }), el("div", { class: "gauge__num", text: rate + "%" })]),
    el("div", {}, [el("div", { class: "stat__num", text: `${d.working_days} days` }), el("div", { class: "stat__label", text: `attendance rate · ${d.records} records` })])]);
  const body = el("div", {}, [gauge, el("div", { style: "margin-top:16px" }, [row])]);
  const depts = d.by_department || [];
  if (depts.length > 1) {
    const head = el("tr", {}, ["Department", "Present", "Remote", "Absent", "On leave", "Late", "Rate"].map((h) => el("th", { text: h })));
    const rows = depts.map((x) => el("tr", {}, [el("td", { text: x.department }), el("td", { text: x.present }), el("td", { text: x.remote }), el("td", { text: x.absent }), el("td", { text: x.on_leave }), el("td", { text: x.late }), el("td", { text: x.attendance_rate + "%" })]));
    body.append(el("div", { class: "table-wrap", style: "margin-top:16px" }, [el("table", { class: "data" }, [el("thead", {}, [head]), el("tbody", {}, rows)])]));
  }
  return body;
}
function balancesBody(d) {
  return el("div", {}, (d.balances || []).map((b) => {
    const entitled = Number(b.entitled), remaining = Number(b.remaining);
    return el("div", { class: "bar-row" }, [el("span", { class: "bar-label", text: titleCase(b.leave_type) }), el("div", { class: "bar-track" }, [el("div", { class: "bar-fill", style: `width:${entitled ? (remaining / entitled * 100) : 0}%` })]), el("span", { class: "bar-val", text: `${remaining}/${entitled}` })]);
  }).concat([el("p", { class: "big-sub", style: "margin-top:6px", text: "remaining / entitled days" })]));
}
function requestsBody(d) {
  if (!d.requests?.length) return el("p", { class: "card-empty", text: "No leave requests." });
  const head = el("tr", {}, ["Reference", "Type", "From", "To", "Days", "Status"].map((h) => el("th", { text: h })));
  const rows = d.requests.map((r) => el("tr", {}, [el("td", { text: r.reference }), el("td", { text: titleCase(r.leave_type) }), el("td", { text: r.start_date }), el("td", { text: r.end_date }), el("td", { text: r.working_days }), el("td", {}, [el("span", { class: "badge badge--" + r.status, text: r.status })])]));
  return el("div", { class: "table-wrap" }, [el("table", { class: "data" }, [el("thead", {}, [head]), el("tbody", {}, rows)])]);
}
function leaveSummaryBody(d) {
  const body = el("div", {});
  if (d.by_status) body.append(el("div", { class: "pills" }, Object.entries(d.by_status).map(([s, n]) => el("span", { class: "pill" }, [titleCase(s) + " ", el("b", { text: String(n) })]))));
  if (Array.isArray(d.pending) && d.pending.length) {
    const head = el("tr", {}, ["Reference", "Employee", "From", "To", "Days"].map((h) => el("th", { text: h })));
    const rows = d.pending.map((p) => el("tr", {}, [el("td", { text: p.reference }), el("td", { text: p.employee }), el("td", { text: p.start_date }), el("td", { text: p.end_date }), el("td", { text: p.days })]));
    body.append(el("h4", { style: "margin:14px 0 6px;font-size:.82rem;color:var(--muted)", text: "Pending requests" }));
    body.append(el("div", { class: "table-wrap" }, [el("table", { class: "data" }, [el("thead", {}, [head]), el("tbody", {}, rows)])]));
  } else if (d.pending) { body.append(el("p", { class: "card-empty", text: "No pending requests." })); }
  return body;
}
function payrollBody(d) {
  const tiles = [["Gross", money(d.gross_total)], ["Net", money(d.net_total)], ["Headcount paid", d.headcount_paid]];
  const row = el("div", { class: "stat-row" }, tiles.map(([l, v]) => el("div", { class: "stat" }, [el("div", { class: "stat__num", text: String(v) }), el("div", { class: "stat__label", text: l })])));
  const body = el("div", {}, [el("div", { class: "big-sub", text: "Period " + (d.period || "") }), row]);
  const dept = d.by_department;
  if (dept && typeof dept === "object") {
    const entries = Array.isArray(dept) ? dept.map((x) => [x.department, x.gross_total]) : Object.entries(dept);
    const max = Math.max(1, ...entries.map(([, v]) => Number(v)));
    body.append(el("div", { style: "margin-top:14px" }, entries.map(([name, v]) => bar(name, Number(v), max, money(v)))));
  }
  return body;
}
function bar(label, value, max, valText) {
  return el("div", { class: "bar-row" }, [el("span", { class: "bar-label", text: label }), el("div", { class: "bar-track" }, [el("div", { class: "bar-fill", style: `width:${Math.round(value / max * 100)}%` })]), el("span", { class: "bar-val", text: valText != null ? valText : String(value) })]);
}

/* ---------- my leave ---------- */
async function loadLeave() {
  const grid = $("#leave-grid"); grid.innerHTML = "";
  for (let i = 0; i < 2; i++) grid.append(el("div", { class: "skeleton" }));
  try {
    const [bal, reqs] = await Promise.all([api("/leave/balance"), api("/leave/requests")]);
    grid.innerHTML = "";
    grid.append(card("Leave balances", bal.ok ? balancesBody(bal.data) : el("p", { class: "card-empty", text: bal.error?.message || "No data." }), "col-6", bal.source));
    grid.append(card("My requests", reqs.ok ? requestsBody(reqs.data) : el("p", { class: "card-empty", text: reqs.error?.message || "No data." }), "col-6", reqs.source));
  } catch (e) { grid.innerHTML = ""; grid.append(card("Leave", el("p", { class: "card-empty", text: e.message }), "col-12")); }
}

/* ---------- users (admin / HR) ---------- */
function creatableRoles() { return me.role === "admin" ? ["hr_admin", "employee"] : ["employee"]; }
function fillRoleOptions() {
  const sel = $("#uf-role"); sel.innerHTML = "";
  for (const r of creatableRoles()) sel.append(el("option", { value: r, text: roleLabel(r) }));
}
function setUserFormMode(editing) {
  editingUserId = editing ? editing.user_id : null;
  $("#userform-title").textContent = editing ? `Edit ${editing.email}` : "Add a user";
  $("#uf-submit").textContent = editing ? "Save changes" : "Create user";
  $("#userform-cancel").hidden = !editing;
  $("#uf-pass-field").hidden = !!editing;         // password/email only on create
  $("#uf-email").disabled = !!editing;
  $("#uf-error").hidden = true;
  if (editing) {
    $("#uf-name").value = editing.name; $("#uf-email").value = editing.email;
    $("#uf-dept").value = editing.department; $("#uf-title").value = editing.job_title;
    fillRoleOptionsForEdit(editing.role);
  } else {
    $("#user-form").reset(); fillRoleOptions();
  }
}
function fillRoleOptionsForEdit(current) {
  const sel = $("#uf-role"); sel.innerHTML = "";
  const roles = new Set(creatableRoles()); roles.add(current);
  for (const r of roles) sel.append(el("option", { value: r, text: roleLabel(r), selected: r === current ? "" : null }));
}
async function loadUsers() {
  $("#users-sub").textContent = me.role === "admin" ? "Create and manage HR staff and employees." : "Create and manage employees.";
  fillRoleOptions(); setUserFormMode(null);
  const wrap = $("#users-table"); wrap.innerHTML = "Loading…";
  try {
    const { users } = await api("/users");
    wrap.innerHTML = "";
    if (!users.length) { wrap.append(el("p", { class: "card-empty", text: "No users yet." })); return; }
    const head = el("tr", {}, ["Name", "Email", "Role", "Department", "Job title", "Status", ""].map((h) => el("th", { text: h })));
    const rows = users.map((u) => {
      const canManage = u.user_id !== me.user_id && u.role !== "admin" && (me.role === "admin" || u.role === "employee");
      const actions = el("td", { class: "row-actions" });
      if (canManage) {
        actions.append(el("button", { class: "btn btn--ghost btn--sm", text: "Edit", onclick: () => setUserFormMode(u) }));
        actions.append(el("button", { class: "btn btn--ghost btn--sm", text: u.active ? "Deactivate" : "Activate", onclick: () => setActive(u) }));
        actions.append(el("button", { class: "btn btn--ghost btn--sm danger", text: "Delete", onclick: () => delUser(u) }));
      } else { actions.append(el("span", { class: "card-src", text: u.user_id === me.user_id ? "you" : "—" })); }
      return el("tr", {}, [el("td", { text: u.name }), el("td", { text: u.email }), el("td", { text: roleLabel(u.role) }),
        el("td", { text: u.department }), el("td", { text: u.job_title }),
        el("td", {}, [el("span", { class: "badge badge--" + (u.active ? "approved" : "cancelled"), text: u.active ? "active" : "inactive" })]), actions]);
    });
    wrap.append(el("table", { class: "data" }, [el("thead", {}, [head]), el("tbody", {}, rows)]));
  } catch (e) { wrap.innerHTML = ""; wrap.append(el("p", { class: "card-empty", text: e.message })); }
}
async function submitUserForm(ev) {
  ev.preventDefault();
  const errEl = $("#uf-error"); errEl.hidden = true;
  const btn = $("#uf-submit"); btn.disabled = true;
  try {
    if (editingUserId) {
      await api(`/users/${editingUserId}`, { method: "PATCH", body: { name: $("#uf-name").value.trim(), role: $("#uf-role").value, department: $("#uf-dept").value.trim(), job_title: $("#uf-title").value.trim() } });
      toast("User updated");
    } else {
      await api("/users", { body: { email: $("#uf-email").value.trim(), password: $("#uf-password").value, name: $("#uf-name").value.trim(), role: $("#uf-role").value, department: $("#uf-dept").value.trim(), job_title: $("#uf-title").value.trim() } });
      toast("User created");
    }
    await loadUsers();
  } catch (e) { errEl.textContent = e.message; errEl.hidden = false; }
  finally { btn.disabled = false; }
}
async function setActive(u) {
  try { await api(`/users/${u.user_id}/active`, { body: { active: !u.active } }); toast(u.active ? "Deactivated" : "Activated"); loadUsers(); }
  catch (e) { toast(e.message); }
}
async function delUser(u) {
  if (!window.confirm(`Delete ${u.name} (${u.email})? This removes their login and records.`)) return;
  try { await api(`/users/${u.user_id}`, { method: "DELETE" }); toast("User deleted"); loadUsers(); }
  catch (e) { toast(e.message); }
}

/* ---------- profile ---------- */
function loadProfile() {
  $("#profile-info").replaceChildren(kvRows([["Name", me.display_name], ["Email", me.email || "—"], ["Role", roleLabel(me.role)], ["Department", me.department || "—"]]));
  $("#pw-old").value = ""; $("#pw-new").value = ""; $("#pw-error").hidden = true;
}
async function changePassword(ev) {
  ev.preventDefault();
  const errEl = $("#pw-error"); errEl.hidden = true;
  const btn = $("#pw-btn"); btn.disabled = true;
  try {
    await api("/me/password", { body: { old_password: $("#pw-old").value, new_password: $("#pw-new").value } });
    toast("Password updated"); $("#pw-old").value = ""; $("#pw-new").value = "";
  } catch (e) { errEl.textContent = e.message; errEl.hidden = false; }
  finally { btn.disabled = false; }
}

/* ---------- assistant ---------- */
const SUGGESTIONS = {
  _all: ["What is the annual leave policy?", "What is my remaining annual leave balance?", "Prepare a leave request for next Monday and Tuesday"],
  manager: ["Who was late today?", "Summarise team attendance this month"],
  hr_admin: ["How many employees are in the organisation?", "What was last month's payroll?"],
  admin: ["How many employees are in the organisation?", "What was last month's payroll?"],
};
function initAssistant() {
  const sug = $("#suggested");
  if (sug.dataset.done) return;
  sug.dataset.done = "1";
  for (const p of [...SUGGESTIONS._all, ...(SUGGESTIONS[me.role] || [])]) sug.append(el("button", { class: "chip", text: p, type: "button", onclick: () => { $("#chat-text").value = p; sendChat(); } }));
  addMsg("bot", `Hi ${me.display_name.split(" ")[0]}! I'm your HR assistant. Ask me about policies, your leave, or your team — I only use records your role can see.`);
}
function addMsg(kind, text) { const node = el("div", { class: "msg msg--" + kind, text }); $("#chat-log").append(node); scrollChat(); return node; }
function scrollChat() { const l = $("#chat-log"); l.scrollTop = l.scrollHeight; }
async function sendChat() {
  if (chatBusy) return;
  const input = $("#chat-text"), text = input.value.trim();
  if (!text) return;
  chatBusy = true; $("#chat-send").disabled = true;
  addMsg("user", text); input.value = ""; input.style.height = "auto";
  const typing = el("div", { class: "typing" }, [el("span"), el("span"), el("span")]);
  $("#chat-log").append(typing); scrollChat();
  try {
    if (!cid) cid = (await api("/assistant/conversations", { method: "POST" })).conversation_id;
    const r = await api(`/assistant/conversations/${cid}/messages`, { method: "POST", body: { message: text } });
    typing.remove();
    if (r.error_category) { addMsg("err", r.reply || "Something went wrong (" + r.error_category + ")."); }
    else {
      const node = addMsg("bot", r.reply || "(no reply)");
      if (r.citations?.length) {
        const cites = el("div", { class: "cites" }, [el("b", { text: "Sources" })]);
        r.citations.forEach((c, i) => cites.append(el("span", { class: "cite", text: `[${i + 1}] ${c.document_title || c.title || "source"}${c.section ? " — " + c.section : ""}` })));
        node.append(cites);
      }
      if (r.ready_draft && r.ready_draft.status === "ready_for_review") renderDraft(r.ready_draft);
    }
  } catch (e) { typing.remove(); addMsg("err", e.message); }
  finally { chatBusy = false; $("#chat-send").disabled = false; scrollChat(); }
}
function renderDraft(dft) {
  const rows = [["Type", titleCase(dft.leave_type || "—")], ["From", dft.start_date || "—"], ["To", dft.end_date || "—"], ["Working days", dft.working_days ?? "—"], ["Reason", dft.reason || "—"]];
  const cardEl = el("div", { class: "draft-card" }, [el("div", { class: "draft-tag", text: "DRAFT — NOT SUBMITTED" }), el("h4", { text: "Leave request for your review" }), ...rows.map(([k, v]) => el("div", { class: "draft-row" }, [el("span", { class: "bar-label", text: k }), el("b", { text: String(v) })]))]);
  for (const w of dft.warnings || []) cardEl.append(el("div", { class: "draft-warn", text: "⚠ " + w }));
  const confirm = el("button", { class: "btn btn--primary btn--sm", text: "Confirm & submit" });
  const cancel = el("button", { class: "btn btn--ghost btn--sm", text: "Discard" });
  confirm.addEventListener("click", async () => {
    confirm.disabled = cancel.disabled = true;
    try { const res = await api(`/assistant/conversations/${cid}/drafts/${dft.draft_id}/confirm`, { method: "POST" }); cardEl.remove(); addMsg("sys", `✓ Submitted — reference ${res.reference} (status ${res.status}). It now needs manager approval.`); }
    catch (e) { confirm.disabled = cancel.disabled = false; toast(e.message); }
  });
  cancel.addEventListener("click", async () => {
    try { await api(`/assistant/conversations/${cid}/drafts/${dft.draft_id}`, { method: "DELETE" }); } catch { /* ignore */ }
    cardEl.remove(); addMsg("sys", "Draft discarded — nothing was submitted.");
  });
  cardEl.append(el("div", { class: "draft-actions" }, [confirm, cancel]));
  $("#chat-log").append(cardEl); scrollChat();
}

/* ---------- wire up ---------- */
$("#setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#su-btn"), errEl = $("#su-error"); errEl.hidden = true; btn.disabled = true; btn.textContent = "Creating…";
  const email = $("#su-email").value.trim(), password = $("#su-password").value, name = $("#su-name").value.trim();
  try { await api("/setup/admin", { body: { email, password, name } }); await login(email, password); }
  catch (err) { errEl.textContent = err.code === "already_initialised" ? "An admin already exists — please sign in." : err.message; errEl.hidden = false; }
  finally { btn.disabled = false; btn.textContent = "Create admin & sign in"; }
});
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-btn"), errEl = $("#login-error"); errEl.hidden = true; btn.disabled = true; btn.textContent = "Signing in…";
  try { await login($("#email").value.trim(), $("#password").value); }
  catch (err) { errEl.textContent = err.status === 401 ? "Invalid email or password." : err.message; errEl.hidden = false; }
  finally { btn.disabled = false; btn.textContent = "Sign in"; }
});
$("#tabs").addEventListener("click", (e) => { const t = e.target.closest(".tab"); if (t) showView(t.dataset.view); });
$("#logout-btn").addEventListener("click", logout);
$("#user-form").addEventListener("submit", submitUserForm);
$("#userform-cancel").addEventListener("click", () => setUserFormMode(null));
$("#users-refresh").addEventListener("click", loadUsers);
$("#pw-form").addEventListener("submit", changePassword);
$("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat(); });
const chatText = $("#chat-text");
chatText.addEventListener("input", () => { chatText.style.height = "auto"; chatText.style.height = Math.min(chatText.scrollHeight, 140) + "px"; });
chatText.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });

boot();
