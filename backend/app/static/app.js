const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`${resp.status} ${text}`);
  }
  return resp.json();
}

function setStatus(msg) {
  $("action-status").textContent = msg;
}

async function refreshOverview() {
  try {
    const [graph, anomalies, injection] = await Promise.all([
      api("/api/graph"),
      api("/api/telemetry/anomalies"),
      api("/api/failure-injection/status"),
    ]);
    const anomalousCount = anomalies.results.filter((r) => r.is_anomalous).length;
    $("overview-stats").innerHTML = `
      <div class="stat"><span class="value">${graph.nodes.length}</span><span class="label">Services in graph</span></div>
      <div class="stat ${anomalousCount > 0 ? "anomalous" : ""}"><span class="value">${anomalousCount} / ${anomalies.results.length}</span><span class="label">Anomalous services</span></div>
      <div class="stat"><span class="value">${injection["inventory-service"].latency_enabled ? "ON" : "off"}</span><span class="label">Latency injection</span></div>
      <div class="stat"><span class="value">${injection["inventory-service"].errors_enabled ? "ON" : "off"}</span><span class="label">Error injection</span></div>
      <div class="stat"><span class="value">${injection["order-service"].load_enabled ? "ON" : "off"}</span><span class="label">Load injection</span></div>
    `;
    $("chk-latency").checked = injection["inventory-service"].latency_enabled;
    $("chk-errors").checked = injection["inventory-service"].errors_enabled;
    $("chk-load").checked = injection["order-service"].load_enabled;
  } catch (e) {
    $("overview-stats").textContent = `Failed to load overview: ${e.message}`;
  }
}

async function renderGraph(service) {
  const box = $("graph-view");
  box.textContent = "Loading dependency graph…";
  try {
    const blast = await api(`/api/graph/blast-radius?service=${encodeURIComponent(service)}`);
    if (blast.potentially_impacted.length === 0) {
      box.innerHTML = `<p><strong>${service}</strong> has no downstream dependencies.</p>`;
      return;
    }
    box.innerHTML =
      `<p>Blast radius of a change to <strong>${service}</strong> — potentially impacted, not confirmed affected:</p>` +
      blast.potentially_impacted
        .map(
          (item) =>
            `<div class="blast-item"><span class="dist-badge">distance ${item.dependency_distance}</span>${item.service}</div>`
        )
        .join("");
  } catch (e) {
    box.innerHTML = `<div class="error-box">Failed to load graph: ${e.message}</div>`;
  }
}

async function renderTimeline(service) {
  const box = $("timeline-view");
  box.textContent = "Loading evidence timeline…";
  try {
    const [deployment, anomalies] = await Promise.all([
      api(`/api/events/latest-deployment?service=${encodeURIComponent(service)}`).catch(() => null),
      api("/api/telemetry/anomalies/recent"),
    ]);

    const events = [];
    if (deployment) {
      events.push({
        time: deployment.deployment_timestamp,
        text: `Deployment of ${deployment.service} — commit ${deployment.commit_sha} by ${deployment.author}`,
      });
    }
    for (const a of anomalies.anomalies) {
      events.push({ time: a.timestamp, text: `Anomaly: ${a.service} flagged on ${a.metric} (score ${a.score.toFixed(3)})` });
    }
    events.sort((a, b) => new Date(a.time) - new Date(b.time));

    if (events.length === 0) {
      box.innerHTML = "<p>No deployment or anomaly events yet.</p>";
      return;
    }
    box.innerHTML = events
      .map(
        (e) =>
          `<div class="timeline-item"><span class="timeline-time">${new Date(e.time).toLocaleTimeString()}</span> — ${e.text}</div>`
      )
      .join("");
  } catch (e) {
    box.innerHTML = `<div class="error-box">Failed to load timeline: ${e.message}</div>`;
  }
}

function renderSummary(result) {
  const box = $("summary-view");
  const hypotheses = result.hypotheses
    .map(
      (h) => `
      <div class="hypothesis">
        <div class="statement">${h.statement}</div>
        <h4>Supporting evidence</h4>
        <ul>${h.supporting_evidence.map((e) => `<li><span class="evidence-source">${e.source}</span> — ${e.detail}</li>`).join("")}</ul>
        <h4>Limitations</h4>
        <ul class="limitations">${h.limitations.map((l) => `<li>${l}</li>`).join("")}</ul>
      </div>`
    )
    .join("");
  box.innerHTML = `<p>${result.summary}</p>${hypotheses}`;
}

async function runInvestigation() {
  const service = $("service-select").value;
  const btn = $("btn-investigate");
  btn.disabled = true;
  setStatus(`Investigating ${service}… this calls the LLM through MCP tools and can take up to a minute.`);
  $("summary-view").textContent = "Investigating…";

  await Promise.all([renderGraph(service), renderTimeline(service)]);

  try {
    const result = await api(`/api/investigate?service=${encodeURIComponent(service)}`, { method: "POST" });
    renderSummary(result);
    setStatus("Investigation complete.");
  } catch (e) {
    $("summary-view").innerHTML = `<div class="error-box">Investigation failed: ${e.message}</div>`;
    setStatus("Investigation failed.");
  } finally {
    btn.disabled = false;
    refreshOverview();
  }
}

async function generateDemoDeploy() {
  setStatus("Generating a demo deploy event for order-service…");
  try {
    const result = await api("/api/events/generate-demo-deploy", { method: "POST" });
    setStatus(`Deploy recorded: ${result.service} @ commit ${result.commit_sha}`);
  } catch (e) {
    setStatus(`Failed to generate deploy: ${e.message}`);
  }
  refreshOverview();
}

async function toggleInjection(kind, checked) {
  const params = new URLSearchParams({ enabled: checked });
  if (kind === "errors") params.set("rate", "0.3");
  if (kind === "load") params.set("multiplier", "6");
  setStatus(`${checked ? "Enabling" : "Disabling"} ${kind} injection…`);
  try {
    await api(`/api/failure-injection/${kind}?${params.toString()}`, { method: "POST" });
    setStatus(`${kind} injection ${checked ? "enabled" : "disabled"}.`);
  } catch (e) {
    setStatus(`Failed to toggle ${kind} injection: ${e.message}`);
  }
  refreshOverview();
}

$("btn-deploy").addEventListener("click", generateDemoDeploy);
$("btn-investigate").addEventListener("click", runInvestigation);
$("chk-latency").addEventListener("change", (e) => toggleInjection("latency", e.target.checked));
$("chk-errors").addEventListener("change", (e) => toggleInjection("errors", e.target.checked));
$("chk-load").addEventListener("change", (e) => toggleInjection("load", e.target.checked));

refreshOverview();
setInterval(refreshOverview, 15000);
