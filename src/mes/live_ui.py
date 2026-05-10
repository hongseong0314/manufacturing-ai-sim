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
    .trace-grid { display: grid; gap: 10px; grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 12px; }
    .trace-card { border: 1px solid var(--border); border-radius: 6px; padding: 10px; }
    .trace-card strong { display: block; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; }
    .trace-card code, .trace-card span { color: var(--muted); font-size: 11px; }
    .candidate-list { display: grid; gap: 6px; margin-top: 8px; }
    .candidate-item { background: var(--surface-alt); border: 1px solid var(--border); border-radius: 4px; padding: 7px; }
    .event-row { border-bottom: 1px solid var(--border); display: grid; gap: 10px; grid-template-columns: 96px 1fr auto; padding: 10px 0; }
    .event-row:last-child { border-bottom: 0; }
    .event-row b { display: block; font-size: 13px; }
    .event-row span { color: var(--muted); font-size: 12px; }
    .split-grid { display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }
    .flow-gantt-grid { display: grid; gap: 16px; grid-template-columns: 1fr; }
    .flow-board {
      align-items: stretch;
      display: grid;
      gap: 10px;
      grid-template-columns: 1fr 28px 1fr 28px 1fr 28px .8fr;
      padding: 12px;
    }
    .flow-step {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      display: grid;
      gap: 10px;
      min-height: 136px;
      padding: 12px;
      text-align: left;
    }
    .flow-step.selected { border-color: var(--blue); box-shadow: inset 0 0 0 1px var(--blue); }
    .flow-step:focus { outline: 2px solid var(--blue); outline-offset: 2px; }
    .flow-step .flow-title { align-items: flex-start; display: flex; justify-content: space-between; }
    .flow-step strong { display: block; font-size: 15px; }
    .flow-step small { color: var(--muted); display: block; margin-top: 3px; }
    .flow-arrow {
      align-items: center;
      color: var(--blue);
      display: flex;
      font-size: 22px;
      font-weight: 650;
      justify-content: center;
    }
    .flow-complete {
      border: 1px solid var(--border);
      border-radius: 6px;
      display: grid;
      gap: 8px;
      min-height: 136px;
      padding: 12px;
    }
    .gantt-shell { padding: 12px; }
    .gantt-toolbar {
      align-items: center;
      display: flex;
      gap: 8px;
      justify-content: space-between;
      margin-bottom: 10px;
    }
    .legend { display: flex; flex-wrap: wrap; gap: 8px; }
    .legend-item { align-items: center; color: var(--muted); display: inline-flex; font-size: 12px; gap: 6px; }
    .legend-swatch { border-radius: 3px; display: inline-block; height: 10px; width: 18px; }
    .gantt-scroll { overflow-x: auto; }
    .gantt-table {
      display: grid;
      grid-template-columns: 172px minmax(760px, 1fr);
      min-width: 940px;
    }
    .gantt-label, .gantt-lane {
      border-bottom: 1px solid var(--border);
      min-height: 44px;
    }
    .gantt-label {
      align-items: center;
      background: var(--surface);
      color: var(--muted);
      display: flex;
      font-size: 12px;
      padding: 0 10px;
    }
    .gantt-label.buffer { background: #fff7ed; color: #9a520d; }
    .gantt-label strong { color: var(--ink); font-size: 12px; margin-right: 6px; }
    .gantt-label.buffer strong { color: #7a3f08; }
    .gantt-head { background: var(--surface-alt); color: var(--subtle); font-size: 11px; font-weight: 650; text-transform: uppercase; }
    .gantt-lane {
      background-image:
        linear-gradient(to right, rgba(208, 208, 208, .65) 1px, transparent 1px);
      background-size: 10% 100%;
      position: relative;
    }
    .gantt-tick {
      color: var(--subtle);
      font-size: 11px;
      position: absolute;
      top: 11px;
      transform: translateX(-50%);
    }
    .gantt-now {
      background: var(--red);
      bottom: 0;
      position: absolute;
      top: 0;
      width: 2px;
      z-index: 4;
    }
    .gantt-now:before {
      background: var(--red);
      border-radius: 999px;
      color: #fff;
      content: "now";
      font-size: 10px;
      left: -13px;
      padding: 1px 5px;
      position: absolute;
      top: -18px;
    }
    .gantt-bar {
      align-items: center;
      border: 1px solid transparent;
      border-radius: 4px;
      color: #fff;
      display: flex;
      font-size: 11px;
      min-width: 8px;
      overflow: hidden;
      padding: 0 6px;
      position: absolute;
      text-overflow: ellipsis;
      white-space: nowrap;
      z-index: 2;
    }
    .gantt-bar.active { background: var(--blue); }
    .gantt-bar.completed { background: var(--green); }
    .gantt-bar.planned { background: #edf5ff; border-color: var(--blue); color: var(--blue); }
    .gantt-bar.rework, .gantt-bar.rework_active, .gantt-bar.planned_rework {
      background: repeating-linear-gradient(135deg, #da1e28 0 7px, #fa4d56 7px 14px);
      color: #fff;
    }
    .gantt-bar.pack { background: var(--green); border-color: rgba(22, 125, 73, .35); }
    .stage-detail-grid { display: grid; gap: 16px; grid-template-columns: 1.15fr .85fr; }
    .schedule-table { min-width: 640px; }
    .progress-track {
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: 999px;
      height: 8px;
      overflow: hidden;
      width: 96px;
    }
    .progress-fill { background: var(--blue); height: 100%; }
    .header-actions { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; }
    .link-button {
      background: transparent;
      border: 0;
      color: var(--blue);
      cursor: pointer;
      font: inherit;
      font-weight: 650;
      padding: 0;
      text-align: left;
    }
    .link-button:hover { color: var(--blue-hover); text-decoration: underline; }
    tr.selectable { cursor: pointer; }
    tr.selectable:hover td { background: #edf5ff; }
    .machine-dashboard { scroll-margin-top: 12px; }
    .machine-content { display: grid; gap: 16px; padding: 12px; }
    .machine-kpi-grid { display: grid; gap: 8px; grid-template-columns: repeat(6, 1fr); }
    .machine-detail-grid { display: grid; gap: 16px; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .65fr); }
    .machine-chart { overflow-x: auto; }
    .machine-chart svg { display: block; min-width: 760px; width: 100%; }
    .chart-axis { stroke: var(--border-strong); stroke-width: 1; }
    .chart-grid { stroke: var(--border); stroke-width: 1; }
    .chart-line { fill: none; stroke: var(--blue); stroke-width: 2.5; }
    .target-band { fill: #defbe6; opacity: .75; }
    .target-line { stroke: var(--green); stroke-dasharray: 4 4; stroke-width: 1.2; }
    .chart-point { cursor: pointer; fill: var(--surface); stroke: var(--blue); stroke-width: 2.5; }
    .chart-point.pass { fill: var(--green); stroke: var(--green); }
    .chart-point.fail { fill: var(--red); stroke: var(--red); }
    .chart-point.selected { fill: var(--blue); stroke: var(--ink); stroke-width: 3; }
    .chart-text { fill: var(--subtle); font-size: 11px; }
    .point-detail { border-left: 4px solid var(--blue); display: grid; gap: 10px; padding: 4px 0 4px 12px; }
    .point-detail strong { display: block; font-size: 14px; }
    .point-detail dl { display: grid; gap: 8px; grid-template-columns: 120px 1fr; margin: 0; }
    .point-detail dt { color: var(--subtle); font-size: 11px; text-transform: uppercase; }
    .point-detail dd { font-size: 13px; margin: 0; min-width: 0; overflow-wrap: anywhere; }
    .empty-state { color: var(--muted); padding: 20px; }
    @media (max-width: 1200px) { .kpis { grid-template-columns: repeat(3, 1fr); } .main-grid, .split-grid { grid-template-columns: 1fr; } }
    @media (max-width: 1200px) { .stage-detail-grid, .machine-detail-grid { grid-template-columns: 1fr; } .machine-kpi-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 900px) { .shell { grid-template-columns: 1fr; } .sidebar { border-bottom: 1px solid var(--border); border-right: 0; } .stage-grid, .flow-board { grid-template-columns: 1fr; } .flow-arrow { display: none; } .topbar { align-items: stretch; flex-direction: column; } .commands { justify-content: flex-start; } }
    @media (max-width: 640px) { .workspace { padding: 12px; } .kpis, .machine-kpi-grid { grid-template-columns: 1fr; } .event-row { grid-template-columns: 1fr; } }
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
      <a class="nav-item" href="#gantt"><span>Flow & Gantt</span><span id="nav-gantt">-</span></a>
      <a class="nav-item" href="#chain"><span>Decision Chain</span><span id="nav-chain">-</span></a>
      <a class="nav-item" href="#equipment"><span>Equipment</span><span id="nav-eqp">-</span></a>
      <a class="nav-item" href="#machine"><span>Machine Detail</span><span id="nav-machine">-</span></a>
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
          <button class="button" id="reset">Reset</button>
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
        <section class="flow-gantt-grid" id="gantt">
          <div class="panel">
            <div class="panel-header"><h2>Process Flow</h2><span id="flow-state">A → B → C</span></div>
            <div class="flow-board" id="flow-board"></div>
          </div>
          <div class="panel">
            <div class="panel-header"><h2>Global Gantt</h2><span id="gantt-window">t=0</span></div>
            <div class="gantt-shell">
              <div class="gantt-toolbar">
                <div class="legend">
                  <span class="legend-item"><i class="legend-swatch" style="background: var(--blue)"></i>Running</span>
                  <span class="legend-item"><i class="legend-swatch" style="background: var(--green)"></i>Finished</span>
                  <span class="legend-item"><i class="legend-swatch" style="background: #edf5ff; border: 1px solid var(--blue)"></i>Next eligible</span>
                  <span class="legend-item"><i class="legend-swatch" style="background: var(--red)"></i>Rework</span>
                </div>
                <span class="kpi-note">current time marker is red</span>
              </div>
              <div id="global-gantt"></div>
            </div>
          </div>
          <div class="panel">
            <div class="panel-header"><h2>Stage Drilldown</h2><span id="stage-detail-title">Stage A</span></div>
            <div class="stage-detail-grid">
              <div class="gantt-shell" id="stage-gantt"></div>
              <div class="table-wrap">
                <table class="schedule-table">
                  <thead><tr><th>Equipment</th><th>Status</th><th>Task UIDs</th><th>Window</th><th>Progress</th></tr></thead>
                  <tbody id="schedule-body"></tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
        <section class="main-grid">
          <div class="panel active">
            <div class="panel-header"><h2>Stage Board</h2><span id="autoplay-state">stopped</span></div>
            <div class="stage-grid" id="stage-grid"></div>
          </div>
          <div class="panel" id="chain">
            <div class="panel-header"><h2>Decision Chain</h2><span id="chain-count">0 records</span></div>
            <div class="trace-grid" id="chain-trace"></div>
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
        <section class="panel machine-dashboard" id="machine">
          <div class="panel-header">
            <h2>Machine Detail</h2>
            <div class="header-actions">
              <span id="machine-subtitle">Select an A/B/C machine</span>
              <button class="button" id="machine-back" type="button">Back to equipment</button>
            </div>
          </div>
          <div class="empty-state" id="machine-empty">
            Equipment rows open APC quality trends for A/B and packing composition quality for C.
          </div>
          <div class="machine-content" id="machine-content" hidden>
            <div class="machine-kpi-grid" id="machine-kpis"></div>
            <div class="machine-detail-grid">
              <div>
                <div class="panel-header"><h2>Quality Trend</h2><span id="machine-axis">step × quality</span></div>
                <div class="machine-chart" id="quality-chart"></div>
              </div>
              <div>
                <div class="panel-header"><h2>Point Snapshot</h2><span id="point-title">latest</span></div>
                <div class="point-detail" id="point-detail"></div>
              </div>
            </div>
            <div class="table-wrap">
              <table>
                <thead><tr><th>Step</th><th>Tasks</th><th>Quality</th><th>Recipe</th><th>Material</th><th>Result</th></tr></thead>
                <tbody id="machine-history-body"></tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
  <script>
    const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
    let running = false;
    let selectedStage = "A";
    let selectedMachineId = null;
    let selectedMachineDetail = null;
    let selectedPointId = null;
    let lastGantt = null;
    let lastLive = null;

    const statusClass = (status) => {
      const s = String(status || "").toUpperCase();
      if (s.includes("REWORK") || s.includes("REJECT") || s.includes("DOWN")) return "status red";
      if (s.includes("PLAN") || s.includes("PENDING")) return "status yellow";
      if (s.includes("PASS") || s === "IDLE" || s === "READY" || s === "EXECUTED") return "status green";
      if (s.includes("RUN") || s.includes("BUSY") || s.includes("ACTIVE")) return "status blue";
      return "status yellow";
    };

    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    const escapeText = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");

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
      const gantt = await fetch("/api/v2/gantt").then(r => r.json());
      render(live, gantt);
      if (selectedMachineId) await loadMachineDetail(selectedMachineId, false);
    }

    function render(live, gantt) {
      lastLive = live;
      lastGantt = gantt;
      const k = live.kpis || {};
      const chain = live.active_chain || {};
      const corr = chain.correlation_id || "-";
      document.getElementById("sim-time").textContent = live.time ?? 0;
      document.getElementById("corr-id").textContent = corr;
      document.getElementById("nav-chain").textContent = corr === "-" ? "-" : "active";
      document.getElementById("nav-gantt").textContent = `${gantt?.bars?.length || 0}`;
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
      renderGantt(gantt || {}, live);
      updateNavState();
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
      document.getElementById("equipment-body").innerHTML = items.map(eq => {
        const detailEnabled = ["A", "B", "C"].includes(String(eq.stage || "").toUpperCase());
        const equipmentCell = detailEnabled
          ? `<button class="link-button machine-link" type="button" data-equipment-id="${escapeText(eq.equipment_id)}"><code>${escapeText(eq.equipment_id)}</code></button>`
          : `<code>${escapeText(eq.equipment_id)}</code>`;
        return `
        <tr class="${detailEnabled ? "selectable" : ""}" data-equipment-id="${escapeText(eq.equipment_id)}">
          <td>${equipmentCell}</td><td>${eq.stage}</td>
          <td><span class="${statusClass(eq.status)}">${eq.status}</span></td>
          <td>${eq.batch_size || 1}</td><td><code>${(eq.current_batch_uids || []).join(", ") || "-"}</code></td>
          <td>${eq.finish_time ?? "-"}</td>
        </tr>`;
      }).join("");
      document.querySelectorAll(".machine-link").forEach(button => {
        button.onclick = (event) => {
          event.stopPropagation();
          openMachineDetail(button.dataset.equipmentId);
        };
      });
      document.querySelectorAll("tr.selectable[data-equipment-id]").forEach(row => {
        row.onclick = () => openMachineDetail(row.dataset.equipmentId);
      });
    }

    async function openMachineDetail(equipmentId) {
      if (!equipmentId) return;
      selectedMachineId = equipmentId;
      selectedPointId = null;
      location.hash = "machine";
      await loadMachineDetail(equipmentId, true);
    }

    async function loadMachineDetail(equipmentId, showLoading) {
      const empty = document.getElementById("machine-empty");
      const content = document.getElementById("machine-content");
      if (showLoading) {
        empty.hidden = false;
        content.hidden = true;
        empty.textContent = `Loading ${equipmentId} detail...`;
      }
      try {
        const detail = await fetch(`/api/v2/equipment/${equipmentId}/detail`).then(r => {
          if (!r.ok) throw new Error("detail unavailable");
          return r.json();
        });
        selectedMachineDetail = detail;
        renderMachineDetail(detail);
      } catch (error) {
        selectedMachineDetail = null;
        document.getElementById("nav-machine").textContent = "-";
        document.getElementById("machine-subtitle").textContent = "Machine detail unavailable";
        empty.hidden = false;
        content.hidden = true;
        empty.textContent = "Machine detail is available after the equipment exists in the live simulator state.";
      }
    }

    function renderMachineDetail(detail) {
      const empty = document.getElementById("machine-empty");
      const content = document.getElementById("machine-content");
      empty.hidden = true;
      content.hidden = false;
      document.getElementById("nav-machine").textContent = detail.equipment_id;
      document.getElementById("machine-subtitle").textContent =
        `${detail.equipment_id} · ${detail.process_label} · ${detail.status}`;
      document.getElementById("machine-axis").textContent =
        `${detail.apc?.quality_axis?.x || "step"} × ${detail.apc?.quality_axis?.y || "quality"}`;
      renderMachineKpis(detail);
      renderQualityChart(detail);
      renderMachineHistory(detail);
    }

    function renderMachineKpis(detail) {
      const k = detail.kpis || {};
      const material = detail.material_state || {};
      if (detail.stage === "C") {
        const currentBatch = formatTaskList(detail.current_batch_uids || []) || "-";
        const items = [
          ["Status", detail.status || "-", `finish t=${detail.finish_time ?? "-"}`],
          ["Pack Quality", formatMetric(k.avg_quality), `${k.packs_completed || 0} packs`],
          ["Latest", formatMetric(k.latest_quality), "composition quality"],
          ["Compatibility", formatMetric(k.avg_compatibility), "same material/color"],
          ["Packed", k.packed_tasks ?? 0, `active ${k.active_wip || 0}`],
          [material.primary_label || "Material match", material.primary_value ?? 0, material.state_label || "-"],
        ];
        document.getElementById("machine-kpis").innerHTML = items.map(item => `
          <div class="metric">
            <span>${escapeText(item[0])}</span>
            <b>${escapeText(item[1])}</b>
            <div class="kpi-note">${escapeText(item[2])}</div>
          </div>`).join("");
        if (currentBatch !== "-") {
          document.getElementById("machine-subtitle").textContent += ` · running ${currentBatch}`;
        }
        return;
      }
      const yieldPct = `${Math.round((k.yield_rate ?? 1) * 100)}%`;
      const currentBatch = formatTaskList(detail.current_batch_uids || []) || "-";
      const items = [
        ["Status", detail.status || "-", `finish t=${detail.finish_time ?? "-"}`],
        ["Yield", yieldPct, `${k.passed || 0} pass / ${k.failed || 0} fail`],
        ["Avg QA", formatMetric(k.avg_quality), `${k.sample_count || 0} samples`],
        ["Latest QA", formatMetric(k.latest_quality), "last completed batch"],
        ["Processed", k.processed ?? 0, `active ${k.active_wip || 0}`],
        [material.primary_label || "Material", material.primary_value ?? 0, material.state_label || "-"],
      ];
      document.getElementById("machine-kpis").innerHTML = items.map(item => `
        <div class="metric">
          <span>${escapeText(item[0])}</span>
          <b>${escapeText(item[1])}</b>
          <div class="kpi-note">${escapeText(item[2])}</div>
        </div>`).join("");
      if (currentBatch !== "-") {
        document.getElementById("machine-subtitle").textContent += ` · running ${currentBatch}`;
      }
    }

    function renderQualityChart(detail) {
      const series = detail.quality_series || [];
      const target = document.getElementById("quality-chart");
      if (!series.length) {
        target.innerHTML = `<div class='empty-state'>No completed ${detail.stage === "C" ? "C packs" : "A/B quality samples"} yet.</div>`;
        renderPointDetail(null, detail);
        return;
      }

      const width = 860;
      const height = 320;
      const margin = { left: 54, right: 22, top: 24, bottom: 42 };
      const plotW = width - margin.left - margin.right;
      const plotH = height - margin.top - margin.bottom;
      const xs = series.map(p => Number(p.step ?? p.time ?? 0));
      const ys = series.map(p => Number(p.quality ?? 0));
      const windows = series.map(p => p.target_window).filter(Boolean);
      windows.forEach(window => {
        ys.push(Number(window[0]));
        ys.push(Number(window[1]));
      });
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const xSpan = Math.max(1, maxX - minX);
      const minYRaw = Math.min(...ys);
      const maxYRaw = Math.max(...ys);
      const yPad = Math.max(1, (maxYRaw - minYRaw) * 0.18);
      const minY = minYRaw - yPad;
      const maxY = maxYRaw + yPad;
      const ySpan = Math.max(1, maxY - minY);
      const x = (value) => margin.left + ((Number(value) - minX) / xSpan) * plotW;
      const y = (value) => margin.top + (1 - ((Number(value) - minY) / ySpan)) * plotH;
      const path = series.map((p, index) =>
        `${index === 0 ? "M" : "L"} ${x(p.step ?? p.time)} ${y(p.quality)}`
      ).join(" ");
      const xTicks = buildTicks(minX, maxX, 5);
      const yTicks = buildTicks(minY, maxY, 5);
      const selected = selectedPointId && series.find(p => p.point_id === selectedPointId)
        ? selectedPointId
        : series[series.length - 1].point_id;
      selectedPointId = selected;
      const latestWindow = detail.stage === "C" ? null : series[series.length - 1].target_window;
      const targetBand = latestWindow
        ? `<rect class="target-band" x="${margin.left}" y="${y(latestWindow[1])}" width="${plotW}" height="${Math.max(1, y(latestWindow[0]) - y(latestWindow[1]))}"></rect>
           <line class="target-line" x1="${margin.left}" x2="${width - margin.right}" y1="${y(latestWindow[0])}" y2="${y(latestWindow[0])}"></line>
           <line class="target-line" x1="${margin.left}" x2="${width - margin.right}" y1="${y(latestWindow[1])}" y2="${y(latestWindow[1])}"></line>`
        : "";
      target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeText(detail.equipment_id)} quality trend">
        ${targetBand}
        ${xTicks.map(tick => `<line class="chart-grid" x1="${x(tick)}" x2="${x(tick)}" y1="${margin.top}" y2="${height - margin.bottom}"></line><text class="chart-text" x="${x(tick)}" y="${height - 16}" text-anchor="middle">${Math.round(tick)}</text>`).join("")}
        ${yTicks.map(tick => `<line class="chart-grid" x1="${margin.left}" x2="${width - margin.right}" y1="${y(tick)}" y2="${y(tick)}"></line><text class="chart-text" x="${margin.left - 8}" y="${y(tick) + 4}" text-anchor="end">${fmt.format(tick)}</text>`).join("")}
        <line class="chart-axis" x1="${margin.left}" x2="${width - margin.right}" y1="${height - margin.bottom}" y2="${height - margin.bottom}"></line>
        <line class="chart-axis" x1="${margin.left}" x2="${margin.left}" y1="${margin.top}" y2="${height - margin.bottom}"></line>
        <path class="chart-line" d="${path}"></path>
        ${series.map(point => {
          const cls = point.point_id === selected ? "selected" : (point.passed ? "pass" : "fail");
          const title = detail.stage === "C"
            ? `${point.equipment_id} pack ${point.pack_id} quality=${formatMetric(point.quality)} ${point.composition_label || ""}`
            : `${point.equipment_id} t=${point.time} qa=${formatMetric(point.quality)} ${point.recipe_label} ${point.material_state?.state_label || ""}`;
          return `<circle class="chart-point ${cls}" cx="${x(point.step ?? point.time)}" cy="${y(point.quality)}" r="6" data-point-id="${escapeText(point.point_id)}"><title>${escapeText(title)}</title></circle>`;
        }).join("")}
        <text class="chart-text" x="${width / 2}" y="${height - 2}" text-anchor="middle">${detail.stage === "C" ? "pack" : "step"}</text>
        <text class="chart-text" x="16" y="${height / 2}" transform="rotate(-90 16 ${height / 2})" text-anchor="middle">${detail.stage === "C" ? "composition quality" : "quality"}</text>
      </svg>`;
      target.querySelectorAll(".chart-point").forEach(point => {
        point.onclick = () => {
          selectedPointId = point.dataset.pointId;
          renderQualityChart(detail);
        };
      });
      renderPointDetail(series.find(p => p.point_id === selectedPointId) || series[series.length - 1], detail);
    }

    function renderPointDetail(point, detail) {
      const target = document.getElementById("point-detail");
      if (!point) {
        document.getElementById("point-title").textContent = "empty";
        target.innerHTML = "<span class='kpi-note'>Run the line until this machine completes a task.</span>";
        return;
      }
      if (detail.stage === "C") {
        const materialCounts = formatCounts(point.material_counts || {});
        const colorCounts = formatCounts(point.color_counts || {});
        document.getElementById("point-title").textContent = `pack ${point.pack_id} · ${formatTaskList(point.task_uids)}`;
        target.innerHTML = `
          <strong>${escapeText(detail.equipment_id)} pack quality ${escapeText(formatMetric(point.quality))}</strong>
          <dl>
            <dt>Tasks</dt><dd><code>${escapeText(formatTaskList(point.task_uids) || "-")}</code></dd>
            <dt>Material</dt><dd>${escapeText(materialCounts || "-")}</dd>
            <dt>Color</dt><dd>${escapeText(colorCounts || "-")}</dd>
            <dt>Dominant</dt><dd>${escapeText(point.composition_label || "-")}</dd>
            <dt>Match</dt><dd>${escapeText(`${point.material_match_count || 0} material / ${point.color_match_count || 0} color`)}</dd>
            <dt>Wait</dt><dd>${escapeText(formatMetric(point.avg_wait_time))}</dd>
          </dl>`;
        return;
      }
      document.getElementById("point-title").textContent = `t=${point.time} · ${formatTaskList(point.task_uids)}`;
      target.innerHTML = `
        <strong>${escapeText(detail.equipment_id)} quality ${escapeText(formatMetric(point.quality))}</strong>
        <dl>
          <dt>Tasks</dt><dd><code>${escapeText(formatTaskList(point.task_uids) || "-")}</code></dd>
          <dt>Recipe</dt><dd>${escapeText(point.recipe_label || "-")}</dd>
          <dt>Material</dt><dd>${escapeText(point.material_state?.state_label || "-")}</dd>
          <dt>Target</dt><dd>${escapeText(formatTargetWindow(point.target_window))}</dd>
          <dt>Samples</dt><dd>${escapeText((point.quality_values || []).map(formatMetric).join(", ") || "-")}</dd>
          <dt>Result</dt><dd><span class="${statusClass(point.passed ? "PASS" : "FAIL")}">${point.passed ? "PASS" : "FAIL"}</span></dd>
        </dl>`;
    }

    function renderMachineHistory(detail) {
      const rows = [...(detail.quality_series || [])].reverse().slice(0, 18);
      document.getElementById("machine-history-body").innerHTML = rows.map(point => `
        <tr>
          <td>t=${point.time}</td>
          <td><code>${escapeText(formatTaskList(point.task_uids) || "-")}</code></td>
          <td>${escapeText(formatMetric(point.quality))}</td>
          <td>${escapeText(detail.stage === "C" ? `P${point.pack_id}` : (point.recipe_label || "-"))}</td>
          <td>${escapeText(detail.stage === "C" ? (point.composition_label || "-") : (point.material_state?.state_label || "-"))}</td>
          <td><span class="${statusClass(point.passed ? "PASS" : "FAIL")}">${point.passed ? "PASS" : "FAIL"}</span></td>
        </tr>`).join("") || "<tr><td colspan='6'>No completed samples</td></tr>";
    }

    function renderChain(chain) {
      const recs = chain.recommendations || [];
      renderTraceability(chain.traceability || {});
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

    function renderTraceability(trace) {
      const budgets = trace.dispatch_budgets || {};
      const selected = trace.selected_candidates || [];
      const annotations = trace.l2_annotations || [];
      const budgetText = ["A", "B", "C"]
        .map(stage => `${stage}:${budgets[stage] || 0}`)
        .join(" / ");
      const candidateRows = selected.slice(0, 4).map(candidate => {
        const group = candidate.group_key || {};
        const annotation = candidate.l2_annotation || {};
        return `<div class="candidate-item">
          <code>${escapeText(candidate.candidate_id || "-")}</code>
          <span>${escapeText(candidate.stage || "-")} · ${escapeText(group.customer_id || "-")} · score ${escapeText(formatMetric(candidate.upper_score ?? candidate.local_score))}</span>
          <span>L2 ${escapeText(annotation.quality_risk || annotation.recipe_id || "-")}</span>
        </div>`;
      }).join("");
      document.getElementById("chain-trace").innerHTML = `
        <div class="trace-card">
          <strong>Budget Plan</strong>
          <code>${escapeText(budgetText)}</code>
          <span>L4 ${escapeText(trace.l4_policy_id || "-")}</span>
          <span>L3 ${escapeText(trace.l3_policy_id || "-")}</span>
          <span>max ${escapeText(trace.selected_candidate_ids?.length || 0)} commands</span>
        </div>
        <div class="trace-card">
          <strong>Candidate Portfolio</strong>
          <code>${escapeText(trace.candidate_count || 0)} candidates</code>
          <div class="candidate-list">${candidateRows || "<span>No selected candidates</span>"}</div>
        </div>
        <div class="trace-card">
          <strong>L2 Annotations</strong>
          <code>${escapeText(annotations.length)} annotations</code>
          <span>selected ${escapeText(trace.selected_candidate_id || "-")}</span>
        </div>`;
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

    function renderGantt(gantt, live) {
      renderFlow(gantt.flow || [], live);
      document.getElementById("gantt-window").textContent =
        `t=${gantt.horizon?.start ?? 0} → ${gantt.horizon?.end ?? 0}`;
      renderTimeline(
        document.getElementById("global-gantt"),
        gantt.rows || [],
        gantt.bars || [],
        gantt.horizon || { start: 0, end: 12, span: 12, ticks: [0, 3, 6, 9, 12] },
        gantt.time || 0
      );
      renderStageDetail(gantt);
    }

    function renderFlow(flow, live) {
      const byStage = Object.fromEntries(flow.map(item => [item.stage, item]));
      const completed = live?.kpis?.completed ?? 0;
      const parts = ["A", "B", "C"].map(stage => flowStep(stage, byStage[stage] || {}));
      document.getElementById("flow-board").innerHTML = `
        ${parts[0]}<div class="flow-arrow">→</div>
        ${parts[1]}<div class="flow-arrow">→</div>
        ${parts[2]}<div class="flow-arrow">→</div>
        <div class="flow-complete">
          <div><strong>Completed</strong><small>finished wafers</small></div>
          <div class="metric-grid">
            <div class="metric"><span>Total</span><b>${completed}</b></div>
            <div class="metric"><span>Commands</span><b>${live?.kpis?.executed_commands ?? 0}</b></div>
          </div>
          <span class="status green">Closed</span>
        </div>`;
      document.querySelectorAll(".flow-step").forEach(button => {
        button.onclick = () => {
          selectedStage = button.dataset.stage;
          renderGantt(lastGantt || {}, lastLive || {});
          location.hash = "gantt";
        };
      });
    }

    function flowStep(stage, item) {
      const util = Math.round((item.utilization || 0) * 100);
      return `<button class="flow-step ${selectedStage === stage ? "selected" : ""}" data-stage="${stage}" type="button">
        <div class="flow-title">
          <div><strong>${stage} · ${escapeText(item.label || "")}</strong><small>${item.equipment_count || 0} tools</small></div>
          <span class="${statusClass(item.status || "READY")}">${item.status || "READY"}</span>
        </div>
        <div class="metric-grid">
          <div class="metric"><span>WIP</span><b>${item.wip || 0}</b></div>
          <div class="metric"><span>Util</span><b>${util}%</b></div>
          <div class="metric"><span>Run/Idle</span><b>${item.running || 0}/${item.idle || 0}</b></div>
          <div class="metric"><span>Rework</span><b>${item.rework || 0}</b></div>
        </div>
      </button>`;
    }

    function renderTimeline(target, rows, bars, horizon, now) {
      const span = Math.max(1, (horizon.end || 1) - (horizon.start || 0));
      const leftPct = (value) => clamp(((value - horizon.start) / span) * 100, 0, 100);
      const ticks = (horizon.ticks || []).map(tick =>
        `<span class="gantt-tick" style="left:${leftPct(tick)}%">${tick}</span>`
      ).join("");
      const nowLine = `<span class="gantt-now" style="left:${leftPct(now)}%"></span>`;
      const barsByRow = {};
      bars.forEach(bar => {
        (barsByRow[bar.row_id] ||= []).push(bar);
      });
      target.innerHTML = `<div class="gantt-scroll"><div class="gantt-table">
        <div class="gantt-label gantt-head">Resource</div>
        <div class="gantt-lane gantt-head">${ticks}${nowLine}</div>
        ${rows.map(row => {
          const rowBars = (barsByRow[row.row_id] || []).map(bar => barHtml(bar, horizon)).join("");
          const labelClass = row.row_type === "buffer" ? "gantt-label buffer" : "gantt-label";
          const rowName = row.label || row.machine_id;
          const rowStage = row.display_stage || row.stage;
          return `<div class="${labelClass}"><strong>${escapeText(rowName)}</strong><span>${escapeText(rowStage)}</span></div>
            <div class="gantt-lane">${nowLine}${rowBars}</div>`;
        }).join("")}
      </div></div>`;
      attachGanttBarHandlers(target);
    }

    function barHtml(bar, horizon) {
      const span = Math.max(1, (horizon.end || 1) - (horizon.start || 0));
      const visibleStart = Math.max(Number(bar.start || 0), Number(horizon.start || 0));
      const visibleEnd = Math.min(Number(bar.end || 0), Number(horizon.end || 0));
      const left = clamp(((visibleStart - horizon.start) / span) * 100, 0, 100);
      const rawWidth = Math.max(0, ((visibleEnd - visibleStart) / span) * 100);
      const width = clamp(rawWidth, 2.2, 100 - left);
      const cls = barVisualClass(bar);
      const uids = formatTaskList(bar.task_uids || []);
      const batchUids = formatTaskList(bar.batch_task_uids || bar.task_uids || []);
      const stackSize = Math.max(1, Number(bar.stack_size || 1));
      const stackIndex = Math.min(stackSize - 1, Math.max(0, Number(bar.stack_index || 0)));
      const gap = stackSize > 1 ? 2 : 0;
      const stackArea = 32;
      const height = stackSize > 1 ? Math.max(7, Math.floor((stackArea - gap * (stackSize - 1)) / stackSize)) : 22;
      const top = stackSize > 1 ? 6 + stackIndex * (height + gap) : 10;
      const batchLabel = bar.batch_id !== null && bar.batch_id !== undefined ? ` batch=${bar.batch_id}` : "";
      const title = `${bar.machine_id} t=${bar.start}→${bar.end}${batchLabel} tasks=${batchUids}`;
      return `<span class="gantt-bar ${cls} selectable-gantt-bar" data-machine-id="${escapeText(bar.machine_id)}" data-stage="${escapeText(bar.stage)}" data-task-uids="${escapeText((bar.task_uids || []).join(","))}" data-batch-uids="${escapeText((bar.batch_task_uids || bar.task_uids || []).join(","))}" style="left:${left}%;width:${width}%;top:${top}px;height:${height}px;" title="${escapeText(title)}">${escapeText(bar.label || uids || bar.status)}</span>`;
    }

    function attachGanttBarHandlers(target) {
      target.querySelectorAll(".selectable-gantt-bar[data-machine-id]").forEach(bar => {
        bar.onclick = () => openMachineDetail(bar.dataset.machineId);
      });
    }

    function barVisualClass(bar) {
      const status = String(bar.status || "planned").toLowerCase();
      const taskType = String(bar.task_type || "").toLowerCase();
      if (taskType === "pack") return "pack";
      if (status.includes("rework")) return status;
      if (status.includes("active")) return "active";
      if (status.includes("completed")) return "completed";
      return "planned";
    }

    function renderStageDetail(gantt) {
      const view = gantt.stage_views?.[selectedStage] || { rows: [], bars: [] };
      document.getElementById("stage-detail-title").textContent =
        `Stage ${selectedStage} · ${view.bar_count || 0} bars`;
      renderTimeline(
        document.getElementById("stage-gantt"),
        view.rows || [],
        view.bars || [],
        gantt.horizon || { start: 0, end: 12, span: 12, ticks: [0, 3, 6, 9, 12] },
        gantt.time || 0
      );
      renderScheduleTable(view.bars || [], gantt.time || 0);
    }

    function renderScheduleTable(bars, now) {
      const rank = { active: 0, rework_active: 0, planned: 1, planned_rework: 1, completed: 2, rework: 2 };
      const sorted = [...bars].sort((a, b) =>
        (rank[a.status] ?? 3) - (rank[b.status] ?? 3) || a.start - b.start
      ).slice(0, 18);
      document.getElementById("schedule-body").innerHTML = sorted.map(bar => {
        const progress = progressPct(bar, now);
        return `<tr>
          <td><code>${escapeText(bar.machine_id)}</code></td>
          <td><span class="${statusClass(bar.status)}">${escapeText(labelStatus(bar.status))}</span></td>
          <td><code>${escapeText(formatTaskList(bar.batch_task_uids || bar.task_uids || []) || "-")}</code></td>
          <td>t=${bar.start}→${bar.end}</td>
          <td><div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div></td>
        </tr>`;
      }).join("") || "<tr><td colspan='5'>No stage schedule</td></tr>";
    }

    function progressPct(bar, now) {
      if (now <= bar.start) return 0;
      if (now >= bar.end) return 100;
      return Math.round(((now - bar.start) / Math.max(1, bar.end - bar.start)) * 100);
    }

    function labelStatus(status) {
      const s = String(status || "planned");
      if (s === "planned") return "NEXT";
      if (s === "planned_rework") return "NEXT REWORK";
      if (s === "rework_active") return "REWORK RUN";
      return s.toUpperCase();
    }

    function formatTaskList(uids) {
      if (!Array.isArray(uids) || !uids.length) return "";
      return uids.map(uid => `T${uid}`).join(", ");
    }

    function formatMetric(value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
      return fmt.format(Number(value));
    }

    function formatCounts(counts) {
      return Object.entries(counts || {})
        .map(([key, value]) => `${key}:${value}`)
        .join(" / ");
    }

    function formatTargetWindow(window) {
      if (!Array.isArray(window) || window.length < 2) return "-";
      return `${formatMetric(window[0])} – ${formatMetric(window[1])}`;
    }

    function buildTicks(minValue, maxValue, count) {
      const span = Math.max(1, Number(maxValue) - Number(minValue));
      const steps = Math.max(1, Number(count) - 1);
      return Array.from({ length: steps + 1 }, (_, index) =>
        Number(minValue) + (span * index) / steps
      );
    }

    function updateNavState() {
      const hash = location.hash || "#fab";
      document.querySelectorAll(".nav-item").forEach(item => {
        item.classList.toggle("active", item.getAttribute("href") === hash);
      });
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
    document.getElementById("reset").onclick = async () => {
      running = false;
      selectedPointId = null;
      await postJSON("/api/v2/simulation/reset", {});
      refresh(0);
    };
    document.getElementById("machine-back").onclick = () => {
      location.hash = "equipment";
    };
    window.addEventListener("hashchange", updateNavState);
    setInterval(() => refresh(running ? Number(document.getElementById("speed").value) : 0), 1000);
    refresh(0);
  </script>
</body>
</html>
"""
