"use strict";

const state = {
  workplace: new Set(),
  seniority: new Set(),
  tech: new Set(),
  q: "",
  resume: null, // null | {type:'sample'} | {type:'file', file}
  ai: false,
  token: null, // server-side cache token for the current resume (avoids re-embed/re-LLM)
  offset: 0,
  pageSize: 20,
};

const AVATAR = ["#525AFF", "#4AB5B5", "#6D8BC0", "#7c86e8", "#2f9e9a", "#5a6cc0", "#4f8fd0", "#8a63c0"];
const WORKPLACE_ICON = { Remote: "🏠", Hybrid: "🔀", "On-site": "🏢", Unknown: "📍" };
const WORKPLACE_CLASS = { Remote: "b-remote", Hybrid: "b-hybrid", "On-site": "b-onsite", Unknown: "b-onsite" };

const $ = (id) => document.getElementById(id);
const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
const csv = (set) => [...set].join(",");
const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); };

// ---- theme ----
function initTheme() {
  const t = localStorage.getItem("theme") || "light";
  document.documentElement.setAttribute("data-theme", t);
  $("themeBtn").textContent = t === "dark" ? "☀️" : "🌙";
}
$("themeBtn").addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  $("themeBtn").textContent = next === "dark" ? "☀️" : "🌙";
});

// ---- pills ----
function buildPills(container, options, set) {
  container.innerHTML = "";
  options.forEach((opt) => {
    const el = document.createElement("div");
    el.className = "pill";
    el.textContent = opt;
    el.addEventListener("click", () => {
      if (set.has(opt)) { set.delete(opt); el.classList.remove("active"); }
      else { set.add(opt); el.classList.add("active"); }
      if (container.id === "techPanel") updateTechBtn();
      refresh();
    });
    container.appendChild(el);
  });
}

function updateTechBtn() {
  const n = state.tech.size;
  $("techBtn").textContent = n ? `Tech stack (${n}) ▾` : "Tech stack ▾";
}

// ---- resume ----
function setResume(r, label) {
  state.resume = r;
  state.token = null; // new resume → force fresh embed/analysis
  if (!r) { $("aiPanel").hidden = true; }
  $("resumeStatus").innerHTML = r
    ? `Ranked to <b>${esc(label)}</b><span class="clear" id="clearResume">✕ clear</span>`
    : "";
  if (r) $("clearResume").addEventListener("click", () => setResume(null));
  refresh();
}
$("uploadBtn").addEventListener("click", () => $("fileInput").click());
$("fileInput").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) setResume({ type: "file", file: f }, f.name);
});
$("sampleBtn").addEventListener("click", () => setResume({ type: "sample" }, "sample resume"));
$("aiToggle").addEventListener("change", (e) => {
  state.ai = e.target.checked;
  state.token = null; // toggling AI changes how the resume is represented → re-analyse
  if (state.resume) refresh();
});
$("loadMore").addEventListener("click", loadMore);

// ---- search ----
let searchTimer;
$("search").addEventListener("input", (e) => {
  state.q = e.target.value;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(refresh, 250);
});

// ---- tech dropdown open/close ----
$("techBtn").addEventListener("click", (e) => { e.stopPropagation(); $("techPanel").hidden = !$("techPanel").hidden; });
document.addEventListener("click", (e) => {
  if (!$("techPanel").hidden && !$("techPanel").contains(e.target) && e.target !== $("techBtn")) $("techPanel").hidden = true;
});

// ---- render ----
function scoreClass(s) { return s >= 60 ? "" : s >= 45 ? "mid" : "low"; }

function card(j) {
  const color = AVATAR[hash(j.company || "?") % AVATAR.length];
  const initial = esc((j.company || "?").trim().slice(0, 1).toUpperCase());
  const loc = j.location && j.location.length > 42 ? j.location.slice(0, 40) + "…" : j.location;

  let badges = `<span class="badge b-sen">${esc(j.seniority)}</span>`;
  badges += `<span class="badge ${WORKPLACE_CLASS[j.workplace] || "b-onsite"}">${WORKPLACE_ICON[j.workplace] || ""} ${esc(j.workplace)}</span>`;
  if (j.salary) badges += `<span class="badge b-salary">💰 ${esc(j.salary)}</span>`;
  if (j.posted) badges += `<span class="badge b-date">🕑 ${esc(j.posted)}</span>`;

  let chips = "";
  if (j.matches || j.gaps) {
    (j.matches || []).forEach((s) => (chips += `<span class="chip c-match">${esc(s)}</span>`));
    (j.gaps || []).forEach((s) => (chips += `<span class="chip c-gap">${esc(s)}</span>`));
  } else {
    (j.skills || []).forEach((s) => (chips += `<span class="chip c-tech">${esc(s)}</span>`));
  }

  let right = "";
  if (j.score != null) right += `<div class="score ${scoreClass(j.score)}">${j.score}</div><div class="score-lbl">match</div>`;
  if (j.url) right += `<a class="apply" href="${esc(j.url)}" target="_blank" rel="noopener">Apply ↗</a>`;

  const company = esc(j.company) + (loc ? ` · ${esc(loc)}` : "") + ` · ${esc(j.source)}`;
  return `<div class="card">
    <div class="avatar" style="background:${color}">${initial}</div>
    <div class="c-main">
      <div class="c-title">${esc(j.title)}</div>
      <div class="c-company">${company}</div>
      <div class="badges">${badges}</div>
      <div class="chips">${chips}</div>
    </div>
    <div class="c-right">${right}</div>
  </div>`;
}

function refresh() { state.offset = 0; fetchAndRender(false); }
function loadMore() { state.offset += state.pageSize; fetchAndRender(true); }

function renderAiPanel(data) {
  const p = $("aiPanel");
  if (data.profile) {
    const pr = data.profile;
    const chips = (pr.skills || []).map((s) => `<span class="chip c-tech">${esc(s)}</span>`).join("");
    p.innerHTML =
      `✨ <b>AI read your resume:</b> ${esc(pr.seniority || "—")} · ${pr.years != null ? esc(pr.years) + " yrs" : "—"} · ${(pr.skills || []).length} skills` +
      `<div class="chips">${chips}</div>` +
      (data.warning ? `<div class="warn">${esc(data.warning)}</div>` : "");
    p.hidden = false;
  } else if (data.warning) {
    p.innerHTML = `<div class="warn">${esc(data.warning)}</div>`;
    p.hidden = false;
  } else {
    p.hidden = true;
  }
}

async function fetchAndRender(append = false) {
  const results = $("results");
  const more = $("loadMore");
  if (!append) { results.innerHTML = `<div class="spinner"></div>`; more.hidden = true; }
  else { more.textContent = "Loading…"; more.disabled = true; }

  const params = {
    q: state.q, workplace: csv(state.workplace), seniority: csv(state.seniority),
    tech: csv(state.tech), limit: state.pageSize, offset: state.offset,
  };

  let data;
  try {
    if (state.resume) {
      const fd = new FormData();
      Object.entries(params).forEach(([k, v]) => fd.append(k, v));
      if (state.token) {
        fd.append("token", state.token);
      } else {
        if (state.resume.type === "file") fd.append("file", state.resume.file);
        else fd.append("sample", "1");
        if (state.ai) fd.append("ai", "1");
      }
      data = await (await fetch("/api/match", { method: "POST", body: fd })).json();
      if (data.token) state.token = data.token;
      renderAiPanel(data);
    } else {
      const qs = new URLSearchParams(params).toString();
      data = await (await fetch("/api/jobs?" + qs)).json();
      $("aiPanel").hidden = true;
    }
  } catch (err) {
    results.innerHTML = `<div class="empty">Could not load jobs. Is the server running?</div>`;
    more.hidden = true;
    return;
  }

  const mode = data.mode === "matched" ? "ranked by fit to your resume" : "newest first — upload a resume to rank by fit";
  const shownEnd = state.offset + data.jobs.length;
  $("meta").innerHTML = `<b>${data.total}</b> jobs match · showing ${Math.min(shownEnd, data.total)} · ${mode}`;

  const html = data.jobs.length
    ? data.jobs.map(card).join("")
    : append ? "" : `<div class="empty">No jobs match these filters. Try widening them.</div>`;
  if (append) results.insertAdjacentHTML("beforeend", html);
  else results.innerHTML = html;

  more.disabled = false;
  more.textContent = "Load more ↓";
  more.hidden = shownEnd >= data.total;
}

// ---- init ----
async function init() {
  initTheme();
  const f = await (await fetch("/api/facets")).json();
  $("updated").textContent = `Updated ${f.updated}`;
  buildPills($("workplaceGroup"), f.workplace, state.workplace);
  buildPills($("seniorityGroup"), f.seniority, state.seniority);
  buildPills($("techPanel"), f.tech, state.tech);
  fetchAndRender();
}
init();
