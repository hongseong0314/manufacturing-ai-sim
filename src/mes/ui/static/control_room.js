    const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
    let running = false;
    let selectedStage = "A";
    let selectedMachineId = null;
    let selectedMachineDetail = null;
    let selectedPointId = null;
    let lastGantt = null;
    let lastLive = null;
    let portfolioStageFilter = "ALL";
    let portfolioSelectedOnly = false;
    let selectedAiDevCorrelation = null;
    let selectedAiDevCandidateId = null;
    let lastAiDevPortfolio = null;
    let selectedExperimentScenarioId = null;
    let selectedExperimentVariantIds = new Set(["baseline_fifo_rule", "c_grouped_packing"]);
    let lastExperiment = null;
    let lastAssignmentTrace = null;
    let lastGenealogy = null;
    const AI_DEV_CYCLE_LIMIT = 25;

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

    function renderId(value, max = 28) {
      const text = String(value || "-");
      const clipped = text.length > max ? `${text.slice(0, max - 1)}…` : text;
      return `<code class="truncate-id" title="${escapeText(text)}">${escapeText(clipped)}</code>`;
    }

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
      const aiDev = await loadAiDevSummary();
      render(live, gantt, aiDev);
      if (selectedMachineId) await loadMachineDetail(selectedMachineId, false);
    }

    async function loadAiDevSummary() {
      try {
        const [policyStack, decisionCycles, policyVariants, scenarios, experiments] = await Promise.all([
          fetch("/api/v2/ai-dev/policy-stack").then(r => r.json()),
          fetch(`/api/v2/ai-dev/decision-cycles?limit=${AI_DEV_CYCLE_LIMIT}`).then(r => r.json()),
          fetch("/api/v2/ai-dev/policy-variants").then(r => r.json()),
          fetch("/api/v2/ai-dev/scenarios").then(r => r.json()),
          fetch("/api/v2/ai-dev/experiments").then(r => r.json()),
        ]);
        return { policyStack, decisionCycles, policyVariants, scenarios, experiments };
      } catch (error) {
        return {
          policyStack: {},
          decisionCycles: { items: [] },
          policyVariants: { items: [] },
          scenarios: { items: [] },
          experiments: { items: [] },
        };
      }
    }

    function render(live, gantt, aiDev = {}) {
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
      renderPortfolio(live.candidate_portfolio || chain.candidate_portfolio || {});
      renderAiDev(live, aiDev);
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
          ${renderId(candidate.candidate_id, 32)}
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
          <div class="trace-card-title">
            <strong>Candidate Portfolio</strong>
            <button class="link-button" id="open-portfolio-workbench" type="button">Open</button>
          </div>
          <code>${escapeText(trace.candidate_count || 0)} candidates</code>
          <div class="candidate-list">${candidateRows || "<span>No selected candidates</span>"}</div>
        </div>
        <div class="trace-card">
          <strong>L2 Annotations</strong>
          <code>${escapeText(annotations.length)} annotations</code>
          <span>selected ${escapeText(trace.selected_candidate_id || "-")}</span>
        </div>`;
      const openPortfolio = document.getElementById("open-portfolio-workbench");
      if (openPortfolio) {
        openPortfolio.onclick = () => {
          location.hash = "candidate-portfolio";
          updateNavState();
        };
      }
    }

    function renderPortfolio(portfolio) {
      const items = portfolio.items || [];
      const filtered = items.filter(candidate => {
        const stage = String(candidate.stage || "").toUpperCase();
        if (portfolioStageFilter !== "ALL" && stage !== portfolioStageFilter) return false;
        if (portfolioSelectedOnly && !candidate.selected) return false;
        return true;
      });
      const summary = portfolio.summary || {};
      document.getElementById("nav-portfolio").textContent = String(summary.count || items.length || 0);
      document.getElementById("portfolio-count").textContent =
        `${filtered.length}/${items.length} candidates · selected ${summary.selected_count || 0}`;
      const stageCounts = summary.stage_counts || {};
      document.getElementById("portfolio-stage-counts").textContent =
        `A ${stageCounts.A || 0} / B ${stageCounts.B || 0} / C ${stageCounts.C || 0}`;
      document.getElementById("portfolio-body").innerHTML = filtered.map(candidate => {
        const annotation = candidate.l2_annotation || {};
        const components = candidate.score_components || {};
        const group = formatGroupKey(candidate.group_key || {});
        const l2 = annotation.quality_risk || annotation.recipe_id || annotation.apc_policy || "-";
        const reason = candidate.selected
          ? "selected_by_l3"
          : (candidate.rejection_reason || "not_selected");
        const commandStatus = candidate.command_status || "-";
        return `<tr class="${candidate.selected ? "portfolio-selected" : ""}">
          <td><span class="${statusClass(candidate.selected ? "PASS" : (candidate.budget_selected ? "PLAN" : "REJECTED"))}">${candidate.selected ? "SELECTED" : (candidate.budget_selected ? "BUDGET" : "REJECTED")}</span></td>
          <td>${escapeText(candidate.stage || "-")}</td>
          <td>${escapeText(group || "-")}</td>
          <td><code>${escapeText(candidate.equipment_id || "-")}</code></td>
          <td><code>${escapeText(formatTaskList(candidate.task_uids || []) || "-")}</code></td>
          <td>${escapeText(formatMetric(candidate.local_score))}</td>
          <td><strong>${escapeText(formatMetric(candidate.upper_score))}</strong><div class="kpi-note">due ${escapeText(formatMetric(components.due_date_pressure))}</div></td>
          <td>${escapeText(l2)}</td>
          <td>${escapeText(reason)}</td>
          <td><span class="${statusClass(commandStatus)}">${escapeText(commandStatus)}</span></td>
        </tr>`;
      }).join("") || "<tr><td colspan='10'>No candidate portfolio yet. Run a cycle to create one.</td></tr>";
    }

    function renderAiDev(live, aiDev) {
      const policy = aiDev.policyStack || {};
      const cycles = aiDev.decisionCycles?.items || [];
      document.getElementById("nav-ai-dev").textContent = String(cycles.length || "-");
      document.getElementById("ai-dev-policy-factory").textContent = policy.factory_name || "-";
      renderAiDevPolicyStack(policy);
      renderAiDevCycles(cycles);
      renderExperimentRunner(aiDev);
      const fallbackPortfolio = live.candidate_portfolio || live.active_chain?.candidate_portfolio || {};
      const activePortfolio = lastAiDevPortfolio || fallbackPortfolio;
      if (!selectedAiDevCorrelation && activePortfolio.correlation_id) {
        selectedAiDevCorrelation = activePortfolio.correlation_id;
      }
      renderAiDevPortfolio(activePortfolio);
    }

    function renderAiDevPolicyStack(policy) {
      const layers = policy.layers || {};
      document.getElementById("ai-dev-policy-stack-body").innerHTML = ["L4", "L3", "L1", "L2"].map(layer => {
        const item = layers[layer] || {};
        const policyId = item.policy_id || policy[`${layer.toLowerCase()}_policy_id`] || "-";
        const modelId = item.model_id || "-";
        const configSummary = policyConfigSummary(policy, layer);
        return `<div class="policy-layer">
          <strong>${layer}</strong>
          <div class="policy-layer-detail">
            <code title="${escapeText(policyId)}">${escapeText(policyId)}</code>
            <span title="${escapeText(modelId)}">model ${escapeText(modelId)} · v${escapeText(item.model_version || "-")}</span>
            <span title="${escapeText(configSummary)}">config ${escapeText(configSummary)}</span>
            <span>source ${escapeText(item.config_source || policy.factory_name || "-")}</span>
          </div>
        </div>`;
      }).join("");
    }

    function policyConfigSummary(policy, layer) {
      const config = policy.config || {};
      if (layer === "L4") {
        return `objective_policy_L4=${policy.objective_policy_L4 || config.objective_policy_L4 || "-"}`;
      }
      if (layer === "L3") {
        return `meta_scheduler_L3=${policy.meta_scheduler_L3 || config.meta_scheduler_L3 || "-"}`;
      }
      if (layer === "L2") {
        return `tuner_A=${policy.tuner_A || config.tuner_A || "-"} · tuner_B=${policy.tuner_B || config.tuner_B || "-"}`;
      }
      return [
        `scheduler_A=${policy.scheduler_A || config.scheduler_A || "-"}`,
        `scheduler_B=${policy.scheduler_B || config.scheduler_B || "-"}`,
        `packing_C=${policy.packing_C || config.packing_C || "-"}`,
      ].join(" · ");
    }

    function renderAiDevCycles(cycles) {
      document.getElementById("ai-dev-cycle-count").textContent = `${cycles.length} latest`;
      document.getElementById("ai-dev-cycle-body").innerHTML = cycles.map(row => {
        const selected = row.correlation_id === selectedAiDevCorrelation;
        return `<tr class="${selected ? "portfolio-selected" : ""}">
          <td><button class="link-button ai-dev-cycle-link" type="button" data-corr="${escapeText(row.correlation_id)}">${renderId(row.correlation_id, 24)}</button></td>
          <td>${escapeText(row.time ?? "-")}</td>
          <td>${escapeText(row.objective_id || "-")}</td>
          <td>${escapeText(row.selected_stage || "-")}</td>
          <td>${escapeText(`${row.selected_count || 0}/${row.candidate_count || 0}`)}</td>
          <td><span class="${statusClass(row.is_actionable ? "PASS" : "PENDING")}">${escapeText(row.is_actionable ? "ACTIONABLE" : (row.empty_reason || "EMPTY"))}</span></td>
        </tr>`;
      }).join("") || "<tr><td colspan='6'>No decision cycles yet.</td></tr>";
      document.querySelectorAll(".ai-dev-cycle-link").forEach(button => {
        button.onclick = async () => {
          await loadAiDevPortfolio(button.dataset.corr);
        };
      });
    }

    async function loadAiDevPortfolio(correlationId) {
      if (!correlationId) return;
      selectedAiDevCorrelation = correlationId;
      selectedAiDevCandidateId = null;
      lastAiDevPortfolio = await fetch(`/api/v2/ai-dev/candidate-portfolio/${correlationId}`).then(r => r.json());
      renderAiDevPortfolio(lastAiDevPortfolio);
      renderAiDevCycles((await loadAiDevSummary()).decisionCycles?.items || []);
    }

    function renderAiDevPortfolio(portfolio) {
      const items = portfolio.items || [];
      const selected = items.find(item => item.candidate_id === selectedAiDevCandidateId)
        || items.find(item => item.selected)
        || items[0]
        || null;
      selectedAiDevCandidateId = selected?.candidate_id || null;
      document.getElementById("ai-dev-summary").textContent =
        `${portfolio.kind || "EMPTY"} · ${portfolio.correlation_id || "-"} · ${items.length} candidates`;
      document.getElementById("ai-dev-portfolio-title").textContent =
        `${portfolio.correlation_id || "-"} · ${portfolio.summary?.selected_count || 0}/${portfolio.count || 0} selected`;
      document.getElementById("ai-dev-portfolio-body").innerHTML = items.map(candidate => {
        const annotation = candidate.l2_annotation || {};
        return `<tr class="${candidate.candidate_id === selectedAiDevCandidateId ? "portfolio-selected" : ""}">
          <td><button class="link-button ai-dev-candidate-link" type="button" data-candidate-id="${escapeText(candidate.candidate_id)}">${escapeText(candidate.selected ? "SELECTED" : (candidate.budget_selected ? "BUDGET" : "REJECTED"))}</button></td>
          <td>${escapeText(candidate.stage || "-")}</td>
          <td>${escapeText(formatGroupKey(candidate.group_key || {}) || "-")}</td>
          <td><code>${escapeText(candidate.equipment_id || "-")}</code></td>
          <td><code>${escapeText(formatTaskList(candidate.task_uids || []) || "-")}</code></td>
          <td>${escapeText(formatMetric(candidate.local_score))}</td>
          <td><strong>${escapeText(formatMetric(candidate.upper_score))}</strong></td>
          <td>${escapeText(annotation.quality_risk || annotation.recipe_id || "-")}</td>
          <td>${escapeText(candidate.rejection_reason || (candidate.selected ? "selected_by_l3" : "-"))}</td>
        </tr>`;
      }).join("") || "<tr><td colspan='9'>No candidates in this cycle.</td></tr>";
      document.querySelectorAll(".ai-dev-candidate-link").forEach(button => {
        button.onclick = () => {
          selectedAiDevCandidateId = button.dataset.candidateId;
          renderAiDevPortfolio(portfolio);
        };
      });
      renderAiDevCandidateDetail(selected, portfolio);
      renderAiDevDiagnostics(portfolio);
    }

    function renderAiDevCandidateDetail(candidate, portfolio) {
      const target = document.getElementById("ai-dev-candidate-detail");
      document.getElementById("ai-dev-candidate-title").textContent = candidate?.candidate_id || "empty";
      if (!candidate) {
        target.innerHTML = "<span class='kpi-note'>Select a decision cycle with candidates.</span>";
        return;
      }
      const components = candidate.score_components || {};
      const annotation = candidate.l2_annotation || {};
      const weights = portfolio.objective_weights || {};
      target.innerHTML = `
        <dl>
          <dt>Local</dt><dd>${escapeText(formatMetric(components.local_candidate_score ?? candidate.local_score))}</dd>
          <dt>Due pressure</dt><dd>${escapeText(formatMetric(components.due_date_pressure))}</dd>
          <dt>WIP pressure</dt><dd>${escapeText(formatMetric(components.wip_pressure))}</dd>
          <dt>Objective bonus</dt><dd>${escapeText(formatMetric(components.objective_weight_bonus))}</dd>
          <dt>Quality penalty</dt><dd>${escapeText(formatMetric(components.quality_risk_penalty))}</dd>
          <dt>Final upper</dt><dd>${escapeText(formatMetric(components.final_upper_score ?? candidate.upper_score))}</dd>
          <dt>L4 weights</dt><dd>${escapeText(formatGroupKey(weights) || "-")}</dd>
          <dt>L2 annotation</dt><dd>${escapeText(formatGroupKey(annotation) || "-")}</dd>
        </dl>`;
    }

    function renderAiDevDiagnostics(portfolio) {
      const diagnostics = portfolio.diagnostics?.stages || {};
      document.getElementById("ai-dev-empty-status").textContent =
        portfolio.is_actionable ? "actionable" : (portfolio.empty_reason || "empty");
      document.getElementById("ai-dev-empty-diagnostics").innerHTML = `
        <dl>
          ${["A", "B", "C"].map(stage => {
            const item = diagnostics[stage] || {};
            return `<dt>${stage}</dt><dd>queue ${item.queue_size || 0} · idle ${item.idle_machines || 0} · running ${item.running_machines || 0} · batch ${item.batch_size || 1} · candidates ${item.candidate_count || 0}</dd>`;
          }).join("")}
          <dt>Latest empty</dt><dd><code>${escapeText(portfolio.latest_empty_correlation_id || "-")}</code></dd>
          <dt>Last actionable</dt><dd><code>${escapeText(portfolio.last_actionable_correlation_id || "-")}</code></dd>
        </dl>`;
    }

    async function loadAssignmentTrace(params = {}) {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined && String(value) !== "") {
          query.set(key, value);
        }
      });
      const suffix = query.toString() ? `?${query.toString()}` : "";
      lastAssignmentTrace = await fetch(`/api/v2/assignment-trace${suffix}`).then(r => r.json());
      renderAssignmentTrace(lastAssignmentTrace);
      return lastAssignmentTrace;
    }

    function renderAssignmentTrace(trace) {
      const found = Boolean(trace?.found);
      document.getElementById("nav-assignment-trace").textContent = found ? "active" : "-";
      document.getElementById("trace-status").textContent = found
        ? `${trace.assignment?.equipment_id || "-"} · ${formatTaskList(trace.assignment?.task_uids || [])}`
        : (trace?.reason || "No trace loaded");
      renderTraceAssignment(trace || {});
      renderTraceState(trace || {});
      renderTraceLayers(trace || {});
      renderTracePortfolio(trace?.candidate_portfolio || {});
      document.getElementById("trace-raw-payload").textContent = JSON.stringify(trace || {}, null, 2);
      attachTraceGenealogyLink(trace || {});
    }

    function renderTraceAssignment(trace) {
      const assignment = trace.assignment || {};
      document.getElementById("trace-assignment-title").textContent =
        assignment.correlation_id || "-";
      document.getElementById("trace-assignment-summary").innerHTML = trace.found ? `
        <dl>
          <dt>Equipment</dt><dd><code>${escapeText(assignment.equipment_id || "-")}</code></dd>
          <dt>Tasks</dt><dd><code>${escapeText(formatTaskList(assignment.task_uids || []) || "-")}</code></dd>
          <dt>Window</dt><dd>t=${escapeText(assignment.start ?? "-")}→${escapeText(assignment.end ?? "-")}</dd>
          <dt>Candidate</dt><dd>${renderId(assignment.candidate_id, 32)}</dd>
          <dt>Command</dt><dd>${renderId(assignment.command_id, 28)}</dd>
          <dt>Simulator action</dt><dd>${escapeText(formatGroupKey(trace.simulator_action || {}) || "-")}</dd>
          <dt>Genealogy</dt><dd><button class="link-button trace-genealogy-link" type="button">Open execution lineage</button></dd>
        </dl>` : `<span class="kpi-note">${escapeText(trace.reason || "Search for an assignment trace.")}</span>`;
    }

    function attachTraceGenealogyLink(trace) {
      const button = document.querySelector(".trace-genealogy-link");
      if (!button || !trace?.found) return;
      button.onclick = async () => {
        const assignment = trace.assignment || {};
        document.getElementById("genealogy-task-uid").value = (assignment.task_uids || [])[0] ?? "";
        document.getElementById("genealogy-equipment-id").value = assignment.equipment_id || "";
        document.getElementById("genealogy-correlation-id").value = assignment.correlation_id || "";
        document.getElementById("genealogy-state-time").value = assignment.start ?? "";
        location.hash = "genealogy";
        await loadGenealogy();
      };
    }

    function renderTraceState(trace) {
      const summary = trace.state_summary || {};
      const machine = trace.machine_snapshot || {};
      const tasks = trace.task_snapshots || [];
      document.getElementById("trace-state-title").textContent = `t=${summary.time ?? "-"}`;
      document.getElementById("trace-state-summary").innerHTML = trace.found ? `
        <dl>
          <dt>A/B/C queues</dt><dd>${["A", "B", "C"].map(stage => {
            const item = summary.stages?.[stage] || {};
            return `${stage} wait ${item.wait || 0} · in ${item.incoming || 0} · rework ${item.rework || 0}`;
          }).join("<br>")}</dd>
          <dt>Machine</dt><dd><code>${escapeText(machine.equipment_id || "-")}</code> · ${escapeText(machine.status || "-")} · batch ${escapeText(machine.batch_size || "-")}</dd>
          <dt>Task rows</dt><dd>${tasks.map(task => `T${escapeText(task.uid)} due ${escapeText(task.due_date ?? "-")} · ${escapeText(task.customer_id || "-")} · ${escapeText(task.material_type || "-")} / ${escapeText(task.color || "-")}`).join("<br>") || "-"}</dd>
        </dl>` : "<span class='kpi-note'>No decision state loaded.</span>";
    }

    function renderTraceLayers(trace) {
      const layers = trace.layers || {};
      const order = ["L4", "L3", "L1", "L2", "RULE_ENGINE", "COMMAND"];
      document.getElementById("trace-layer-timeline").innerHTML = order.map(layer => {
        const item = layers[layer] || {};
        const action = item.recommended_action || item.validated_command || {};
        const label = item.recommendation_type || item.validation_status || item.command_type || "-";
        const status = item.rule_validation_status || item.validation_status || item.status || "";
        return `<div class="trace-layer-card">
          <strong>${escapeText(layer)} · ${escapeText(label)}</strong>
          ${renderId(item.recommendation_id || item.command_id || item.correlation_id, 32)}
          <span>policy ${escapeText(item.policy_id || "-")} · model ${escapeText(item.model_id || "-")}</span>
          <span>status ${escapeText(status || "-")}</span>
          <span>action ${escapeText(formatGroupKey(action) || "-")}</span>
        </div>`;
      }).join("");
    }

    function renderTracePortfolio(portfolio) {
      const items = portfolio.items || [];
      document.getElementById("trace-portfolio-title").textContent =
        `${portfolio.correlation_id || "-"} · ${portfolio.summary?.selected_count || 0}/${portfolio.count || 0} selected`;
      document.getElementById("trace-portfolio-body").innerHTML = items.map(candidate => {
        const annotation = candidate.l2_annotation || {};
        return `<tr class="${candidate.selected ? "portfolio-selected" : ""}">
          <td>${escapeText(candidate.selected ? "SELECTED" : (candidate.budget_selected ? "BUDGET" : "REJECTED"))}</td>
          <td>${escapeText(candidate.stage || "-")}</td>
          <td>${escapeText(formatGroupKey(candidate.group_key || {}) || "-")}</td>
          <td><code>${escapeText(candidate.equipment_id || "-")}</code></td>
          <td><code>${escapeText(formatTaskList(candidate.task_uids || []) || "-")}</code></td>
          <td>${escapeText(formatMetric(candidate.local_score))}</td>
          <td><strong>${escapeText(formatMetric(candidate.upper_score))}</strong></td>
          <td>${escapeText(annotation.quality_risk || annotation.recipe_id || "-")}</td>
          <td>${escapeText(candidate.rejection_reason || (candidate.selected ? "selected_by_l3" : "-"))}</td>
        </tr>`;
      }).join("") || "<tr><td colspan='9'>No portfolio rows for this trace.</td></tr>";
    }

    async function loadGenealogy() {
      const inputs = {
        task_uid: document.getElementById("genealogy-task-uid").value.trim(),
        equipment_id: document.getElementById("genealogy-equipment-id").value.trim(),
        lot_id: document.getElementById("genealogy-lot-id").value.trim(),
        correlation_id: document.getElementById("genealogy-correlation-id").value.trim(),
        state_time: document.getElementById("genealogy-state-time").value.trim(),
      };
      const payload = { inputs, task: null, equipment: null, lot: null, ledger: null, state: null };

      if (inputs.task_uid) {
        payload.task = await fetch(`/api/v2/genealogy/task/${encodeURIComponent(inputs.task_uid)}`).then(r => r.json());
        if (payload.task?.found) {
          inputs.lot_id ||= payload.task.lot_id || "";
          inputs.equipment_id ||= payload.task.assignments?.[0]?.equipment_id || "";
          inputs.correlation_id ||= payload.task.assignment_trace?.correlation_id || payload.task.related_correlation_ids?.[0] || "";
        }
      }
      if (inputs.equipment_id) {
        payload.equipment = await fetch(`/api/v2/genealogy/equipment/${encodeURIComponent(inputs.equipment_id)}`).then(r => r.json());
      }
      if (inputs.lot_id) {
        payload.lot = await fetch(`/api/v2/genealogy/lot/${encodeURIComponent(inputs.lot_id)}`).then(r => r.json());
      }
      if (inputs.correlation_id) {
        payload.ledger = await fetch(`/api/v2/execution-ledger/${encodeURIComponent(inputs.correlation_id)}`).then(r => r.json());
      }
      if (inputs.state_time) {
        payload.state = await fetch(`/api/v2/digital-twin/state-at?time=${encodeURIComponent(inputs.state_time)}`).then(r => r.json());
      }
      renderGenealogy(payload);
      return payload;
    }

    function renderGenealogy(payload) {
      lastGenealogy = payload;
      const foundCount = ["task", "equipment", "lot", "ledger", "state"]
        .filter(key => payload?.[key]?.found).length;
      document.getElementById("nav-genealogy").textContent = foundCount ? `${foundCount}` : "-";
      document.getElementById("genealogy-status").textContent =
        foundCount ? `${foundCount} genealogy views loaded` : "No genealogy result loaded";
      renderGenealogyTask(payload?.task || {});
      renderGenealogyEquipment(payload?.equipment || {});
      renderGenealogyLot(payload?.lot || {});
      renderGenealogyState(payload?.state || {});
      renderGenealogyLedger(payload?.ledger || {});
      renderGenealogyTimeline(payload || {});
    }

    function renderGenealogyTask(task) {
      document.getElementById("genealogy-task-title").textContent =
        task?.found ? `T${task.task_uid} · ${task.lot_id || "-"}` : (task?.reason || "-");
      document.getElementById("genealogy-task-summary").innerHTML = task?.found ? `
        <dl>
          <dt>Wafer</dt><dd><code>${escapeText(task.wafer_id || "-")}</code></dd>
          <dt>Current</dt><dd>${escapeText(task.current_state?.location || "-")} · ${escapeText(task.current_state?.customer_id || "-")} · ${escapeText(task.current_state?.material_type || "-")} / ${escapeText(task.current_state?.color || "-")}</dd>
          <dt>Assignments</dt><dd>${(task.assignments || []).map(item =>
            `${escapeText(item.stage || "-")} ${escapeText(item.equipment_id || "-")} · ${renderId(item.command_id, 24)}`
          ).join("<br>") || "-"}</dd>
          <dt>Correlations</dt><dd>${(task.related_correlation_ids || []).map(id => renderId(id, 24)).join("<br>") || "-"}</dd>
        </dl>` : "<span class='kpi-note'>Search by task UID to load task lineage.</span>";
    }

    function renderGenealogyEquipment(equipment) {
      document.getElementById("genealogy-equipment-title").textContent =
        equipment?.found ? `${equipment.equipment_id} · ${equipment.commands?.length || 0} commands` : (equipment?.reason || "-");
      document.getElementById("genealogy-equipment-summary").innerHTML = equipment?.found ? `
        <dl>
          <dt>Stage</dt><dd>${escapeText(equipment.stage || "-")}</dd>
          <dt>Status</dt><dd>${escapeText(equipment.current_state?.status || "-")} · finish t=${escapeText(equipment.current_state?.finish_time ?? "-")}</dd>
          <dt>Current batch</dt><dd><code>${escapeText(formatTaskList(equipment.current_state?.current_batch_uids || []) || "-")}</code></dd>
          <dt>Latest commands</dt><dd>${(equipment.commands || []).slice(0, 5).map(item =>
            `${renderId(item.command_id, 24)} · ${escapeText(formatTaskList(item.task_uids || []) || "-")}`
          ).join("<br>") || "-"}</dd>
        </dl>` : "<span class='kpi-note'>Search by equipment ID to load tool timeline.</span>";
    }

    function renderGenealogyLot(lot) {
      document.getElementById("genealogy-lot-title").textContent =
        lot?.found ? `${lot.lot_id} · ${lot.task_count || 0} tasks` : (lot?.reason || "-");
      document.getElementById("genealogy-lot-summary").innerHTML = lot?.found ? `
        <dl>
          <dt>Tasks</dt><dd><code>${escapeText(formatTaskList(lot.task_uids || []) || "-")}</code></dd>
          <dt>Commands</dt><dd>${(lot.command_ids || []).slice(0, 8).map(id => renderId(id, 24)).join("<br>") || "-"}</dd>
          <dt>Correlations</dt><dd>${(lot.related_correlation_ids || []).slice(0, 8).map(id => renderId(id, 24)).join("<br>") || "-"}</dd>
        </dl>` : "<span class='kpi-note'>Search by lot ID or task UID to load lot rollout.</span>";
    }

    function renderGenealogyState(state) {
      const summary = state?.summary || {};
      document.getElementById("genealogy-state-title").textContent =
        state?.found ? `requested t=${state.requested_time} · source ${state.source || "-"}` : (state?.reason || "-");
      document.getElementById("genealogy-state-summary").innerHTML = state?.found ? `
        <dl>
          <dt>State time</dt><dd>${escapeText(summary.time ?? "-")}</dd>
          <dt>Completed</dt><dd>${escapeText(summary.num_completed ?? 0)}</dd>
          <dt>A/B/C</dt><dd>${["A", "B", "C"].map(stage => {
            const item = summary.stages?.[stage] || {};
            return `${stage} wait ${item.wait || 0} · in ${item.incoming || 0} · rework ${item.rework || 0} · machines ${item.machines || 0}`;
          }).join("<br>")}</dd>
        </dl>` : "<span class='kpi-note'>Enter state time to load replayable snapshot summary.</span>";
    }

    function renderGenealogyLedger(ledger) {
      const records = ledger?.records || [];
      document.getElementById("genealogy-ledger-title").textContent =
        ledger?.found ? `${ledger.correlation_id} · ${records.length} records` : (ledger?.reason || "-");
      document.getElementById("genealogy-ledger-body").innerHTML = records.map(record => `
        <tr>
          <td>${escapeText(record.time ?? "-")}</td>
          <td>${escapeText(record.event_type || "-")}</td>
          <td>${escapeText(record.actor_type || "-")}</td>
          <td><code>${escapeText(record.equipment_id || "-")}</code></td>
          <td><code>${escapeText(formatTaskList(record.task_uids || []) || "-")}</code></td>
          <td>${renderId(record.command_id || record.recommendation_id || record.correlation_id, 28)}</td>
        </tr>
      `).join("") || "<tr><td colspan='6'>No execution ledger loaded.</td></tr>";
    }

    function renderGenealogyTimeline(payload) {
      const source = payload.task?.found ? payload.task : (payload.equipment?.found ? payload.equipment : payload.lot);
      const rows = source?.timeline || [];
      document.getElementById("genealogy-timeline-title").textContent =
        rows.length ? `${rows.length} lineage events` : "-";
      document.getElementById("genealogy-timeline").innerHTML = rows.map(record => `
        <div class="trace-layer-card">
          <strong>t=${escapeText(record.time ?? "-")} · ${escapeText(record.event_type || "-")}</strong>
          <span>actor ${escapeText(record.actor_type || "-")} · equipment ${escapeText(record.equipment_id || "-")} · tasks ${escapeText(formatTaskList(record.task_uids || []) || "-")}</span>
          <span>command ${escapeText(record.command_id || "-")} · correlation ${escapeText(record.correlation_id || "-")}</span>
        </div>
      `).join("") || "<span class='kpi-note'>No lineage timeline loaded.</span>";
    }

    function renderExperimentRunner(aiDev) {
      const variants = aiDev.policyVariants?.items || [];
      const scenarios = aiDev.scenarios?.items || [];
      if (!selectedExperimentScenarioId && scenarios.length) {
        selectedExperimentScenarioId = scenarios[0].scenario_id;
      }
      const scenarioSelect = document.getElementById("experiment-scenario");
      scenarioSelect.innerHTML = scenarios.map(scenario => `
        <option value="${escapeText(scenario.scenario_id)}" ${scenario.scenario_id === selectedExperimentScenarioId ? "selected" : ""}>
          ${escapeText(`${scenario.scenario_id} · t=${scenario.time} · tasks ${scenario.task_count}`)}
        </option>
      `).join("") || "<option value=''>No scenario captured</option>";
      document.getElementById("policy-variant-list").innerHTML = variants.map(variant => {
        const checked = selectedExperimentVariantIds.has(variant.variant_id) ? "checked" : "";
        return `<div class="variant-option">
          <label>
            <input type="checkbox" class="experiment-variant" value="${escapeText(variant.variant_id)}" ${checked}>
            <span>${escapeText(variant.label || variant.variant_id)}</span>
          </label>
          <span>${escapeText(variant.description || "")}</span>
        </div>`;
      }).join("") || "<span class='kpi-note'>No policy variants registered.</span>";
      document.querySelectorAll(".experiment-variant").forEach(input => {
        input.onchange = () => {
          if (input.checked) {
            selectedExperimentVariantIds.add(input.value);
          } else {
            selectedExperimentVariantIds.delete(input.value);
          }
        };
      });
      renderExperimentResults(lastExperiment);
    }

    function renderExperimentResults(experiment) {
      const results = experiment?.results || [];
      document.getElementById("experiment-status").textContent = experiment
        ? `${experiment.experiment_id} · ${results.length} variants`
        : "No experiment";
      document.getElementById("experiment-result-body").innerHTML = results.map(row => {
        const delta = row.kpi_delta || {};
        return `<tr class="${row.variant_id === experiment?.comparison?.best_variant_id ? "portfolio-selected" : ""}">
          <td><code>${escapeText(row.variant_id || "-")}</code></td>
          <td>${escapeText(row.l4_objective_id || "-")}</td>
          <td>${escapeText(row.selected_stage || "-")}</td>
          <td>${renderId(row.selected_candidate_id, 32)}</td>
          <td>${escapeText(formatMetric(row.local_score))}</td>
          <td><strong>${escapeText(formatMetric(row.upper_score))}</strong></td>
          <td>${escapeText(row.quality_risk || "-")}</td>
          <td><span class="${statusClass(row.command_valid ? "PASS" : "REJECTED")}">${escapeText(row.validation_status || "-")}</span></td>
          <td>${escapeText(`wip ${delta.expected_wip_reduction || 0} · done ${delta.expected_completion_delta || 0}`)}</td>
        </tr>`;
      }).join("") || "<tr><td colspan='9'>Capture a scenario and run a comparison.</td></tr>";
      renderExperimentInspector(experiment);
    }

    function renderExperimentInspector(experiment) {
      const target = document.getElementById("experiment-comparison-inspector");
      if (!experiment) {
        target.innerHTML = "<span class='kpi-note'>No comparison result yet.</span>";
        return;
      }
      const comparison = experiment.comparison || {};
      const rows = comparison.decision_diff || [];
      target.innerHTML = `
        <dl>
          <dt>Scenario</dt><dd><code>${escapeText(experiment.scenario_id || "-")}</code></dd>
          <dt>Best variant</dt><dd><code>${escapeText(comparison.best_variant_id || "-")}</code> · ${escapeText(comparison.best_reason || "-")}</dd>
          <dt>Decision diff</dt><dd>${rows.map(row =>
            `${escapeText(row.variant_id || "-")}: ${escapeText(row.selected_stage || "-")} · upper ${escapeText(formatMetric(row.upper_score))} · ${escapeText(row.command_valid ? "valid" : "invalid")}`
          ).join("<br>")}</dd>
        </dl>`;
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
      return `<span class="gantt-bar ${cls} selectable-gantt-bar" data-machine-id="${escapeText(bar.machine_id)}" data-stage="${escapeText(bar.stage)}" data-task-uids="${escapeText((bar.task_uids || []).join(","))}" data-batch-uids="${escapeText((bar.batch_task_uids || bar.task_uids || []).join(","))}" data-correlation-id="${escapeText(bar.correlation_id || "")}" data-command-id="${escapeText(bar.command_id || "")}" data-candidate-id="${escapeText(bar.candidate_id || "")}" style="left:${left}%;width:${width}%;top:${top}px;height:${height}px;" title="${escapeText(title)}">${escapeText(bar.label || uids || bar.status)}</span>`;
    }

    function attachGanttBarHandlers(target) {
      target.querySelectorAll(".selectable-gantt-bar[data-machine-id]").forEach(bar => {
        bar.onclick = () => openAssignmentTraceFromBar(bar);
      });
    }

    async function openAssignmentTraceFromBar(bar) {
      const taskUid = String(bar.dataset.taskUids || bar.dataset.batchUids || "")
        .split(",")
        .filter(Boolean)[0] || "";
      const params = {
        equipment_id: bar.dataset.machineId || "",
        task_uid: taskUid,
        correlation_id: bar.dataset.correlationId || "",
        candidate_id: bar.dataset.candidateId || "",
      };
      document.getElementById("trace-equipment-id").value = params.equipment_id;
      document.getElementById("trace-task-uid").value = params.task_uid;
      document.getElementById("trace-correlation-id").value = params.correlation_id;
      document.getElementById("trace-candidate-id").value = params.candidate_id;
      location.hash = "assignment-trace";
      await loadAssignmentTrace(params);
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

    function formatGroupKey(group) {
      return Object.entries(group || {})
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
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
      document.body.classList.toggle("portfolio-page", hash === "#candidate-portfolio");
      document.body.classList.toggle("ai-dev-page", hash === "#ai-dev");
      document.body.classList.toggle("assignment-trace-page-active", hash === "#assignment-trace");
      document.body.classList.toggle("genealogy-page-active", hash === "#genealogy");
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
    document.getElementById("portfolio-stage-filter").onchange = (event) => {
      portfolioStageFilter = event.target.value || "ALL";
      renderPortfolio(lastLive?.candidate_portfolio || lastLive?.active_chain?.candidate_portfolio || {});
    };
    document.getElementById("portfolio-selected-only").onchange = (event) => {
      portfolioSelectedOnly = Boolean(event.target.checked);
      renderPortfolio(lastLive?.candidate_portfolio || lastLive?.active_chain?.candidate_portfolio || {});
    };
    document.getElementById("experiment-scenario").onchange = (event) => {
      selectedExperimentScenarioId = event.target.value || null;
    };
    document.getElementById("capture-scenario").onclick = async () => {
      const scenario = await postJSON("/api/v2/ai-dev/scenarios/capture", {});
      selectedExperimentScenarioId = scenario.scenario_id;
      refresh(0);
    };
    document.getElementById("run-experiment").onclick = async () => {
      if (!selectedExperimentScenarioId) {
        const scenario = await postJSON("/api/v2/ai-dev/scenarios/capture", {});
        selectedExperimentScenarioId = scenario.scenario_id;
      }
      const variantIds = Array.from(selectedExperimentVariantIds);
      lastExperiment = await postJSON("/api/v2/ai-dev/experiments/run", {
        scenario_id: selectedExperimentScenarioId,
        variant_ids: variantIds.length ? variantIds : ["baseline_fifo_rule"],
      });
      renderExperimentResults(lastExperiment);
    };
    document.getElementById("trace-find").onclick = async () => {
      const params = {
        equipment_id: document.getElementById("trace-equipment-id").value.trim(),
        task_uid: document.getElementById("trace-task-uid").value.trim(),
        correlation_id: document.getElementById("trace-correlation-id").value.trim(),
        candidate_id: document.getElementById("trace-candidate-id").value.trim(),
      };
      location.hash = "assignment-trace";
      await loadAssignmentTrace(params);
    };
    document.getElementById("genealogy-find").onclick = async () => {
      location.hash = "genealogy";
      await loadGenealogy();
    };
    document.getElementById("trace-raw-payload-toggle").onclick = () => {
      const payload = document.getElementById("trace-raw-payload");
      const collapsed = payload.classList.toggle("raw-json-collapsed");
      document.getElementById("trace-raw-payload-toggle").textContent =
        collapsed ? "Show full raw JSON" : "Collapse raw JSON";
    };
    window.addEventListener("hashchange", updateNavState);
    setInterval(() => refresh(running ? Number(document.getElementById("speed").value) : 0), 1000);
    refresh(0);
