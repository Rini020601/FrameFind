const SAMPLE_RECORDS = [
  {
    id: "typeerror",
    name: "VS Code - TypeError Bug (2026-11-15).mp4",
    category: "Code & Terminal",
    source: "Apple Vision OCR",
    time: "00:42",
    duration: "03:18",
    progress: 22,
    snippet: "TypeError: Cannot read properties of undefined (reading 'token') at auth.ts:48",
    keywords: ["typeerror", "token", "undefined", "vs code", "auth"],
    frameLines: [
      "src/services/auth.ts — VS Code",
      "47 | const session = await fetchSession(req);",
      "48 | <span class=\"highlight-box\">TypeError: Cannot read properties of undefined (reading 'token')</span>",
      "49 |     at verifyUser (auth.ts:48:19)",
    ],
    footerNote: "Jumped to 00:42 · Yellow OCR bounding-box highlight",
  },
  {
    id: "privacy",
    name: "Terminal - Deploy Env Config (2026-11-22).png",
    category: "Code & Terminal",
    source: "Privacy Redactor",
    time: "Screenshot",
    duration: "1 frame",
    progress: 100,
    snippet: "OPENAI_API_KEY=sk-proj… detected & blurred before export",
    keywords: ["sk-proj", "api", "key", "secret", "privacy", "redact", "email"],
    frameLines: [
      "~/.env.production — Terminal",
      "OPENAI_API_KEY=<span class=\"redacted\">sk-proj-94k2a8x01m7f2q9</span>  ← auto-blurred",
      "CONTACT_EMAIL=<span class=\"redacted\">ops@acme.io</span>  ← auto-blurred",
      "STATUS: 2 sensitive credentials redacted",
    ],
    footerNote: "1-Click Privacy Redactor · Ready to share safely",
  },
  {
    id: "roadmap",
    name: "Keynote - Q3 Product Roadmap (2026-11-21).mov",
    category: "Slides & Presentation",
    source: "Apple Vision OCR",
    time: "04:15",
    duration: "12:40",
    progress: 34,
    snippet: "Q3 Product Roadmap — Strategic Deliverables & Key Takeaways",
    keywords: ["roadmap", "slides", "keynote", "q3", "deliverables"],
    frameLines: [
      "Slide 08 / 24 — Keynote",
      "<span class=\"highlight-box\">Q3 Product Roadmap</span>",
      "• Native Spotlight integration (kMDItemFinderComment)",
      "• VideoToolbox compression: 850 MB → 65 MB (92% saved)",
    ],
    footerNote: "Jumped to 04:15 · Compressed 92% with VideoToolbox",
  },
  {
    id: "kubernetes",
    name: "Zoom - Infrastructure Sync (2026-11-24).mov",
    category: "Meeting & Chat",
    source: "Whisper Audio",
    time: "08:12",
    duration: "24:05",
    progress: 34,
    snippet: "“…we're scheduling the quarterly kubernetes rollout for Thursday morning…”",
    keywords: ["kubernetes", "zoom", "meeting", "audio", "rollout", "whisper"],
    frameLines: [
      "Zoom Meeting · Audio Transcript Match",
      "[08:10] Host: Let's confirm the deployment window.",
      "[08:12] <span class=\"highlight-box\">\"quarterly kubernetes rollout for Thursday morning\"</span>",
      "[08:19] Aligned automatically with nearest video keyframe",
    ],
    footerNote: "Jumped to 08:12 · Local Whisper transcript match",
  },
];

const searchInput = document.getElementById("demo-search");
const resultsEl = document.getElementById("demo-results");
const stageEl = document.getElementById("demo-stage");
const chips = Array.from(document.querySelectorAll(".chip"));

let selectedId = SAMPLE_RECORDS[0].id;

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightSnippet(text, query) {
  const safe = escapeHtml(text);
  const q = query.trim();
  if (!q) return safe;
  const escapedQuery = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return safe.replace(new RegExp(`(${escapedQuery})`, "gi"), "<mark>$1</mark>");
}

function renderStage(record) {
  if (!record) {
    stageEl.innerHTML = `<div class="muted">No indexed frames match this query. Try <code>TypeError</code>, <code>sk-proj</code>, <code>Roadmap</code>, or <code>kubernetes</code>.</div>`;
    return;
  }

  stageEl.innerHTML = `
    <div class="stage-meta">
      <div class="stage-title">${escapeHtml(record.name)}</div>
      <div class="stage-badges">
        <span class="meta-pill blue">${escapeHtml(record.source)}</span>
        <span class="meta-pill green">${escapeHtml(record.category)}</span>
      </div>
    </div>
    <div class="stage-frame">${record.frameLines.join("<br />")}</div>
    <div class="scrubber-wrap">
      <div class="scrubber-track">
        <div class="scrubber-fill" style="width: ${record.progress}%"></div>
      </div>
      <div class="scrubber-foot">
        <span>${escapeHtml(record.footerNote)}</span>
        <span>${escapeHtml(record.time)} / ${escapeHtml(record.duration)}</span>
      </div>
    </div>
  `;
}

function renderResults(query = "") {
  const q = query.trim().toLowerCase();
  const matches = q
    ? SAMPLE_RECORDS.filter(
        (r) =>
          r.name.toLowerCase().includes(q) ||
          r.snippet.toLowerCase().includes(q) ||
          r.category.toLowerCase().includes(q) ||
          r.keywords.some((k) => k.includes(q))
      )
    : SAMPLE_RECORDS;

  if (!matches.some((m) => m.id === selectedId)) {
    selectedId = matches[0] ? matches[0].id : null;
  }

  resultsEl.innerHTML = matches.length
    ? matches
        .map(
          (r) => `
        <button
          type="button"
          class="result-item ${r.id === selectedId ? "selected" : ""}"
          data-id="${r.id}"
          role="listitem"
        >
          <div class="result-top">
            <span class="result-name">${escapeHtml(r.name)}</span>
            <span class="time-badge">${escapeHtml(r.time)}</span>
          </div>
          <div class="result-snippet">${highlightSnippet(r.snippet, query)}</div>
        </button>
      `
        )
        .join("")
    : `<div class="muted" style="font-size:13px; padding:12px;">No matches for "${escapeHtml(query)}"</div>`;

  resultsEl.querySelectorAll(".result-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      selectedId = btn.dataset.id;
      renderResults(searchInput.value);
    });
  });

  const activeRecord = matches.find((m) => m.id === selectedId) || matches[0];
  renderStage(activeRecord);
}

searchInput.addEventListener("input", () => {
  const val = searchInput.value.trim().toLowerCase();
  chips.forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.query.toLowerCase() === val);
  });
  renderResults(searchInput.value);
});

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const q = chip.dataset.query;
    searchInput.value = q;
    chips.forEach((c) => c.classList.toggle("active", c === chip));
    renderResults(q);
  });
});

// Initialize interactive demo with first chip selected
searchInput.value = "TypeError";
renderResults("TypeError");

// Quickstart tabs & copy button
const codeTabs = Array.from(document.querySelectorAll(".code-tab"));
const codeBlocks = {
  install: document.getElementById("code-install"),
  gui: document.getElementById("code-gui"),
  daemon: document.getElementById("code-daemon"),
};
const copyBtn = document.getElementById("copy-code");
let activeTab = "install";

codeTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    activeTab = tab.dataset.tab;
    codeTabs.forEach((t) => {
      const isActive = t.dataset.tab === activeTab;
      t.classList.toggle("active", isActive);
      t.setAttribute("aria-selected", String(isActive));
    });
    Object.entries(codeBlocks).forEach(([key, el]) => {
      el.classList.toggle("hidden", key !== activeTab);
    });
    copyBtn.textContent = "Copy";
  });
});

copyBtn.addEventListener("click", async () => {
  const text = codeBlocks[activeTab].innerText.trim();
  try {
    await navigator.clipboard.writeText(text);
    copyBtn.textContent = "Copied!";
    setTimeout(() => {
      copyBtn.textContent = "Copy";
    }, 1500);
  } catch {
    copyBtn.textContent = "Select to copy";
  }
});
