/* Hybrid Clinic KPI Dashboard — static, reads precomputed docs/data/dashboard.json. */
(() => {
  "use strict";
  const COLORS = { in_person: "#0b3954", video: "#087e8b", audio: "#f2a541", fallback: "#e4572e" };
  const LABEL = { in_person: "In-person", video: "Video", audio: "Audio-only", fallback: "Video→audio fallback" };
  const AGES = ["0-17", "18-44", "45-64", "65-74", "75+"];
  const BASE = {
    margin: { l: 48, r: 18, t: 10, b: 40 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Segoe UI, Roboto, Helvetica, Arial, sans-serif", size: 12, color: "#1f2d3a" },
    legend: { orientation: "h", y: 1.12, x: 0 }, xaxis: { gridcolor: "#eef2f5" }, yaxis: { gridcolor: "#eef2f5" },
  };
  const CFG = { displayModeBar: false, responsive: true };
  const pct = (x, d = 1) => (x == null || !isFinite(x) ? "–" : (x * 100).toFixed(d) + "%");
  const num = (x) => (x == null || !isFinite(x) ? "–" : Math.round(x).toLocaleString("en-US"));
  const money = (x) => "$" + (x >= 1e6 ? (x / 1e6).toFixed(2) + "M" : Math.round(x / 1e3).toLocaleString() + "K");
  const div = (a, b) => (b ? a / b : NaN);
  const layout = (extra) => Object.assign({}, BASE, extra, {
    xaxis: Object.assign({}, BASE.xaxis, extra.xaxis || {}), yaxis: Object.assign({}, BASE.yaxis, extra.yaxis || {}),
  });

  let D, rows, util, cms, months;
  const $ = (id) => document.getElementById(id);

  function toRows(cols) {
    const keys = Object.keys(cols), n = cols[keys[0]].length, out = new Array(n);
    for (let i = 0; i < n; i++) { const r = {}; for (const k of keys) r[k] = cols[k][i]; out[i] = r; }
    return out;
  }

  function sum(arr, f) { let s = 0; for (const r of arr) s += f(r); return s; }

  function groupBy(arr, keyFn) {
    const m = new Map();
    for (const r of arr) { const k = keyFn(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); }
    return m;
  }

  // Aggregate metrics for a set of cube rows.
  function agg(rs) {
    const s = (k) => sum(rs, (r) => r[k]);
    const done = s("completed"), ns = s("no_show"), fb = s("fallback");
    const by = (m, k) => sum(rs.filter((r) => r.modality === m), (r) => r[k]);
    const videoDone = by("video", "completed"), audioDone = by("audio", "completed");
    const delivered = { in_person: by("in_person", "completed"), video: videoDone - by("video", "fallback"), audio: audioDone + by("video", "fallback") };
    return {
      scheduled: s("scheduled"), completed: done, noShowRate: div(ns, done + ns),
      virtualShare: div(delivered.video + delivered.audio, done), delivered,
      lead: div(s("lead_sum"), s("lead_n")), over14: div(s("lead_over14"), s("lead_n")),
      fallbackRate: div(by("video", "fallback"), videoDone),
      followup: div(by("video", "followup14") + by("audio", "followup14"), videoDone + audioDone),
      denialRate: div(s("denied"), done), charges: s("charges"), deniedCharges: s("denied_charges"),
      fb, fbDenied: s("fallback_denied"),
    };
  }

  function state() {
    const clinic = $("f-clinic").value;
    const mods = [...document.querySelectorAll("input[name=mod]:checked")].map((e) => e.value);
    let from = $("f-from").value, to = $("f-to").value;
    if (from > to) [from, to] = [to, from];
    return { clinic, mods, from, to };
  }

  function filt(st, { ignoreClinic = false, ignoreMod = false } = {}) {
    return rows.filter((r) => r.month >= st.from && r.month <= st.to
      && (ignoreClinic || st.clinic === "ALL" || r.clinic === st.clinic)
      && (ignoreMod || st.mods.includes(r.modality)));
  }

  function utilFor(st) {
    const us = util.filter((u) => u.month >= st.from && u.month <= st.to && (st.clinic === "ALL" || u.clinic === st.clinic));
    return div(sum(us, (u) => u.completed), sum(us, (u) => u.slots));
  }

  function renderKpis(st) {
    const a = agg(filt(st));
    const net = agg(filt(Object.assign({}, st, { clinic: "ALL" }), { ignoreMod: true }));
    const u = utilFor(st), uNet = utilFor(Object.assign({}, st, { clinic: "ALL" }));
    const cards = [
      ["Scheduled visits", num(a.scheduled), `${num(a.completed)} completed`],
      ["Virtual share", pct(a.virtualShare), "of completed visits"],
      ["No-show rate", pct(a.noShowRate), `network ${pct(net.noShowRate)}`, a.noShowRate > net.noShowRate * 1.15],
      ["Days to appointment", isFinite(a.lead) ? a.lead.toFixed(1) : "–", `${pct(a.over14, 0)} wait >14 days`, a.lead > net.lead * 1.15],
      ["Video→audio fallback", pct(a.fallbackRate), "of completed video visits", a.fallbackRate > net.fallbackRate * 1.15],
      ["Virtual→in-person ≤14d", pct(a.followup), "of completed virtual visits"],
      ["Claim denial rate", pct(a.denialRate), `${money(a.deniedCharges)} denied`, a.denialRate > net.denialRate * 1.15],
      ["Provider utilization", pct(u), `network ${pct(uNet)} · all modalities`, u < uNet * 0.93],
      ["Gross charges", money(a.charges), "completed visits"],
    ];
    $("kpis").innerHTML = cards.map(([l, v, c, w]) =>
      `<div class="kpi${w ? " warn" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="ctx">${c}</div></div>`).join("");
  }

  function renderVolume(st) {
    const byMonth = groupBy(filt(st), (r) => r.month);
    const ms = months.filter((m) => m >= st.from && m <= st.to);
    const A = ms.map((m) => agg(byMonth.get(m) || []));
    const traces = ["in_person", "video", "audio"].map((k) => ({
      type: "bar", name: LABEL[k], x: ms, y: A.map((a) => a.delivered[k]), marker: { color: COLORS[k] },
      hovertemplate: `${LABEL[k]}: %{y:,}<extra></extra>`,
    }));
    traces.push({ type: "scatter", mode: "lines+markers", name: "Virtual share", x: ms, y: A.map((a) => a.virtualShare),
      yaxis: "y2", line: { color: COLORS.fallback, width: 2.5 }, hovertemplate: "Virtual share: %{y:.1%}<extra></extra>" });
    Plotly.react("c-volume", traces, layout({ barmode: "stack", hovermode: "x unified",
      yaxis: { title: { text: "Completed visits" } },
      yaxis2: { overlaying: "y", side: "right", tickformat: ".0%", rangemode: "tozero", showgrid: false },
      margin: { l: 56, r: 48, t: 10, b: 40 } }), CFG);
  }

  function renderNoShow(st) {
    const ms = months.filter((m) => m >= st.from && m <= st.to);
    const traces = st.mods.map((k) => {
      const byMonth = groupBy(filt(Object.assign({}, st, { mods: [k] })), (r) => r.month);
      return { type: "scatter", mode: "lines", name: LABEL[k], x: ms, line: { color: COLORS[k], width: 2.5 },
        y: ms.map((m) => agg(byMonth.get(m) || []).noShowRate), hovertemplate: `${LABEL[k]}: %{y:.1%}<extra></extra>` };
    });
    Plotly.react("c-noshow", traces, layout({ hovermode: "x unified", yaxis: { tickformat: ".0%", rangemode: "tozero" } }), CFG);
  }

  function renderClinic(st) {
    const byClinic = groupBy(filt(st, { ignoreClinic: true }), (r) => r.clinic);
    const cl = D.clinics.map((c) => ({ c, a: agg(byClinic.get(c.clinic_id) || []) }));
    const names = cl.map(({ c }) => `${c.clinic_id} ${c.clinic_name.split(" ")[0]}`);
    const hi = (base) => cl.map(({ c }) => (st.clinic === "ALL" || st.clinic === c.clinic_id ? base : "#c9d3da"));
    Plotly.react("c-clinic", [
      { type: "bar", name: "No-show rate", x: names, y: cl.map((x) => x.a.noShowRate), marker: { color: hi(COLORS.fallback) },
        hovertemplate: "%{x}<br>No-show: %{y:.1%}<extra></extra>", offsetgroup: 1 },
      { type: "bar", name: "Avg days to appt", x: names, y: cl.map((x) => x.a.lead), yaxis: "y2", marker: { color: hi(COLORS.in_person) },
        hovertemplate: "%{x}<br>Days to appt: %{y:.1f}<extra></extra>", offsetgroup: 2 },
    ], layout({ barmode: "group", yaxis: { tickformat: ".0%", title: { text: "No-show" } },
      yaxis2: { overlaying: "y", side: "right", title: { text: "Days" }, showgrid: false },
      margin: { l: 56, r: 48, t: 10, b: 50 } }), CFG);
  }

  function renderEquity(st) {
    const rs = filt(st, { ignoreMod: true });
    const g = groupBy(rs, (r) => `${r.rurality}|${r.age_band}`);
    const traces = [];
    for (const [rur, color] of [["Rural", COLORS.audio], ["Urban", COLORS.video]]) {
      const A = AGES.map((age) => g.get(`${rur}|${age}`) || []);
      traces.push({ type: "bar", name: `${rur} · audio share of virtual`, x: AGES, marker: { color },
        y: A.map((r) => { const v = r.filter((x) => x.modality !== "in_person"); return div(sum(v.filter((x) => x.modality === "audio"), (x) => x.scheduled), sum(v, (x) => x.scheduled)); }),
        hovertemplate: `${rur} %{x}: %{y:.1%} audio<extra></extra>` });
      traces.push({ type: "scatter", mode: "lines+markers", name: `${rur} · video fallback`, x: AGES, yaxis: "y2",
        line: { color, dash: "dot", width: 2.5 }, marker: { symbol: "diamond", size: 8 },
        y: A.map((r) => agg(r).fallbackRate), hovertemplate: `${rur} %{x}: %{y:.1%} fallback<extra></extra>` });
    }
    Plotly.react("c-equity", traces, layout({ barmode: "group", legend: { orientation: "h", y: 1.2, x: 0, font: { size: 11 } },
      xaxis: { title: { text: "Patient age band" } }, yaxis: { tickformat: ".0%", title: { text: "Audio share" } },
      yaxis2: { overlaying: "y", side: "right", tickformat: ".0%", showgrid: false, rangemode: "tozero" },
      margin: { l: 56, r: 48, t: 24, b: 44 } }), CFG);
  }

  function renderDenial(st) {
    const rs = filt(st);
    const m = (k) => rs.filter((r) => r.modality === k);
    const ip = m("in_person"), vi = m("video"), au = m("audio");
    const cats = [
      ["in_person", div(sum(ip, (r) => r.denied), sum(ip, (r) => r.completed))],
      ["video", div(sum(vi, (r) => r.denied - r.fallback_denied), sum(vi, (r) => r.completed - r.fallback))],
      ["audio", div(sum(au, (r) => r.denied), sum(au, (r) => r.completed))],
      ["fallback", div(sum(vi, (r) => r.fallback_denied), sum(vi, (r) => r.fallback))],
    ].filter(([, v]) => isFinite(v));
    Plotly.react("c-denial", [{ type: "bar", x: cats.map(([k]) => LABEL[k]), y: cats.map(([, v]) => v),
      marker: { color: cats.map(([k]) => COLORS[k]) }, text: cats.map(([, v]) => pct(v)), textposition: "outside",
      hovertemplate: "%{x}: %{y:.1%}<extra></extra>" }],
    layout({ showlegend: false, yaxis: { tickformat: ".0%", rangemode: "tozero" } }), CFG);
  }

  function renderUtil(st) {
    const us = util.filter((u) => u.month >= st.from && u.month <= st.to);
    const byP = groupBy(us, (u) => u.provider);
    const ps = [...byP.entries()].map(([p, a]) => ({ p, clinic: a[0].clinic, role: a[0].role,
      u: div(sum(a, (x) => x.completed), sum(a, (x) => x.slots)) })).sort((a, b) => a.p.localeCompare(b.p));
    const avg = div(sum(us, (x) => x.completed), sum(us, (x) => x.slots));
    Plotly.react("c-util", [{ type: "bar", x: ps.map((p) => `${p.p} (${p.clinic} ${p.role})`), y: ps.map((p) => p.u),
      marker: { color: ps.map((p) => (st.clinic === "ALL" || st.clinic === p.clinic ? (p.u < avg * 0.93 ? COLORS.fallback : COLORS.video) : "#c9d3da")) },
      hovertemplate: "%{x}<br>Utilization: %{y:.1%}<extra></extra>" }],
    layout({ showlegend: false, yaxis: { tickformat: ".0%", range: [0, 1] }, xaxis: { tickangle: -35 },
      margin: { l: 48, r: 18, t: 10, b: 90 },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: avg, y1: avg, line: { color: "#5c6b78", dash: "dash", width: 1.5 } }],
      annotations: [{ xref: "paper", x: 1, y: avg, text: `network ${pct(avg)}`, showarrow: false, yanchor: "bottom", xanchor: "right", font: { size: 11, color: "#5c6b78" } }] }), CFG);
  }

  function renderCms() {
    const q = cms.filter((r) => r.dimension === "rurality");
    const series = [["National", "All", "National · all", COLORS.in_person, "solid"], ["National", "Rural", "National · rural", COLORS.audio, "solid"],
      ["National", "Urban", "National · urban", COLORS.video, "solid"], ["New York", "All", "New York · all", COLORS.fallback, "dot"]];
    const traces = series.map(([geo, seg, name, color, dash]) => {
      const s = q.filter((r) => r.geography === geo && r.segment === seg).sort((a, b) => a.year - b.year || a.quarter - b.quarter);
      return { type: "scatter", mode: "lines", name, x: s.map((r) => `${r.year}-Q${r.quarter}`), y: s.map((r) => r.pct_using_telehealth),
        line: { color, dash, width: 2.5 }, hovertemplate: `${name}: %{y:.1%}<extra></extra>` };
    });
    Plotly.react("c-cms", traces, layout({ hovermode: "x unified", yaxis: { tickformat: ".0%", rangemode: "tozero" }, xaxis: { tickangle: -45, nticks: 13 }, margin: { l: 48, r: 18, t: 10, b: 60 } }), CFG);
    const f = D.findings;
    $("cms-note").textContent = `Medicare telehealth use peaked at ${pct(f.cms_peak_pct)} of eligible beneficiaries in ${f.cms_peak_label} and has settled at ${pct(f.cms_latest_all)} in ${f.cms_latest_label} ` +
      `(rural ${pct(f.cms_latest_rural)} vs urban ${pct(f.cms_latest_urban)}). Virtual care is now a stable, permanent slice of care rather than a pandemic spike — and the rural gap mirrors the one in this network.`;
  }

  function renderFindings() {
    $("findings").innerHTML = D.findings.headlines.map((h) =>
      `<div class="finding"><h3>${h.title}</h3><p>${h.text}</p><p class="act">→ ${h.action}</p></div>`).join("");
  }

  function render() {
    const st = state();
    renderKpis(st); renderVolume(st); renderNoShow(st); renderClinic(st); renderEquity(st); renderDenial(st); renderUtil(st);
  }

  function init(data) {
    D = data; rows = toRows(D.cube); util = toRows(D.utilization); cms = toRows(D.cms).map((r) => Object.assign(r, { quarter: +r.quarter }));
    months = D.meta.months;
    const sel = $("f-clinic");
    for (const c of D.clinics) sel.insertAdjacentHTML("beforeend", `<option value="${c.clinic_id}">${c.clinic_id} · ${c.clinic_name} (${c.setting})</option>`);
    for (const id of ["f-from", "f-to"]) $(id).innerHTML = months.map((m) => `<option value="${m}">${m}</option>`).join("");
    $("f-to").value = months[months.length - 1];
    // Deep-linkable filters, e.g. ?clinic=C05&mods=in_person,video&from=2025-01&to=2025-12
    const p = new URLSearchParams(location.search);
    if (p.get("clinic")) sel.value = p.get("clinic");
    if (p.get("from")) $("f-from").value = p.get("from");
    if (p.get("to")) $("f-to").value = p.get("to");
    if (p.get("mods")) { const ms = p.get("mods").split(","); document.querySelectorAll("input[name=mod]").forEach((e) => { e.checked = ms.includes(e.value); }); }
    document.querySelectorAll("select, input[name=mod]").forEach((e) => e.addEventListener("change", render));
    $("f-reset").addEventListener("click", () => {
      sel.value = "ALL"; $("f-from").value = months[0]; $("f-to").value = months[months.length - 1];
      document.querySelectorAll("input[name=mod]").forEach((e) => { e.checked = true; }); render();
    });
    renderCms(); renderFindings(); render();
    document.body.dataset.ready = "1";
  }

  fetch("data/dashboard.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(init)
    .catch((e) => { document.querySelector("main").insertAdjacentHTML("afterbegin", `<p class="card">Could not load dashboard data (${e}). Serve the docs/ folder over HTTP.</p>`); });
})();
