import { MultiDirectedGraph } from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { animateNodes } from "sigma/utils";

const TYPE_COLOURS = {
  quotation: "#c8553d",
  "title-source": "#d9a441",
  mention: "#5b8e7d",
  allusion: "#7d5ba6",
  "shared-vocabulary": "#3a7ca5",
  theme: "#8c8c8c",
};
const FALLBACK_COLOUR = "#555555";

const ERAS = [
  { label: "Before 1500", until: 1500, colour: "#6b4e31" },
  { label: "1500 to 1799", until: 1800, colour: "#a0522d" },
  { label: "1800 to 1899", until: 1900, colour: "#b5838d" },
  { label: "1900 to 1945", until: 1946, colour: "#457b9d" },
  { label: "After 1945", until: Infinity, colour: "#1d3557" },
];
const NO_YEAR_COLOUR = "#aaaaaa";
const DIMMED = "#e4ddd0";

const state = {
  data: null,
  minConfidence: 0,
  types: new Set(),
  showProposed: true,
  showRejected: false,
  layout: new URLSearchParams(location.search).get("layout") === "timeline" ? "timeline" : "force",
  focus: null, // work id whose neighbourhood is shown
  selected: null, // link id shown in the detail panel
  lens: null, // { term, counts: Map(work id -> count) }
};

let graph = null;
let renderer = null;
let positions = { force: {}, timeline: {} };
let stopAnimation = null;

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (text) =>
  String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function eraColour(year) {
  if (year === null || year === undefined) return NO_YEAR_COLOUR;
  return ERAS.find((era) => year < era.until).colour;
}

function withAlpha(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function workById(id) {
  return state.data.works.find((work) => work.id === id);
}

function linkVisible(link) {
  if (link.confidence < state.minConfidence && link.status !== "rejected") return false;
  if (!state.types.has(link.type)) return false;
  if (link.status === "rejected") return state.showRejected;
  if (link.status === "proposed") return state.showProposed;
  return true;
}

function visibleLinks() {
  return state.data.links.filter(linkVisible).sort((a, b) => b.confidence - a.confidence);
}

// Layouts ---------------------------------------------------------------

const LANES = 9;

// Half of the axis is true to the calendar and half gives every work equal room, so the crowded
// decades spread out while earlier and later still read left to right.
function timelineScale() {
  const years = state.data.works.map((work) => work.year).filter((year) => year !== null).sort((a, b) => a - b);
  const minYear = years[0];
  const maxYear = years[years.length - 1];
  return (year) => {
    if (year === null || year === undefined) return -0.05;
    const calendar = (year - minYear) / Math.max(1, maxYear - minYear);
    const rank = years.filter((other) => other < year).length / years.length;
    return 0.5 * calendar + 0.5 * rank;
  };
}

function computePositions() {
  const ids = graph.filterNodes((_, attrs) => !attrs.tick);
  ids.forEach((id, index) => {
    const angle = (2 * Math.PI * index) / ids.length;
    graph.mergeNodeAttributes(id, { x: Math.cos(angle), y: Math.sin(angle) });
  });
  const layoutGraph = graph.copy();
  layoutGraph.forEachNode((id, attrs) => attrs.tick && layoutGraph.dropNode(id));
  forceAtlas2.assign(layoutGraph, {
    iterations: 400,
    settings: { ...forceAtlas2.inferSettings(layoutGraph), gravity: 1.5, scalingRatio: 12, adjustSizes: true },
  });

  const xs = [];
  const ys = [];
  layoutGraph.forEachNode((_, attrs) => { xs.push(attrs.x); ys.push(attrs.y); });
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const norm = (value, low, high) => (high === low ? 0.5 : (value - low) / (high - low));

  const scale = timelineScale();
  const width = 2.4; // the timeline is wider than it is tall
  const byYear = [...state.data.works].sort((a, b) => (a.year ?? -Infinity) - (b.year ?? -Infinity) || a.id - b.id);
  const lane = new Map(byYear.map((work, index) => [String(work.id), (index * 4) % LANES]));

  positions = { force: {}, timeline: {} };
  layoutGraph.forEachNode((id, attrs) => {
    positions.force[id] = { x: norm(attrs.x, minX, maxX), y: norm(attrs.y, minY, maxY) };
    positions.timeline[id] = { x: width * scale(graph.getNodeAttribute(id, "year")), y: (lane.get(id) + 0.5) / LANES };
  });
  graph.forEachNode((id, attrs) => {
    if (!attrs.tick) return;
    // Hidden nodes still count towards the view's bounding box, so ticks wait in the middle.
    positions.force[id] = { x: 0.5, y: 0.5 };
    positions.timeline[id] = { x: width * scale(attrs.year), y: -0.06 };
  });
}

function tickYears() {
  const years = state.data.works.map((work) => work.year).filter((year) => year !== null);
  if (!years.length) return [];
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const ticks = new Set([minYear]);
  for (let year = Math.max(1500, Math.ceil(minYear / 100) * 100); year <= maxYear; year += 100) ticks.add(year);
  return [...ticks];
}

function applyLayout(animate) {
  const target = positions[state.layout];
  if (stopAnimation) stopAnimation();
  if (animate) {
    stopAnimation = animateNodes(graph, target, { duration: 700 });
  } else {
    graph.forEachNode((id) => graph.mergeNodeAttributes(id, target[id]));
  }
}

// Graph -----------------------------------------------------------------

function buildGraph() {
  graph = new MultiDirectedGraph();
  const degree = new Map();
  for (const link of state.data.links) {
    if (link.status === "rejected") continue;
    degree.set(link.source, (degree.get(link.source) || 0) + 1);
    degree.set(link.target, (degree.get(link.target) || 0) + 1);
  }
  for (const work of state.data.works) {
    const base = work.kind === "subwork" ? 4 : 6;
    graph.addNode(work.id, {
      label: work.title,
      year: work.year,
      size: base + 2.2 * Math.sqrt(degree.get(work.id) || 0),
      color: eraColour(work.year),
      stub: work.kind === "stub",
      x: 0,
      y: 0,
    });
  }
  for (const work of state.data.works) {
    if (work.parent !== null && graph.hasNode(work.parent)) {
      graph.addEdgeWithKey(`part-${work.id}`, work.id, work.parent, {
        partOf: true, size: 1, color: "#bdb3a2", type: "line",
      });
    }
  }
  for (const link of state.data.links) {
    graph.addEdgeWithKey(`link-${link.id}`, link.source, link.target, {
      linkId: link.id,
      size: 1 + 4 * link.confidence,
      type: "arrow",
    });
  }
  for (const year of tickYears()) {
    graph.addNode(`tick-${year}`, {
      tick: true, year, label: year < 0 ? `${-year} BC` : String(year), size: 2, color: "#b0a696", x: 0, y: 0,
    });
  }
}

function neighbourhood(workId) {
  const keep = new Set([workId]);
  for (const link of visibleLinks()) {
    if (link.source === workId) keep.add(link.target);
    if (link.target === workId) keep.add(link.source);
  }
  for (const work of state.data.works) {
    if (work.parent === workId) keep.add(work.id);
    if (work.id === workId && work.parent !== null) keep.add(work.parent);
  }
  return keep;
}

function nodeReducer(node, attrs) {
  if (attrs.tick) return state.layout === "timeline" ? { ...attrs, forceLabel: true } : { ...attrs, hidden: true };
  const id = Number(node);
  const result = { ...attrs };
  if (state.lens) {
    const count = state.lens.counts.get(id);
    if (count) {
      result.highlighted = true;
      result.label = `${attrs.label} (${count})`;
    } else {
      result.color = DIMMED;
      result.label = "";
    }
  }
  if (state.focus !== null && !neighbourhood(state.focus).has(id)) {
    result.color = DIMMED;
    result.label = "";
  }
  if (state.focus === id) result.highlighted = true;
  return result;
}

function edgeReducer(edge, attrs) {
  if (attrs.partOf) return attrs;
  const link = state.data.links.find((candidate) => candidate.id === attrs.linkId);
  if (!link || !linkVisible(link)) return { ...attrs, hidden: true };
  if (state.focus !== null && link.source !== state.focus && link.target !== state.focus) return { ...attrs, hidden: true };
  const base = TYPE_COLOURS[link.type] || FALLBACK_COLOUR;
  const alpha = link.status === "accepted" ? 0.9 : link.status === "rejected" ? 0.25 : 0.55;
  const selected = state.selected === link.id;
  return {
    ...attrs,
    color: selected ? base : withAlpha(base, alpha),
    size: selected ? attrs.size + 2 : attrs.size,
    zIndex: selected ? 2 : link.status === "accepted" ? 1 : 0,
  };
}

function startRenderer() {
  if (renderer) renderer.kill();
  renderer = new Sigma(graph, $("#graph"), {
    nodeReducer,
    edgeReducer,
    enableEdgeEvents: true,
    zIndex: true,
    labelFont: "Georgia, serif",
    labelSize: 13,
    labelColor: { color: "#2b2620" },
    labelRenderedSizeThreshold: 7,
    defaultEdgeType: "arrow",
  });
  renderer.on("clickNode", ({ node }) => {
    if (graph.getNodeAttribute(node, "tick")) return;
    state.focus = Number(node);
    state.selected = null;
    refresh();
  });
  renderer.on("clickEdge", ({ edge }) => {
    const linkId = graph.getEdgeAttribute(edge, "linkId");
    if (linkId === undefined) return;
    state.selected = linkId;
    refresh();
  });
  renderer.on("clickStage", () => {
    state.focus = null;
    state.selected = null;
    refresh();
  });
  renderer.on("enterEdge", () => { $("#graph").style.cursor = "pointer"; });
  renderer.on("leaveEdge", () => { $("#graph").style.cursor = ""; });
}

// Detail panel ----------------------------------------------------------

function describeWork(work) {
  const year = work.year === null ? "year unknown" : work.year < 0 ? `${-work.year} BC` : work.year;
  const kind = work.kind === "stub" ? ", no text held" : work.kind === "subwork" ? `, in ${workById(work.parent)?.title}` : "";
  return `${escapeHtml(work.author)}, ${year}${escapeHtml(kind)}`;
}

function linkListItem(link) {
  const colour = TYPE_COLOURS[link.type] || FALLBACK_COLOUR;
  return `<li data-link="${link.id}">
    <span class="pair"><span class="swatch" style="background:${colour}"></span>${escapeHtml(workById(link.source).title)} → ${escapeHtml(workById(link.target).title)}</span>
    <span class="meta">${escapeHtml(link.type)} · ${link.confidence.toFixed(2)} · ${link.status}${link.reviewed ? " · reviewed" : ""}</span>
  </li>`;
}

function renderLinkList(title, links, intro = "") {
  return `<h3>${title}</h3>${intro}
    <p class="meta">${links.length} link${links.length === 1 ? "" : "s"} shown, most confident first.</p>
    <ul class="links">${links.map(linkListItem).join("")}</ul>`;
}

function renderLink(link) {
  const source = workById(link.source);
  const target = workById(link.target);
  const colour = TYPE_COLOURS[link.type] || FALLBACK_COLOUR;
  const evidence = link.evidence
    .map(
      (item) => `<div class="evidence">
        <figure><figcaption>${escapeHtml(source.title)}</figcaption><blockquote>${quoteHtml(item.source_quote)}</blockquote></figure>
        <figure><figcaption>${escapeHtml(target.title)}</figcaption><blockquote>${quoteHtml(item.target_quote)}</blockquote></figure>
      </div>`,
    )
    .join("");
  const typeOptions = Object.keys(TYPE_COLOURS)
    .map((type) => `<option value="${type}" ${type === link.type ? "selected" : ""}>${type}</option>`)
    .join("");
  const review = state.data.reviewable
    ? `<div class="review">
        <label>Type <select id="review-type">${typeOptions}</select></label>
        <input id="review-note" type="text" placeholder="Note (optional)" value="${escapeHtml(link.note || "")}" />
        <div class="buttons">
          <button class="accept" data-verdict="accept">Accept</button>
          <button class="reject" data-verdict="reject">Reject</button>
          <button id="next-unreviewed">Next unreviewed</button>
        </div>
        <p class="error" id="review-error"></p>
      </div>`
    : "";
  return `<button class="back" id="back">← All links</button>
    <h3>${escapeHtml(source.title)} → ${escapeHtml(target.title)}</h3>
    <p class="direction">${describeWork(source)} draws on ${describeWork(target)}</p>
    <p><span class="chip" style="background:${colour}">${escapeHtml(link.type)}</span>
      <span class="status ${link.status}">${link.status}${link.reviewed ? (state.data.reviewable ? " by you" : " by the owner") : link.status === "proposed" ? "" : " by the judge"}</span></p>
    <div class="bar"><span style="width:${Math.round(link.confidence * 100)}%"></span></div>
    <p class="meta">Confidence ${link.confidence.toFixed(2)} · detector ${escapeHtml(link.detector)} v${escapeHtml(link.detector_version)}</p>
    <p>${escapeHtml(link.rationale)}</p>
    ${link.article ? `<p class="meta">From: ${escapeHtml(link.article)}</p>` : ""}
    ${evidence}
    ${review}`;
}

function renderDetail() {
  const panel = $("#detail");
  const selected = state.data.links.find((link) => link.id === state.selected);
  if (selected) {
    panel.innerHTML = renderLink(selected);
  } else if (state.focus !== null) {
    const work = workById(state.focus);
    const links = visibleLinks().filter((link) => link.source === work.id || link.target === work.id);
    panel.innerHTML =
      `<button class="back" id="back">← All links</button>` +
      renderLinkList(escapeHtml(work.title), links, `<p class="direction">${describeWork(work)}</p>`);
  } else {
    panel.innerHTML = renderLinkList("Links", visibleLinks());
  }
}

function nextUnreviewed() {
  const queue = visibleLinks().filter((link) => !link.reviewed && link.id !== state.selected);
  state.selected = queue.length ? queue[0].id : null;
  refresh();
}

async function submitReview(verdict) {
  const link = state.data.links.find((candidate) => candidate.id === state.selected);
  const type = $("#review-type").value;
  const body = { link_id: link.id, verdict, note: $("#review-note").value || null };
  if (type !== link.type) body.type = type;
  const response = await fetch("./api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    $("#review-error").textContent = `Could not save the review (${response.status}).`;
    return;
  }
  await load(false);
  nextUnreviewed();
}

$("#detail").addEventListener("click", (event) => {
  const item = event.target.closest("li[data-link]");
  if (item) {
    state.selected = Number(item.dataset.link);
    refresh();
  } else if (event.target.id === "back") {
    state.selected = null;
    state.focus = null;
    refresh();
  } else if (event.target.id === "next-unreviewed") {
    nextUnreviewed();
  } else if (event.target.dataset.verdict) {
    submitReview(event.target.dataset.verdict);
  }
});

// Controls --------------------------------------------------------------

function renderControls() {
  const types = [...new Set([...Object.keys(TYPE_COLOURS), ...state.data.links.map((link) => link.type)])];
  $("#types").innerHTML = types
    .map((type) => {
      const count = state.data.links.filter((link) => link.type === type).length;
      const colour = TYPE_COLOURS[type] || FALLBACK_COLOUR;
      return `<label><input type="checkbox" value="${type}" ${state.types.has(type) ? "checked" : ""} />
        <span class="swatch" style="background:${colour}"></span>${type} (${count})</label>`;
    })
    .join("");
  $("#eras").innerHTML = ERAS.map((era) => `<div><span class="dot" style="background:${era.colour}"></span>${era.label}</div>`).join("");
  const works = state.data.works.length;
  const accepted = state.data.links.filter((link) => link.status === "accepted").length;
  const reviewed = state.data.links.filter((link) => link.reviewed).length;
  const counts = state.data.reviewable ? `${accepted} accepted, ${reviewed} reviewed by you` : `${accepted} accepted`;
  $("#summary").textContent = `${works} works, ${state.data.links.length} links (${counts}). Arrows point from a work to the earlier work it draws on.`;
  $("#lens-section").hidden = !state.data.reviewable;
  $("#show-rejected").closest("label").hidden = !state.data.reviewable;
}

$("#types").addEventListener("change", (event) => {
  if (event.target.checked) state.types.add(event.target.value);
  else state.types.delete(event.target.value);
  refresh();
});
$("#confidence").addEventListener("input", (event) => {
  state.minConfidence = Number(event.target.value);
  $("#confidence-value").textContent = state.minConfidence.toFixed(2);
  refresh();
});
$("#show-proposed").addEventListener("change", (event) => { state.showProposed = event.target.checked; refresh(); });
$("#show-rejected").addEventListener("change", (event) => { state.showRejected = event.target.checked; refresh(); });
document.querySelectorAll('input[name="layout"]').forEach((input) =>
  input.addEventListener("change", (event) => {
    state.layout = event.target.value;
    applyLayout(true);
    refresh();
  }),
);
$("#lens-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const term = $("#lens").value.trim();
  if (!term) {
    state.lens = null;
    $("#lens-result").textContent = "";
    refresh();
    return;
  }
  const response = await fetch(`./api/term?q=${encodeURIComponent(term)}`);
  if (!response.ok) {
    $("#lens-result").textContent = "The term lookup failed.";
    return;
  }
  const found = await response.json();
  state.lens = { term, counts: new Map(found.works.map((work) => [work.id, work.count])) };
  $("#lens-result").textContent = found.works.length
    ? `"${term}" appears in ${found.works.length} work${found.works.length === 1 ? "" : "s"}. Clear the box and press Enter to reset.`
    : `No work uses "${term}".`;
  refresh();
});
$("#lens").addEventListener("search", (event) => {
  if (!event.target.value) $("#lens-form").requestSubmit();
});

// Loading ---------------------------------------------------------------

function refresh() {
  renderDetail();
  renderer.refresh();
}

async function load(first) {
  const response = await fetch("./graph.json", { cache: "no-store" });
  if (!response.ok) {
    $("#detail").innerHTML = `<p class="error">Could not load graph.json (${response.status}). Run <code>book-links serve</code>, or export a graph next to this page.</p>`;
    return;
  }
  state.data = await response.json();
  if (first) {
    state.types = new Set([...Object.keys(TYPE_COLOURS), ...state.data.links.map((link) => link.type)]);
    buildGraph();
    computePositions();
    applyLayout(false);
    startRenderer();
  } else {
    // After a review only statuses and confidences change, so the layout is kept.
    for (const link of state.data.links) {
      if (graph.hasEdge(`link-${link.id}`)) graph.setEdgeAttribute(`link-${link.id}`, "size", 1 + 4 * link.confidence);
    }
  }
  renderControls();
  document.querySelector(`input[name="layout"][value="${state.layout}"]`).checked = true;
  refresh();
}

load(true);

function quoteHtml(quote) {
  return quote ? escapeHtml(quote) : `<span class="none">no passage</span>`;
}
