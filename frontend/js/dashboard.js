/* =========================================================
   RAIL-OPTIMAX — AI-3 ACTIVE SUGGESTIONS
   AI-3 CONFLICTS + AI-1 RECOMMENDATIONS
   ========================================================= */

(function () {
  "use strict";

  const AI_DC = {
    conflictUrl: "./ai/manage",
    coordinationUrl: "./ai/coordination-opportunities",
    operatorUrl: "./operator/decision",
  };

  let decisionCenter = null;
  let activeAlerts = [];
  let lastRefresh = null;
  let lastSnapshot = null;
  // Tracks operator acknowledgements during the current browser session.
  // Without this declaration updateFromTelemetry throws ReferenceError and
  // the AI-3 panel remains stuck on "Scanning live conflicts...".
  const acknowledgedDecisionIds = new Set();
  let fallbackPollTimer = null;
  let lastTelemetryAt = 0;
  let staleTimer = null;

  function escapeHTML(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function findMountPoint() {
    return document.querySelector("#ai3-suggestions-mount");
  }

  function createDecisionCenter() {
    if (document.querySelector("#ai-decision-center")) {
      return document.querySelector("#ai-decision-center");
    }

    const mount = findMountPoint();

    if (!mount) {
      console.warn("RAIL-OPTIMAX: dashboard mount point not found");
      return null;
    }

    const wrapper = document.createElement("section");
    wrapper.id = "ai-decision-center";
    wrapper.className = "ai-decision-center";

    wrapper.innerHTML = `
            <div class="ai-dc-header">
                <div class="ai-dc-title">
                    <span class="ai-dc-icon">⚡</span>
                    AI-3 ACTIVE SUGGESTIONS
                </div>

                <div class="ai-dc-live" id="ai-dc-live-indicator">
                    <span class="ai-dc-live-dot"></span>
                    <span id="ai-dc-live-label">LIVE</span>
                </div>
            </div>

            <div class="ai-dc-body" id="ai-dc-body">
                <div class="ai-dc-empty">
                    Scanning live conflicts and generating operator suggestions...
                </div>
            </div>

            <div class="ai-dc-footer">
                <span id="ai-dc-status">Awaiting AI-3 telemetry</span>
                <button class="ai-dc-refresh" id="ai-dc-refresh">
                    ↻ REFRESH
                </button>
            </div>
        `;

    /*
     * Put Decision Center directly below the VDU.
     * If #bot-grid exists, it goes there.
     */
    mount.appendChild(wrapper);

    document
      .querySelector("#ai-dc-refresh")
      ?.addEventListener("click", refreshDecisionCenter);

    return wrapper;
  }

  function normalizeConflict(item, snapshot = lastSnapshot) {
    const trainA =
      item.train_a ||
      item.trainA ||
      item.train1 ||
      item.leading_train ||
      "";

    const trainB =
      item.train_b ||
      item.trainB ||
      item.train2 ||
      item.conflicting_train ||
      item.trailing_train ||
      "";

    // The telemetry snapshot is the authoritative physical state. AI-3
    // endpoint polling can arrive between two telemetry ticks, so never show
    // an advisory speed that disagrees with the train currently rendered on
    // the OCC map/roster.
    const liveTrains = Array.isArray(snapshot?.trains) ? snapshot.trains : [];
    const liveA = liveTrains.find(t => String(t.train_no) === String(trainA));
    const liveB = liveTrains.find(t => String(t.train_no) === String(trainB));
    const liveControl = snapshot?.ai3?.controls?.[String(trainB)] || {};

    const distance =
      item.distance_km ?? item.headway_km ?? item.separation_km ?? 0;

    const station =
      item.station ||
      item.location ||
      item.node ||
      item.section ||
      "CONTROL SECTION";

    const severity =
      item.severity || (Number(distance) < 1 ? "CRITICAL" : "WARNING");

    const action = String(
      item.recommended_action || item.action ||
      (severity.toUpperCase().includes("CRITICAL") ? "HOLD" : "SPEED_REGULATION")
    ).toUpperCase();

    const targetSpeed = item.target_speed_kmh ?? (action === "HOLD" ? 0 : 40);
    const recommendation =
      item.recommendation ||
      (action === "HOLD"
        ? `Hold ${trainB || "approaching train"} at the next safe signal`
        : `Regulate ${trainB || "approaching train"} to ${targetSpeed} km/h`);

    return {
      id: item.id || item.conflict_id || `AI3-${trainA}-${trainB}-${station}`,
      source: "AI-3 MANAGE",
      severity: severity.toUpperCase(),
      title: item.title || "TRAIN SEPARATION BREACH",
      detail: `${trainA || "Train A"} ↔ ${trainB || "Train B"} separation below the configured threshold near ${station}.`,
      distance: Number(distance).toFixed(2),
      timeHeadway: item.time_headway_minutes != null ? Number(item.time_headway_minutes).toFixed(2) : null,
      station,
      recommendation,
      trainA,
      trainB,
      action,
      actualSpeed: Number(
        liveB?.actual_speed_kmh ??
        liveB?.effective_speed_kmh ??
        liveB?.speed_kmh ??
        item.trailing_actual_speed_kmh ??
        item.current_speed_kmh ??
        0
      ),
      targetSpeed: Number(
        liveControl.target_speed_kmh ??
        item.target_speed_kmh ??
        (action === "HOLD" ? 0 : 40)
      ),
      liveTrainState: liveB?.status || "",
      liveTrainKm: liveB?.current_km,
      liveLeadingKm: liveA?.current_km,
    };
  }

  function normalizeCoordination(item) {
    const block = item.block_id || item.block || item.id || "B-NEW";

    const departments =
      item.departments ||
      item.depts ||
      item.department_list ||
      "Engineering + S&T + TRD";

    const duration = item.duration_minutes || item.duration || 90;

    const delay =
      item.train_delay_minutes || item.train_delay || item.delay || 0;

    return {
      id: `AI1-${block}`,
      source: "AI-1 PLAN",
      severity: "INFO",
      title: "SHADOW BLOCK OPPORTUNITY",
      detail: `Multi-department work can be synchronized into ${block}.`,
      block,
      departments: Array.isArray(departments)
        ? departments.join(" + ")
        : departments,
      duration,
      delay,
      recommendation:
        item.recommendation || "Approve coordinated possession window",
    };
  }

  async function getJSON(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    return await response.json();
  }

  async function loadConflicts() {
    try {
      const data = await getJSON(AI_DC.conflictUrl);

      const list = Array.isArray(data)
        ? data
        : data.conflicts || data.items || data.results || [];

      return list.map(normalizeConflict);
    } catch (error) {
      console.warn("AI-3 conflict feed unavailable:", error);
      return [];
    }
  }

  async function loadCoordination() {
    try {
      const data = await getJSON(AI_DC.coordinationUrl);

      const list = Array.isArray(data)
        ? data
        : data.opportunities ||
          data.coordination_opportunities ||
          data.items ||
          [];

      return list.map(normalizeCoordination);
    } catch (error) {
      console.warn("AI-1 coordination feed unavailable:", error);
      return [];
    }
  }

  function normalizeAdvisory(item) {
    const train = item.train_no || item.train || "TRAIN";
    const type = String(item.type || "ADVISORY").replaceAll("_", " ");
    const rawType = String(item.type || "ADVISORY").toUpperCase();
    const targetSpeed = item.target_speed_kmh;
    const severity = String(
      item.severity || (rawType.includes("HOLD") ? "CRITICAL" : "WARNING")
    ).toUpperCase();
    const recommendation =
      rawType === "HOLD"
        ? `Hold ${train} at the next safe signal`
        : rawType === "SPEED_REGULATION"
          ? `Regulate ${train} to ${targetSpeed ?? 40} km/h`
          : rawType === "BLOCK_APPROACH"
            ? `Reduce ${train} to ${targetSpeed ?? 30} km/h before ${item.block_id || "the active block"}`
            : rawType === "REROUTE_VIA_LOOP"
              ? `Route ${train} via ${item.route_via?.loop_id || "the available loop"}`
              : (item.recommendation || "Follow AI-3 operational advisory");

    return {
      id: item.id || item.advisory_id || `AI3-ADV-${train}-${rawType}-${item.block_id || ""}`,
      source: "AI-3 MANAGE",
      severity,
      title: rawType === "HOLD" ? "TRAIN HOLD ADVISORY" : rawType === "BLOCK_APPROACH" ? "ACTIVE BLOCK APPROACH" : rawType === "REROUTE_VIA_LOOP" ? "LOOP REROUTE ADVISORY" : "TRAFFIC MANAGEMENT ADVISORY",
      detail: `AI-3 recommends ${type.toLowerCase()} for train ${train}. ${item.reason || "Maintain safe operational separation."}`,
      distance: Number(item.headway_km ?? item.distance_km ?? item.distance_to_block_km ?? 0).toFixed(2),
      timeHeadway: item.time_headway_minutes != null ? Number(item.time_headway_minutes).toFixed(2) : null,
      station: item.station || item.section || item.block_id || "CONTROL SECTION",
      recommendation,
      trainA: item.leading_train || "",
      trainB: train,
      trainNo: train,
      action: rawType,
      actualSpeed: Number(item.current_speed_kmh ?? 0),
      targetSpeed: Number(item.target_speed_kmh ?? (rawType === "HOLD" ? 0 : 40)),
    };
  }

  function severityClass(severity) {
    const value = String(severity).toUpperCase();

    if (value.includes("CRITICAL")) return "critical";
    if (value.includes("WARNING")) return "warning";

    return "info";
  }

  function severityChip(severity) {
    const value = String(severity).toUpperCase();

    if (value.includes("CRITICAL")) {
      return `<span class="ai-meta-chip red">CRITICAL</span>`;
    }

    if (value.includes("WARNING")) {
      return `<span class="ai-meta-chip orange">WARNING</span>`;
    }

    return `<span class="ai-meta-chip blue">AI RECOMMENDATION</span>`;
  }

  function renderConflict(item) {
    return `
            <article class="ai-alert-card ${severityClass(item.severity)}">

                <div class="ai-alert-top">
                    <span class="ai-alert-type">
                        ${escapeHTML(item.source)}
                    </span>

                    <span class="ai-alert-time">
                        ${new Date().toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                    </span>
                </div>

                <div class="ai-alert-title">
                    ${escapeHTML(item.title)}
                </div>

                <div class="ai-alert-detail">
                    ${escapeHTML(item.detail)}
                    <br><strong>AI-3 control:</strong> actual ${escapeHTML(item.actualSpeed)} km/h → target ${escapeHTML(item.targetSpeed)} km/h
                </div>

                <div class="ai-alert-meta">
                    ${severityChip(item.severity)}

                    <span class="ai-meta-chip">
                        ${escapeHTML(item.distance)} km separation
                    </span>

                    ${item.timeHeadway ? `<span class="ai-meta-chip">${escapeHTML(item.timeHeadway)} min headway</span>` : ""}

                    <span class="ai-meta-chip">
                        ${escapeHTML(item.station)}
                    </span>

                    <span class="ai-meta-chip orange">
                        ${escapeHTML(item.recommendation)}
                    </span>

                    <span class="ai-meta-chip actual">
                        ACTUAL ${escapeHTML(item.actualSpeed)} km/h
                    </span>

                    <span class="ai-meta-chip target">
                        TARGET ${escapeHTML(item.targetSpeed)} km/h
                    </span>

                    <span class="ai-meta-chip ${item.action === "HOLD" ? "hold" : "action"}">
                        ACTION ${escapeHTML(item.action)}
                    </span>
                </div>

                <div class="ai-dc-actions">

                    <button
                        class="ai-dc-btn accept"
                        data-ai-action="ACCEPT"
                        data-ai-id="${escapeHTML(item.id)}">
                        ✓ ACCEPT
                    </button>

                    <button
                        class="ai-dc-btn override"
                        data-ai-action="OVERRIDE"
                        data-ai-id="${escapeHTML(item.id)}">
                        MANUAL OVERRIDE
                    </button>

                </div>

            </article>
        `;
  }

  function renderCoordination(item) {
    return `
            <article class="ai-alert-card info">

                <div class="ai-alert-top">
                    <span class="ai-alert-type">
                        ${escapeHTML(item.source)}
                    </span>

                    <span class="ai-alert-time">
                        ${new Date().toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                    </span>
                </div>

                <div class="ai-alert-title">
                    ${escapeHTML(item.title)}
                </div>

                <div class="ai-alert-detail">
                    ${escapeHTML(item.detail)}
                </div>

                <div class="ai-alert-meta">

                    <span class="ai-meta-chip green">
                        ${escapeHTML(item.block)}
                    </span>

                    <span class="ai-meta-chip">
                        ${escapeHTML(item.departments)}
                    </span>

                    <span class="ai-meta-chip blue">
                        ${escapeHTML(item.duration)} min
                    </span>

                    <span class="ai-meta-chip orange">
                        ${escapeHTML(item.delay)} min delay
                    </span>

                </div>

                <div class="ai-dc-actions">

                    <button
                        class="ai-dc-btn accept"
                        data-ai-action="ACCEPT"
                        data-ai-id="${escapeHTML(item.id)}">
                        ✓ APPROVE PLAN
                    </button>

                    <button
                        class="ai-dc-btn override"
                        data-ai-action="OVERRIDE"
                        data-ai-id="${escapeHTML(item.id)}">
                        MANUAL OVERRIDE
                    </button>

                </div>

            </article>
        `;
  }

  function renderDecisionCenter() {
    const body = document.querySelector("#ai-dc-body");

    if (!body) return;

    if (!activeAlerts.length) {
      body.innerHTML = `
                <div class="ai-dc-empty">
                    ✓ No active AI intervention required.
                    <br>
                    <small>
                        AI-3 traffic monitor and AI-1 planner are healthy.
                    </small>
                </div>
            `;

      return;
    }

    body.innerHTML = activeAlerts
      .map((item) => {
        if (item.source === "AI-3 MANAGE") {
          return renderConflict(item);
        }

        return renderCoordination(item);
      })
      .join("");

    bindDecisionActions();
  }

  function bindDecisionActions() {
    document.querySelectorAll("[data-ai-action]").forEach((button) => {
      button.addEventListener("click", async function () {
        const action = this.dataset.aiAction;
        const decisionId = this.dataset.aiId;

        await submitOperatorDecision(decisionId, action, this);
      });
    });
  }

  async function submitOperatorDecision(decisionId, action, button) {
    const originalText = button.textContent;

    button.disabled = true;
    button.textContent = "PROCESSING...";

    const payload = {
      decision_id: decisionId,
      action: action,
      operator: "CONTROL_OFFICER",
      timestamp: new Date().toISOString(),
      source: "RAIL-OPTIMAX-AI-DECISION-CENTER",
    };

    try {
      const response = await fetch(AI_DC.operatorUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }

      const execution = (await response.clone().json().catch(() => ({})))?.record?.execution;
      showDecisionToast(
        action === "ACCEPT"
          ? (execution?.status === "APPLIED"
              ? `AI-3 ${execution.action || "CONTROL"} applied to train ${execution.train_no}.`
              : "AI recommendation accepted and logged; live controller remains authoritative.")
          : "Manual override recorded in audit trail.",
      );

      acknowledgedDecisionIds.add(decisionId);
      activeAlerts = activeAlerts.filter((item) => item.id !== decisionId);

      renderDecisionCenter();
    } catch (error) {
      /*
       * Demo-safe fallback:
       * UI still records the operator interaction locally
       * if backend audit endpoint is temporarily unavailable.
       */

      console.warn(
        "Operator API unavailable. Local demo acknowledgement used.",
        error,
      );

      showDecisionToast(
        `${action} recorded locally — backend audit endpoint unavailable.`,
      );

      acknowledgedDecisionIds.add(decisionId);
      activeAlerts = activeAlerts.filter((item) => item.id !== decisionId);

      renderDecisionCenter();
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function showDecisionToast(message) {
    document.querySelectorAll(".ai-dc-toast").forEach((el) => el.remove());

    const toast = document.createElement("div");

    toast.className = "ai-dc-toast";
    toast.textContent = message;

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.remove();
    }, 3200);
  }

  function conflictMatchesLiveState(conflict, snapshot) {
    const trains = Array.isArray(snapshot?.trains) ? snapshot.trains : [];
    const lead = trains.find(t => String(t.train_no) === String(conflict.trainA));
    const trail = trains.find(t => String(t.train_no) === String(conflict.trainB));
    if (!lead || !trail) return true;
    if (lead.track !== trail.track || lead.direction !== trail.direction) return false;
    const leadKm = Number(lead.current_km);
    const trailKm = Number(trail.current_km);
    if (!Number.isFinite(leadKm) || !Number.isFinite(trailKm)) return false;
    // UP: larger KM is ahead. DN: smaller KM is ahead.
    const leadIsAhead = trail.direction === "UP" ? leadKm >= trailKm : leadKm <= trailKm;
    if (!leadIsAhead) return false;
    const liveGap = Math.abs(leadKm - trailKm);
    // Drop a stale endpoint conflict once the live state has safely separated.
    if (liveGap >= 1.8 && String(conflict.severity).toUpperCase() !== "CRITICAL") return false;
    return true;
  }

  function updateFromTelemetry(snapshot) {
    lastSnapshot = snapshot || null;
    lastTelemetryAt = Date.now();
    setLiveState("live");
    const ai3 = snapshot?.ai3 || {};
    const rawConflicts = Array.isArray(ai3.conflicts) ? ai3.conflicts : [];
    const rawAdvisories = Array.isArray(ai3.advisories) ? ai3.advisories : [];

    const advisories = rawAdvisories.map(normalizeAdvisory);
    const advisoryByTrain = new Map();
    for (const advisory of advisories) {
      const existing = advisoryByTrain.get(advisory.trainB);
      if (!existing || advisory.severity === "CRITICAL" || advisory.action === "HOLD") {
        advisoryByTrain.set(advisory.trainB, advisory);
      }
    }

    const conflicts = rawConflicts
      .map((raw) => normalizeConflict(raw, snapshot))
      .filter(conflict => conflictMatchesLiveState(conflict, snapshot))
      .map((conflict) => {
        const linked = advisoryByTrain.get(conflict.trainB);
        if (linked) {
          conflict.recommendation = linked.recommendation;
          conflict.action = linked.action;
          conflict.severity = conflict.severity || linked.severity;
        }
        return conflict;
      });

    const activeConflictIds = new Set(conflicts.map((item) => item.id));
    for (const id of [...acknowledgedDecisionIds]) {
      if (!activeConflictIds.has(id)) acknowledgedDecisionIds.delete(id);
    }

    // A conflict card already contains its linked train advisory. Do not show
    // a second card for the same train/action; show only standalone advisories.
    const conflictedTrains = new Set(conflicts.map((item) => item.trainB));
    const standaloneAdvisories = advisories.filter((item) => !conflictedTrains.has(item.trainB));

    const plan = snapshot?.ai1 || {};
    const summary = plan.summary || {};
    const ai1 = summary.active_blocks_considered ? [{
      id: `AI1-${summary.generated_at_sequence || snapshot?.sequence || 0}`,
      source: "AI-1 PLAN", severity: "INFO", title: "MAINTENANCE-AWARE PLAN",
      detail: `${summary.affected_trains || 0} train(s) affected by ${summary.active_blocks_considered || 0} active possession(s).`,
      block: (snapshot?.active_blocks || [])[0]?.block_id || "B-NEW",
      departments: (snapshot?.active_blocks || [])[0]?.bundled_departments?.join(" + ") || "Maintenance coordination",
      duration: (snapshot?.active_blocks || [])[0]?.duration_minutes || 0,
      delay: summary.total_planned_delay_minutes || 0,
      recommendation: "Review AI-1 plan in OCC"
    }] : [];

    activeAlerts = [...conflicts, ...standaloneAdvisories, ...ai1]
      .filter((item) => !acknowledgedDecisionIds.has(item.id))
      .filter((item, index, arr) => arr.findIndex(x => x.id === item.id) === index)
      .slice(0, 6);

    lastRefresh = new Date();
    renderDecisionCenter();

    const status = document.querySelector("#ai-dc-status");
    if (status) {
      status.textContent = `Live telemetry #${snapshot?.sequence ?? 0} · ${conflicts.length} conflict(s) · ${advisories.length} advisory(s)`;
      status.className = "ai-dc-status-live";
    }
  }

  async function refreshDecisionCenter() {
    // When fresh telemetry is present, it is the single source of truth for
    // physical train state. Avoid racing the WebSocket with an independent
    // /ai/manage evaluation that can describe the previous tick.
    if (lastSnapshot && (Date.now() - lastTelemetryAt) < 5000) {
      updateFromTelemetry(lastSnapshot);
      return activeAlerts;
    }
    try {
      const [manageResult, coordinationResult] = await Promise.allSettled([
        getJSON(AI_DC.conflictUrl),
        getJSON(AI_DC.coordinationUrl),
      ]);
      if (manageResult.status !== "fulfilled") {
        throw manageResult.reason || new Error("AI-3 endpoint unavailable");
      }
      const manage = manageResult.value;
      const coordination = coordinationResult.status === "fulfilled" ? coordinationResult.value : [];

      const conflicts = (Array.isArray(manage) ? manage : manage?.conflicts || [])
        .map(item => normalizeConflict(item, lastSnapshot))
        .filter(conflict => conflictMatchesLiveState(conflict, lastSnapshot));
      const advisories = (Array.isArray(manage) ? [] : manage?.advisories || [])
        .map(normalizeAdvisory);
      const coordinationItems = (Array.isArray(coordination) ? coordination : coordination?.opportunities || [])
        .map(normalizeCoordination);

      const advisoryByTrain = new Map();
      for (const advisory of advisories) {
        const existing = advisoryByTrain.get(advisory.trainB);
        if (!existing || advisory.severity === "CRITICAL" || advisory.action === "HOLD") {
          advisoryByTrain.set(advisory.trainB, advisory);
        }
      }
      for (const conflict of conflicts) {
        const linked = advisoryByTrain.get(conflict.trainB);
        if (linked) {
          conflict.recommendation = linked.recommendation;
          conflict.action = linked.action;
          conflict.severity = conflict.severity || linked.severity;
        }
      }

      const conflictedTrains = new Set(conflicts.map(item => item.trainB));
      const standalone = advisories.filter(item => !conflictedTrains.has(item.trainB));
      activeAlerts = [...conflicts, ...standalone, ...coordinationItems]
        .filter(item => !acknowledgedDecisionIds.has(item.id))
        .filter((item, index, arr) => arr.findIndex(x => x.id === item.id) === index)
        .slice(0, 6);

      lastRefresh = new Date();
      renderDecisionCenter();
      const status = document.querySelector("#ai-dc-status");
      if (status) {
        status.textContent = `AI-3 live · ${conflicts.length} conflict(s) · ${advisories.length} advisory(s)`;
        status.className = "ai-dc-status-live";
        lastTelemetryAt = Date.now();
        setLiveState("live");
      }
      return activeAlerts;
    } catch (error) {
      console.warn("AI-3 refresh failed; waiting for telemetry:", error);
      return [];
    }
  }

  function setLiveState(state) {
    const indicator = document.querySelector("#ai-dc-live-indicator");
    const label = document.querySelector("#ai-dc-live-label");
    const status = document.querySelector("#ai-dc-status");
    if (!indicator || !label) return;
    indicator.classList.remove("is-stale", "is-offline");
    if (state === "offline") {
      indicator.classList.add("is-offline");
      label.textContent = "OFFLINE";
      if (status) { status.className = "ai-dc-status-offline"; status.textContent = "AI-3 feed unavailable"; }
    } else if (state === "stale") {
      indicator.classList.add("is-stale");
      label.textContent = "STALE";
      if (status) { status.className = "ai-dc-status-stale"; status.textContent = "Waiting for fresh telemetry…"; }
    } else {
      label.textContent = "LIVE";
      if (status) status.className = "ai-dc-status-live";
    }
  }

  function startDecisionCenter() {
    decisionCenter = createDecisionCenter();
    if (!decisionCenter) return;
    const initial = document.querySelector("#ai-dc-status");
    if (initial) initial.textContent = "Connecting to AI-3…";

    // Do not depend exclusively on the map's CustomEvent bridge. The OCC
    // decision panel is a first-class consumer of AI-3 and periodically
    // refreshes from the authoritative backend endpoint.
    refreshDecisionCenter();
    clearInterval(fallbackPollTimer);
    clearInterval(staleTimer);
    staleTimer = setInterval(() => {
      if (!lastTelemetryAt) return;
      const age = Date.now() - lastTelemetryAt;
      if (age > 10000) setLiveState("offline");
      else if (age > 4000) setLiveState("stale");
      else setLiveState("live");
    }, 1000);
    fallbackPollTimer = setInterval(() => {
      if (document.visibilityState !== "hidden") refreshDecisionCenter();
    }, 3000);
  }

  window.addEventListener("rail-telemetry", (event) => {
    if (decisionCenter) updateFromTelemetry(event.detail);
  });

  /*
   * Start after existing dashboard rendering.
   */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startDecisionCenter);
  } else {
    startDecisionCenter();
  }
})();

