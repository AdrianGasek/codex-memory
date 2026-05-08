const results = document.querySelector("#results");
const stream = document.querySelector("#stream");
const debugPanel = document.querySelector("#debug-panel");
const selectedEntry = document.querySelector("#selected-entry");
const health = document.querySelector("#health");
const status = document.querySelector("#status");
const count = document.querySelector("#result-count");

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[char],
  );
}

async function loadSearch(filters = {}) {
  results.innerHTML = "<p class='meta'>Loading results...</p>";
  const params = new URLSearchParams({
    query: filters.query || "",
    limit: "20",
  });
  if (filters.type) params.set("type", filters.type);
  if (filters.project) params.set("project", filters.project);
  for (const tag of filters.tags || []) params.append("tags", tag);
  const response = await fetch(`/memory/search?${params}`);
  const body = await response.json();
  count.textContent = `${body.results.length} results`;
  results.innerHTML =
    body.results
      .map(
        ({ entry, score, reason }) => `
    <article class="row">
      <div class="type">${escapeHtml(entry.type)}</div>
      <div>
        <div class="title">${escapeHtml(entry.title)}</div>
        <div class="text">${escapeHtml(entry.context || entry.resolution || reason)}</div>
        <button class="select-entry" data-memory-id="${escapeHtml(entry.id)}" type="button">Details</button>
      </div>
      <div class="score">${Number(score).toFixed(2)}</div>
    </article>
  `,
      )
      .join("") || "<p class='meta'>No memory entries found.</p>";
  results.querySelectorAll("[data-memory-id]").forEach((button) => {
    button.addEventListener("click", () =>
      loadEntryDetails(button.dataset.memoryId),
    );
  });
  await loadDebug(filters);
}

async function loadStream() {
  stream.innerHTML = "<p class='meta'>Loading stream...</p>";
  const response = await fetch("/memory/history?limit=20");
  const body = await response.json();
  stream.innerHTML =
    body
      .map(
        (event) => `
    <div class="event">
      <strong>${escapeHtml(event.action)} &middot; ${escapeHtml(event.snapshot.title)}</strong>
      <span class="text">${escapeHtml(event.timestamp)}</span>
    </div>
  `,
      )
      .join("") || "<p class='meta'>No history yet.</p>";
}

async function loadEntryDetails(memoryId) {
  selectedEntry.innerHTML = "<p class='meta'>Loading entry details...</p>";
  const [historyResponse, auditResponse] = await Promise.all([
    fetch(`/memory/history?memory_id=${encodeURIComponent(memoryId)}&limit=10`),
    fetch(`/memory/audit?memory_id=${encodeURIComponent(memoryId)}&limit=10`),
  ]);
  const [history, audit] = await Promise.all([
    historyResponse.json(),
    auditResponse.json(),
  ]);
  selectedEntry.innerHTML = `
    <div>
      <strong>History</strong>
      ${
        history
          .map(
            (event) => `
        <div class="event">
          <span>${escapeHtml(event.action)} &middot; ${escapeHtml(event.timestamp)}</span>
        </div>
      `,
          )
          .join("") || "<p class='meta'>No history.</p>"
      }
    </div>
    <div>
      <strong>Audit</strong>
      ${
        audit
          .map(
            (event) => `
        <div class="event">
          <span>${escapeHtml(event.action)} &middot; ${escapeHtml(event.timestamp)}</span>
        </div>
      `,
          )
          .join("") || "<p class='meta'>No audit events.</p>"
      }
    </div>
  `;
}

async function loadHealth() {
  health.innerHTML = "<p class='meta'>Loading diagnostics...</p>";
  const response = await fetch("/memory/health/diagnostics");
  const body = await response.json();
  health.innerHTML =
    body.components
      .map(
        (component) => `
    <div class="event">
      <strong>${escapeHtml(component.name)} &middot; ${escapeHtml(component.status)}</strong>
      <span class="text">${escapeHtml(component.detail)}</span>
    </div>
  `,
      )
      .join("") || "<p class='meta'>No diagnostics.</p>";
}

async function loadDebug(filters = {}) {
  debugPanel.innerHTML = "<p class='meta'>Loading debug data...</p>";
  const params = new URLSearchParams({
    query: filters.query || "",
    limit: "5",
  });
  if (filters.type) params.set("type", filters.type);
  if (filters.project) params.set("project", filters.project);
  for (const tag of filters.tags || []) params.append("tags", tag);
  const response = await fetch(`/memory/debug/search?${params}`);
  const body = await response.json();
  debugPanel.innerHTML =
    body.results
      .map(
        ({ entry, score, reason, components }) => `
    <div class="debug-row">
      <div>
        <strong>${escapeHtml(entry.title)}</strong>
        <div class="text">${escapeHtml(reason)}</div>
      </div>
      <div class="components">
        keyword ${Number(components.keyword || 0).toFixed(2)}
        recency ${Number(components.recency || 0).toFixed(2)}
        semantic ${Number(components.semantic || 0).toFixed(2)}
        total ${Number(score || 0).toFixed(2)}
      </div>
    </div>
  `,
      )
      .join("") || "<p class='meta'>No debug results.</p>";
}

document.querySelector("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  loadSearch({
    query: data.get("query"),
    type: data.get("type"),
    project: data.get("project"),
    tags: String(data.get("tags") || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean),
  });
});

Promise.all([loadSearch(), loadStream(), loadHealth()])
  .then(() => {
    status.textContent = "Ready";
  })
  .catch((error) => {
    status.textContent = "Error";
    results.innerHTML = `<p class="meta">${escapeHtml(error.message)}</p>`;
    debugPanel.innerHTML = "<p class='meta'>Unable to load debug data.</p>";
    stream.innerHTML = "<p class='meta'>Unable to load stream.</p>";
    health.innerHTML = "<p class='meta'>Unable to load diagnostics.</p>";
  });
