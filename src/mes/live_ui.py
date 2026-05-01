# -*- coding: utf-8 -*-
"""HTML shell for the live MES control room."""

LIVE_MES_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Semiconductor AI MES</title>
  <style>
    :root {
      --ink: #161616;
      --muted: #525252;
      --subtle: #6f6f6f;
      --canvas: #f4f4f4;
      --surface: #ffffff;
      --surface-alt: #f9f9f9;
      --border: #d0d0d0;
      --border-strong: #8d8d8d;
      --blue: #0f62fe;
      --blue-hover: #0043ce;
      --green: #24a148;
      --yellow: #f1c21b;
      --orange: #ff832b;
      --red: #da1e28;
      --purple: #8a3ffc;
    }

    * { box-sizing: border-box; }
    html {
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    body { margin: 0; min-height: 100vh; }
    button, select, input { font: inherit; }
    .shell { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
    .sidebar {
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 16px;
    }
    .brand { border-bottom: 1px solid var(--border); padding: 8px 4px 18px; }
    .brand strong { display: block; font-size: 18px; font-weight: 650; }
    .brand span { color: var(--muted); font-size: 12px; }
    .nav-label {
      color: var(--subtle);
      font-size: 11px;
      font-weight: 650;
      margin: 20px 4px 8px;
      text-transform: uppercase;
    }
    .nav-item {
      align-items: center;
      border-left: 3px solid transparent;
      color: var(--ink);
      display: flex;
      justify-content: space-between;
      min-height: 36px;
      padding: 8px 10px;
      text-decoration: none;
    }
    .nav-item.active {
      background: #edf5ff;
      border-left-color: var(--blue);
      color: var(--blue);
      font-weight: 650;
    }
    .workspace { min-width: 0; padding: 20px; }
    .topbar {
      align-items: center;
      display: flex;
      gap: 16px;
      justify-content: space-between;
      margin-bottom: 16px;
    }
    h1 { font-size: 22px; line-height: 1.2; margin: 0 0 6px; }
    .meta-row {
      align-items: center;
      color: var(--muted);
      display: flex;
      flex-wrap: wrap;
      font-size: 12px;
      gap: 8px;
    }
    .commands { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .button {
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: 4px;
      color: var(--ink);
      cursor: pointer;
      font-size: 13px;
      font-weight: 650;
      min-height: 36px;
      padding: 8px 12px;
    }
    .button.primary { background: var(--blue); border-color: var(--blue); color: #fff; }
    .button.primary:hover { background: var(--blue-hover); }
    .layout { display: grid; gap: 16px; }
    .kpis { display: grid; gap: 12px; grid-template-columns: repeat(6, 1fr); }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      min-width: 0;
    }
    .panel.active { border-color: var(--blue); }
    .panel-header {
      align-items: center;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      min-height: 44px;
      padding: 10px 12px;
    }
    .panel-header h2 { font-size: 15px; margin: 0; }
    .panel-header span { color: var(--muted); font-size: 12px; }
    .kpi { min-height: 104px; padding: 12px; }
    .kpi-label { color: var(--muted); font-size: 11px; font-weight: 650; text-transform: uppercase; }
    .kpi-value { font-size: 26px; font-variant-numeric: tabular-nums; font-weight: 650; margin-top: 12px; }
    .kpi-note { color: var(--subtle); font-size: 12px; margin-top: 8px; }
    .main-grid { display: grid; gap: 16px; grid-template-columns: 1.1fr .9fr; }
    .stage-grid { display: grid; gap: 12px; grid-template-columns: repeat(3, 1fr); padding: 12px; }
    .stage {
      border: 1px solid var(--border);
      border-radius: 6px;
      display: grid;
      gap: 12px;
      min-height: 188px;
      padding: 12px;
    }
    .stage.focus { background: #f6f2ff; border-color: var(--purple); }
    .stage-head { align-items: start; display: flex; justify-content: space-between; }
    .stage strong { display: block; font-size: 16px; }
    .stage small { color: var(--muted); display: block; margin-top: 3px; }
    .metric-grid { display: grid; gap: 8px; grid-template-columns: repeat(2, 1fr); }
    .metric { background: var(--surface-alt); border: 1px solid var(--border); border-radius: 4px; padding: 8px; }
    .metric span { color: var(--subtle); display: block; font-size: 11px; margin-bottom: 5px; }
    .metric b { font-variant-numeric: tabular-nums; }
    .status {
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 999px;
      display: inline-flex;
      font-size: 11px;
      font-weight: 650;
      gap: 6px;
      height: 22px;
      padding: 0 8px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .status:before { border-radius: 999px; content: ""; display: block; height: 7px; width: 7px; }
    .green { background: #defbe6; border-color: #a7f0ba; color: #0e6027; }
    .green:before { background: var(--green); }
    .yellow { background: #fcf4d6; border-color: #fddc69; color: #684e00; }
    .yellow:before { background: var(--yellow); }
    .blue { background: #edf5ff; border-color: #bae6ff; color: #0043ce; }
    .blue:before { background: var(--blue); }
    .purple { background: #f6f2ff; border-color: #e8daff; color: #6929c4; }
    .purple:before { background: var(--purple); }
    .red { background: #fff1f1; border-color: #ffb3b8; color: #a2191f; }
    .red:before { background: var(--red); }
    table { border-collapse: collapse; min-width: 760px; width: 100%; }
    th {
      background: var(--surface-alt);
      color: var(--subtle);
      font-size: 11px;
      height: 36px;
      text-align: left;
      text-transform: uppercase;
    }
    td, th { border-bottom: 1px solid var(--border); padding: 8px 10px; white-space: nowrap; }
    td { font-size: 13px; height: 44px; }
    .table-wrap { overflow-x: auto; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
    .chain, .events { display: grid; gap: 10px; padding: 12px; }
    .chain-node { border: 1px solid var(--border); border-left: 4px solid var(--purple); border-radius: 6px; padding: 10px; }
    .chain-node strong { display: block; font-size: 13px; margin-bottom: 6px; }
    .chain-node div { color: var(--muted); font-size: 12px; margin-top: 3px; }
    .event-row { border-bottom: 1px solid var(--border); display: grid; gap: 10px; grid-template-columns: 96px 1fr auto; padding: 10px 0; }
    .event-row:last-child { border-bottom: 0; }
    .event-row b { display: block; font-size: 13px; }
    .event-row span { color: var(--muted); font-size: 12px; }
    .split-grid { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }
    @media (max-width: 1200px) { .kpis { grid-template-columns: repeat(3, 1fr); } .main-grid, .split-grid { grid-template-columns: 1fr; } }
    @media (max-width: 900px) { .shell { grid-template-columns: 1fr; } .sidebar { border-bottom: 1px solid var(--border); border-right: 0; } .stage-grid { grid-template-columns: 1fr; } .topbar { align-items: stretch; flex-direction: column; } .commands { justify-content: flex-start; } }
    @media (max-width: 640px) { .workspace { padding: 12px; } .kpis { grid-template-columns: 1fr; } .event-row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <strong>Semiconductor AI MES</strong>
        <span>Live simulator line</span>
      </div>
      <div class="nav-label">Operate</div>
      <a class="nav-item active" href="#fab"><span>Fab Control</span><span id="nav-live">Live</span></a>
      <a class="nav-item" href="#chain"><span>Decision Chain</span><span id="nav-chain">-</span></a>
      <a class="nav-item" href="#equipment"><span>Equipment</span><span id="nav-eqp">-</span></a>
      <div class="nav-label">Trace</div>
      <a class="nav-item" href="#events"><span>Events</span><span id="nav-events">-</span></a>
    </aside>
    <main class="workspace" id="fab">
      <header class="topbar">
        <div>
          <h1>Fab Control Room</h1>
          <div class="meta-row">
            <span>sim_time: <code id="sim-time">0</code></span>
            <span>correlation_id: <code id="corr-id">-</code></span>
            <span class="status green" id="rule-gate">READY</span>
            <span class="status purple">RULE BASELINE</span>
          </div>
        </div>
        <div class="commands">
          <select id="speed" class="button">
            <option value="1">1 cycle</option>
            <option value="3" selected>3 cycles</option>
            <option value="8">8 cycles</option>
          </select>
          <button class="button primary" id="start">Start</button>
          <button class="button" id="stop">Stop</button>
          <button class="button" id="step">Run cycle</button>
          <button class="button" id="generate">Generate lot</button>
        </div>
      </header>
      <div class="layout">
        <section class="kpis">
          <div class="panel kpi"><div class="kpi-label">Total WIP</div><div class="kpi-value" id="kpi-wip">0</div><div class="kpi-note" id="kpi-wip-note">A/B/C</div></div>
          <div class="panel kpi"><div class="kpi-label">Completed</div><div class="kpi-value" id="kpi-completed">0</div><div class="kpi-note">packed wafers</div></div>
          <div class="panel kpi"><div class="kpi-label">Yield Proxy</div><div class="kpi-value" id="kpi-yield">1.00</div><div class="kpi-note">process pass ratio</div></div>
          <div class="panel kpi"><div class="kpi-label">Throughput</div><div class="kpi-value" id="kpi-throughput">0.00</div><div class="kpi-note">completed / time</div></div>
          <div class="panel kpi"><div class="kpi-label">Utilization</div><div class="kpi-value" id="kpi-util">0%</div><div class="kpi-note">busy equipment</div></div>
          <div class="panel kpi"><div class="kpi-label">Commands</div><div class="kpi-value" id="kpi-commands">0</div><div class="kpi-note">executed</div></div>
        </section>
        <section class="main-grid">
          <div class="panel active">
            <div class="panel-header"><h2>Stage Board</h2><span id="autoplay-state">stopped</span></div>
            <div class="stage-grid" id="stage-grid"></div>
          </div>
          <div class="panel" id="chain">
            <div class="panel-header"><h2>Decision Chain</h2><span id="chain-count">0 records</span></div>
            <div class="chain" id="chain-list"></div>
          </div>
        </section>
        <section class="split-grid" id="equipment">
          <div class="panel">
            <div class="panel-header"><h2>Equipment Matrix</h2><span id="equipment-count">0 tools</span></div>
            <div class="table-wrap">
              <table><thead><tr><th>Equipment</th><th>Stage</th><th>Status</th><th>Batch</th><th>Current UIDs</th><th>Finish</th></tr></thead><tbody id="equipment-body"></tbody></table>
            </div>
          </div>
          <div class="panel" id="events">
            <div class="panel-header"><h2>Event Timeline</h2><span id="event-count">0 events</span></div>
            <div class="events" id="event-list"></div>
          </div>
        </section>
      </div>
    </main>
  </div>
  <script>
    const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
    let running = false;

    const statusClass = (status) => {
      const s = String(status || "").toUpperCase();
      if (s.includes("PASS") || s === "IDLE" || s === "READY" || s === "EXECUTED") return "status green";
      if (s.includes("RUN") || s.includes("BUSY")) return "status blue";
      if (s.includes("REJECT") || s.includes("DOWN")) return "status red";
      return "status yellow";
    };

    async function postJSON(url, body) {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      return res.json();
    }

    async function refresh(stepCycles = 0) {
      const live = running
        ? await fetch(`/api/v2/simulation/autoplay/status?step_cycles=${stepCycles}`).then(r => r.json()).then(x => x.live)
        : await fetch("/api/v2/fab/live").then(r => r.json());
      render(live);
    }

    function render(live) {
      const k = live.kpis || {};
      const chain = live.active_chain || {};
      const corr = chain.correlation_id || "-";
      document.getElementById("sim-time").textContent = live.time ?? 0;
      document.getElementById("corr-id").textContent = corr;
      document.getElementById("nav-chain").textContent = corr === "-" ? "-" : "active";
      document.getElementById("autoplay-state").textContent = live.autoplay?.enabled ? "running" : "stopped";
      document.getElementById("kpi-wip").textContent = k.total_wip ?? 0;
      document.getElementById("kpi-wip-note").textContent = `A ${live.stages?.A?.total_wip ?? 0} / B ${live.stages?.B?.total_wip ?? 0} / C ${live.stages?.C?.total_wip ?? 0}`;
      document.getElementById("kpi-completed").textContent = k.completed ?? 0;
      document.getElementById("kpi-yield").textContent = fmt.format(k.yield_proxy ?? 1);
      document.getElementById("kpi-throughput").textContent = fmt.format(k.throughput ?? 0);
      document.getElementById("kpi-util").textContent = `${Math.round((k.equipment_utilization || 0) * 100)}%`;
      document.getElementById("kpi-commands").textContent = k.executed_commands ?? 0;
      const gate = document.getElementById("rule-gate");
      gate.textContent = chain.validation_status || "READY";
      gate.className = statusClass(gate.textContent);
      renderStages(live.stages || {});
      renderEquipment(live.equipment || []);
      renderChain(chain);
      renderEvents(live.recent_events || []);
    }

    function renderStages(stages) {
      const grid = document.getElementById("stage-grid");
      grid.innerHTML = ["A", "B", "C"].map(stage => {
        const s = stages[stage] || {};
        return `<article class="stage ${s.focus ? "focus" : ""}">
          <div class="stage-head"><div><strong>${stage}</strong><small>${s.label || ""}</small></div><span class="${statusClass(s.status || "READY")}">${s.status || "READY"}</span></div>
          <div class="metric-grid">
            <div class="metric"><span>Wait</span><b>${s.wait || 0}</b></div>
            <div class="metric"><span>Incoming</span><b>${s.incoming || 0}</b></div>
            <div class="metric"><span>Rework</span><b>${s.rework || 0}</b></div>
            <div class="metric"><span>Running</span><b>${s.running || 0}</b></div>
          </div>
        </article>`;
      }).join("");
    }

    function renderEquipment(items) {
      document.getElementById("equipment-count").textContent = `${items.length} tools`;
      document.getElementById("nav-eqp").textContent = String(items.length);
      document.getElementById("equipment-body").innerHTML = items.map(eq => `
        <tr>
          <td><code>${eq.equipment_id}</code></td><td>${eq.stage}</td>
          <td><span class="${statusClass(eq.status)}">${eq.status}</span></td>
          <td>${eq.batch_size || 1}</td><td><code>${(eq.current_batch_uids || []).join(", ") || "-"}</code></td>
          <td>${eq.finish_time ?? "-"}</td>
        </tr>`).join("");
    }

    function renderChain(chain) {
      const recs = chain.recommendations || [];
      document.getElementById("chain-count").textContent = `${recs.length} recommendations`;
      document.getElementById("chain-list").innerHTML = recs.map(r => `
        <article class="chain-node">
          <strong>${r.layer_id} · ${r.recommendation_type}</strong>
          <div>rec <code>${r.recommendation_id}</code></div>
          <div>parent <code>${r.parent_recommendation_id || "-"}</code></div>
          <div>feature <code>${r.feature_snapshot_id || "-"}</code></div>
          <div>status <span class="${statusClass(r.rule_validation_status)}">${r.rule_validation_status}</span></div>
        </article>`).join("") || "<span class='kpi-note'>No active chain</span>";
    }

    function renderEvents(events) {
      document.getElementById("event-count").textContent = `${events.length} events`;
      document.getElementById("nav-events").textContent = String(events.length);
      document.getElementById("event-list").innerHTML = events.map(e => `
        <div class="event-row">
          <span>${e.layer_id || e.actor_type || "SYSTEM"}</span>
          <div><b>${e.event_type}</b><span><code>${e.correlation_id}</code></span></div>
          <span class="status ${e.event_type?.includes("REJECT") ? "red" : "green"}">${e.actor_type || "SYSTEM"}</span>
        </div>`).join("") || "<span class='kpi-note'>No events</span>";
    }

    document.getElementById("start").onclick = async () => {
      running = true;
      await postJSON("/api/v2/simulation/autoplay/start", { target_stage: "AUTO", generate_every: 20, bootstrap_cycles: 1 });
      refresh(0);
    };
    document.getElementById("stop").onclick = async () => {
      running = false;
      await postJSON("/api/v2/simulation/autoplay/stop", {});
      refresh(0);
    };
    document.getElementById("step").onclick = async () => {
      await postJSON("/api/v2/harness/run-cycle", { target_stage: "AUTO" });
      refresh(0);
    };
    document.getElementById("generate").onclick = async () => {
      await postJSON("/api/v2/tasks/generate", {});
      refresh(0);
    };
    setInterval(() => refresh(running ? Number(document.getElementById("speed").value) : 0), 1000);
    refresh(0);
  </script>
</body>
</html>
"""

