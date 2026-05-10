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
