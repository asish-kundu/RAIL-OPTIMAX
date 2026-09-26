import { submitMaintenanceQuery, renderSubmittedQueriesTable } from "./maintenance.js";

let lastRailSnapshot = null;
let scheduleMode = "train";

function renderMaintenanceSchedule(snapshot){
  const mount=document.getElementById("maintenance-schedule-list");
  if(!mount)return;
  const tasks=Array.isArray(snapshot?.maintenance)?snapshot.maintenance:[];
  const blocks=Array.isArray(snapshot?.active_blocks)?snapshot.active_blocks:[];
  const blockById=new Map(blocks.map(b=>[String(b.block_id),b]));
  mount.replaceChildren();
  if(!tasks.length){
    mount.innerHTML='<div class="maintenance-empty">No maintenance records available.</div>';
    return;
  }
  const statusClass=(status)=>String(status||"").toLowerCase().replaceAll("_","-").replaceAll(" ","-");
  for(const task of tasks){
    const row=document.createElement("article");
    row.className=`maintenance-schedule-row ${statusClass(task.status)}`;
    const head=document.createElement("div"); head.className="maintenance-schedule-head";
    const id=document.createElement("b"); id.textContent=task.query_id||"TASK";
    const status=document.createElement("span"); status.className="maintenance-status"; status.textContent=task.status||"Under Review";
    head.append(id,status);
    const main=document.createElement("div"); main.className="maintenance-schedule-main";
    const title=document.createElement("strong"); title.textContent=`${task.asset_type||"Asset"} · ${task.maintenance_type||"Maintenance"}`;
    const meta=document.createElement("small");
    meta.textContent=`${task.department||"—"} · KM ${Number(task.location_from_km||0).toFixed(1)}–${Number(task.location_to_km||0).toFixed(1)} · ${task.preferred_date||"—"} · ${task.preferred_window||"—"}`;
    main.append(title,meta);
    const foot=document.createElement("div"); foot.className="maintenance-schedule-foot";
    const details=document.createElement("span"); details.textContent=`${task.duration_minutes||0} min · ${task.priority||"—"} · ${task.assigned_block_id||"No block assigned"}`;
    const emergency=document.createElement("span"); emergency.className=task.emergency?"maintenance-emergency":"maintenance-normal"; emergency.textContent=task.emergency?"EMERGENCY":"SCHEDULED";
    foot.append(details,emergency);
    row.append(head,main,foot);
    if(task.assigned_block_id){
      row.addEventListener("click",()=>window.RAIL_OPTIMAX_MAP?.focusBlock?.(task.assigned_block_id));
    }
    mount.append(row);
  }
}

function setScheduleMode(mode){
  scheduleMode=mode;
  document.querySelectorAll("[data-schedule]").forEach(t=>t.classList.toggle("active",t.dataset.schedule===mode));
  const train=document.getElementById("live-schedule-list");
  const maintenance=document.getElementById("maintenance-schedule-list");
  const eyebrow=document.getElementById("schedule-panel-eyebrow");
  if(train)train.hidden=mode!=="train";
  if(maintenance)maintenance.hidden=mode!=="maintenance";
  if(eyebrow)eyebrow.textContent=mode==="maintenance"?"MAINTENANCE REGISTER · LIVE":"LIVE TRAIN STATE";
  if(mode==="maintenance")renderMaintenanceSchedule(lastRailSnapshot);
}

function renderLivePanels(snapshot){
  lastRailSnapshot=snapshot||null;
  const trains=Array.isArray(snapshot?.trains)?snapshot.trains:[];
  const blocks=Array.isArray(snapshot?.active_blocks)?snapshot.active_blocks:[];
  const planned=Array.isArray(snapshot?.planned_blocks)?snapshot.planned_blocks:[];
  const ai3=snapshot?.ai3||{};
  const schedule=document.getElementById("live-schedule-list");
  if(schedule){
    const controls=ai3?.controls||{};
    const priorityScore=t=>{const rc=t.route_control||{};const action=controls[String(t.train_no)]?.action||"";return (rc.mode==="LOOP"?100:0)+(action==="HOLD"?80:0)+(t.block_context?50:0)+(action==="SPEED_REGULATION"||action==="BLOCK_APPROACH"?30:0);};
    const up=[...trains].filter(t=>t.track==='UP_LINE').sort((a,b)=>priorityScore(b)-priorityScore(a)||Number(a.current_km)-Number(b.current_km)).slice(0,5);
    const dn=[...trains].filter(t=>t.track==='DN_LINE').sort((a,b)=>priorityScore(b)-priorityScore(a)||Number(a.current_km)-Number(b.current_km)).slice(0,5);
    const sorted=[...up,...dn];
    const makeGroup=(label)=>{const h=document.createElement("div");h.className="schedule-group-label";h.textContent=label;return h;};
    const rows=[];
    rows.push(makeGroup(`UP LINE · ${up.length}`));
    up.forEach(t=>rows.push(t));
    rows.push(makeGroup(`DN LINE · ${dn.length}`));
    dn.forEach(t=>rows.push(t));
    schedule.replaceChildren(...rows.map(t=>{
      if(t.nodeType===1)return t;
      const row=document.createElement("div");row.className="schedule-row";
      const dot=document.createElement("span");dot.className="status-dot "+(t.status?.includes("HOLD")?"red":t.status?.includes("CAUTION")||t.block_context?"amber":"green");
      const body=document.createElement("div");const title=document.createElement("b");title.textContent=`${t.train_no} · ${t.direction==='UP'?'UP':'DN'}`;const rc=t.route_control||{};const action=controls[String(t.train_no)]?.action||"";const routeState=rc.mode==="LOOP"?(rc.status==="ON_LOOP"?`↗ ${rc.via?.loop_id||"LOOP"}`:`↗ TO ${rc.via?.loop_id||"LOOP"}`):(action&&action!=="NORMAL"?action.replaceAll("_"," "):"MAIN LINE");const small=document.createElement("small");const source=t.origin||"SDAH";const destination=t.destination||"BP";const sourceName=source==="SDAH"?"Sealdah":source==="BP"?"Barrackpore":source;const destName=destination==="SDAH"?"Sealdah":destination==="BP"?"Barrackpore":destination;small.textContent=`${sourceName} → ${destName} · KM ${Number(t.current_km).toFixed(1)} · ${routeState}`;body.append(title,small);
      const time=document.createElement("time");time.textContent=`${Number(t.effective_speed_kmh??t.speed_kmh).toFixed(0)} km/h`;row.append(dot,body,time);return row;}));
  }
  const activeEl=document.getElementById("active-block-count");if(activeEl)activeEl.textContent=String(blocks.length);
  const pendingEl=document.getElementById("pending-review-count");if(pendingEl)pendingEl.textContent=String(planned.length+(blocks.filter(b=>b.status==='PENDING_SAFETY').length));
  const countEl=document.getElementById("track-runtime-count");if(countEl)countEl.textContent=`${snapshot?.corridor?.stations?.length||0} stations · ${trains.length} trains · ${blocks.length} active blocks`;
  const sync=document.getElementById("schedule-sync-status");if(sync){const rerouted=trains.filter(t=>(t.route_control||{}).mode==="LOOP").length;sync.textContent=`Telemetry #${snapshot?.sequence??0} · ${trains.length} live · ${rerouted} rerouted`; }

  const workList=document.getElementById("active-work-list");
  const workSummary=document.getElementById("active-work-summary");
  if(workList){
    if(!blocks.length){
      workList.innerHTML='<div class="active-work-empty">No active maintenance / possession</div>';
    } else {
      workList.replaceChildren(...blocks.map((b,i)=>{
        const row=document.createElement("div"); row.className=`active-work-row work-color-${i%6}`;
        const title=document.createElement("div"); title.className="active-work-title";
        const dot=document.createElement("span"); dot.className="work-color-dot";
        const name=document.createElement("b"); name.textContent=b.block_id||`BLOCK-${i+1}`;
        title.append(dot,name);
        const status=document.createElement("span"); status.className="work-status"; status.textContent=b.status||"Active";
        title.append(status);
        const meta=document.createElement("div"); meta.className="active-work-meta";
        const type=b.disruption_type||b.maintenance_type||"Maintenance";
        const track=b.target_track||"CORRIDOR";
        const from=Number(b.location_from_km),to=Number(b.location_to_km);
        const range=Number.isFinite(from)&&Number.isFinite(to)?`KM ${from.toFixed(1)}–${to.toFixed(1)}`:"KM —";
        meta.textContent=`${type} · ${track.replace("_LINE", "")} · ${range}`;
        row.append(title,meta);
        row.addEventListener("click",()=>window.RAIL_OPTIMAX_MAP?.focusBlock?.(b.block_id));
        return row;
      }));
    }
  }
  if(workSummary)workSummary.textContent=blocks.length?`${blocks.length} active · ${new Set(blocks.map(b=>b.target_track)).size} route(s)`:'All clear';

  // 2nd Management = traffic-control desk, intentionally separate from maintenance desk.
  const controls=ai3?.controls||{};
  const controlEntries=Object.entries(controls);
  const loopTrains=trains.filter(t=>(t.route_control||{}).mode==="LOOP");
  const holdCount=controlEntries.filter(([,c])=>c?.action==="HOLD").length;
  const speedCount=controlEntries.filter(([,c])=>c?.action==="SPEED_REGULATION"||c?.action==="BLOCK_APPROACH").length;
  const normalCount=Math.max(0,trains.length-holdCount-speedCount-loopTrains.length);
  const setText=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=String(value);};
  setText("ai3-active-control-count", controlEntries.length);
  setText("ai3-reroute-count", loopTrains.length);
  setText("ai3-hold-count", holdCount);
  setText("ai3-speed-count", speedCount);
  setText("ai3-loop-count", loopTrains.length);
  setText("ai3-normal-count", normalCount);
  setText("ai3-control-summary", `${controlEntries.length} active · ${loopTrains.length} routed`);
  const controlList=document.getElementById("ai3-control-list");
  if(controlList){
    const priority=[...trains].filter(t=>{
      const a=controls[String(t.train_no)]?.action;
      return (a&&a!=="NORMAL") || (t.route_control||{}).mode==="LOOP";
    }).sort((a,b)=>{
      const wa=(a.route_control||{}).mode==="LOOP"?3:(controls[String(a.train_no)]?.action==="HOLD"?2:1);
      const wb=(b.route_control||{}).mode==="LOOP"?3:(controls[String(b.train_no)]?.action==="HOLD"?2:1);
      return wb-wa;
    }).slice(0,6);
    if(!priority.length) controlList.innerHTML='<div class="active-work-empty">No exceptional traffic control · all trains operating normally</div>';
    else controlList.replaceChildren(...priority.map(t=>{
      const row=document.createElement("div"); row.className="ai3-control-row";
      const rc=t.route_control||{}; const c=controls[String(t.train_no)]||{};
      const action=rc.mode==="LOOP"?(rc.status==="ON_LOOP"?`ON ${rc.via?.loop_id||"LOOP"}`:`TO ${rc.via?.loop_id||"LOOP"}`):(c.action||"CONTROLLED");
      const name=document.createElement("b"); name.textContent=String(t.train_no);
      const meta=document.createElement("span"); meta.textContent=`${t.direction||""} · ${action.replaceAll("_"," ")}`;
      const speed=document.createElement("small"); speed.textContent=`${Number(t.effective_speed_kmh??t.speed_kmh??0).toFixed(0)} km/h`;
      row.append(name,meta,speed); return row;
    }));
  }
}

window.addEventListener("rail-telemetry",e=>renderLivePanels(e.detail));

document.addEventListener("DOMContentLoaded", async () => {
  const modeSwitch=document.getElementById("modeSwitch"), controlView=document.getElementById("controlView"), departmentView=document.getElementById("departmentView"), btnNewQuery=document.getElementById("btnNewQuery");
  const setMode=(mode)=>{if(mode==="department"){controlView.style.display="none";departmentView.style.display="flex";if(modeSwitch)modeSwitch.value="department";}else{controlView.style.display="flex";departmentView.style.display="none";if(modeSwitch)modeSwitch.value="control";}};
  modeSwitch?.addEventListener("change",e=>setMode(e.target.value)); btnNewQuery?.addEventListener("click",()=>setMode("department"));
  try{const r=await fetch("./maintenance/",{cache:"no-store"});if(r.ok)renderSubmittedQueriesTable("department-queries-table-mount",await r.json());}catch(_){/* presentation mode intentionally works without backend */}

  document.querySelectorAll("[data-schedule]").forEach(tab=>tab.addEventListener("click",()=>setScheduleMode(tab.dataset.schedule||"train")));
  setScheduleMode("train");
  document.querySelectorAll("[data-management]").forEach(tab=>tab.addEventListener("click",()=>{
    document.querySelectorAll("[data-management]").forEach(t=>t.classList.toggle("active",t===tab));
    const first=document.getElementById("management-first-view");
    const second=document.getElementById("management-second-view");
    const isSecond=tab.dataset.management==="second";
    if(first) first.hidden=isSecond;
    if(second) second.hidden=!isSecond;
  }));
  document.getElementById("end-management")?.addEventListener("click",()=>{const panel=document.getElementById("management-content");if(panel)panel.innerHTML='<div class="management-ended">✓<h2>Management Session Ended</h2><p>Live coordination paused. Reopen a management tab to continue.</p></div>';});

  document.getElementById("run-ai-plan")?.addEventListener("click",async()=>{
    const output=document.getElementById("ai-output-content"); if(!output)return; output.innerHTML='<div class="output-empty-icon">⟳</div><b>AI-1 PLAN is calculating…</b><p>Checking maintenance windows, train conflicts and safety constraints.</p>';
    try{
      const plan=await window.RAIL_OPTIMAX_MAP?.runPlan();
      const s=plan?.summary||{};
      const actions=Array.isArray(plan?.actions)?plan.actions:[];
const liveTrains=Array.isArray(lastRailSnapshot?.trains)?lastRailSnapshot.trains:[];
const routeName=(code)=>({SDAH:"Sealdah",BP:"Barrackpore"}[String(code)]||String(code||"—"));

const actionByTrain=new Map(actions.map(a=>[String(a.train_no),a]));

const scheduleTrains=[...liveTrains].sort((a,b)=>{
  const da=String(a.direction||"");
  const db=String(b.direction||"");
  if(da!==db)return da==="UP"?-1:1;
  return Number(a.current_km??0)-Number(b.current_km??0);
});

const rows=scheduleTrains.map(t=>{
  const a=actionByTrain.get(String(t.train_no));
  const rawAction=String(a?.action||"NORMAL");
  const action=rawAction.replaceAll("_"," ");

  const rc=t.route_control||{};
  const route=a?.loop_id
    ? `↗ ${a.loop_id}`
    : rc.mode==="LOOP"
      ? `↗ ${rc.via?.loop_id||"LOOP"}`
      : (a?.route_status&&a.route_status!=="MAIN_LINE"
        ? a.route_status.replaceAll("_"," ")
        : "MAIN LINE");

  const status=a ? action : (String(t.status||"").trim() || "ON TIME");

  const chipClass=a
    ? (action.includes("HOLD")?"danger":action.includes("SPEED")?"warn":"normal")
    : "normal";

  const speed=Number(t.effective_speed_kmh??t.speed_kmh??0);

  return `<div class="ai-plan-row">
    <div class="ai-plan-main">
      <b>${t.train_no} · ${t.train_name||"Train"}</b>
      <span>${routeName(t.origin||t.source||"SDAH")} → ${routeName(t.destination||"BP")} · ${t.direction||""}</span>
    </div>
    <div class="ai-plan-km">KM ${Number(t.current_km??0).toFixed(1)}</div>
    <div class="ai-plan-action">
      <span class="ai-plan-action-chip ${chipClass}">${status}</span>
      <small>${a?.delay_minutes||0} min · ${speed.toFixed(0)} km/h</small>
    </div>
    <div class="ai-plan-reason">
      ${a ? `${a.block_id?`Block ${a.block_id} · `:""}${a.reason||"AI-1 operational action"}` : "No additional restriction — scheduled normally"}
    </div>
  </div>`;
}).join("");
      output.innerHTML=`<div class="output-result ai-plan-result">
        <div class="ai-plan-head"><div><span class="soft-badge">PLAN GENERATED</span><h4>Conflict-aware train schedule</h4><p>AI-1 considered active maintenance, headway and current live train state.</p></div><button class="outline-action" id="refresh-ai-plan">↻ Recalculate</button></div>
        <div class="output-metrics"><span><b>${s.affected_trains??0}</b> affected trains</span><span><b>${s.total_planned_delay_minutes??0}</b> min planned impact</span><span><b>${s.active_blocks_considered??0}</b> active blocks</span><span><b>${s.maintenance_tasks_considered??0}</b> maintenance tasks</span></div>
        <div class="ai-plan-list">${rows||'<div class="ai-plan-empty">No train actions required — all routes clear.</div>'}</div>
      </div>`;
      document.getElementById("refresh-ai-plan")?.addEventListener("click",()=>document.getElementById("run-ai-plan")?.click());
    }catch(error){
      output.innerHTML='<div class="output-result"><span class="soft-badge">PLAN DEGRADED</span><h4>Safe fallback active</h4><p>The OCC remains operational using the deterministic fallback planner.</p></div>';
      console.warn(error);
    }
  });

  const emergencyDept=document.getElementById("quick-emergency-dept");
  const emergencyAsset=document.getElementById("quick-emergency-asset");
  const oheWrap=document.getElementById("ohe-isolation-wrap");
  const syncEmergencyAsset=()=>{
    const isOhe=emergencyAsset?.value==="Catenary Wire" || emergencyDept?.value==="Traction (OHE)";
    if(isOhe && emergencyAsset) emergencyAsset.value="Catenary Wire";
    if(emergencyDept?.value==="S&T (Signalling)" && emergencyAsset) emergencyAsset.value="Signal / Point";
    if(emergencyDept?.value==="Engineering (Track)" && emergencyAsset?.value==="Catenary Wire") emergencyAsset.value="Track Section";
    if(oheWrap)oheWrap.hidden=!isOhe;
  };
  emergencyDept?.addEventListener("change",syncEmergencyAsset); emergencyAsset?.addEventListener("change",syncEmergencyAsset); syncEmergencyAsset();

  document.getElementById("emergency-submit")?.addEventListener("click",async()=>{
    const dept=document.getElementById("quick-emergency-dept")?.value||"Engineering (Track)";
    const asset=document.getElementById("quick-emergency-asset")?.value||"Track Section";
    const track=document.getElementById("quick-emergency-track")?.value||"UP_LINE";
    const km=Number.parseFloat(document.getElementById("quick-emergency-km")?.value||"");
    const toKm=Number.parseFloat(document.getElementById("quick-emergency-to-km")?.value||"");
    const duration=Number(document.getElementById("quick-emergency-duration")?.value||60);
    const description=document.getElementById("quick-emergency-description")?.value||`${asset} emergency at KM ${km}`;
    const resultBox=document.getElementById("emergency-result");
    if(!Number.isFinite(km)||km<0||km>25){if(resultBox)resultBox.textContent="Enter a corridor KM between 0 and 25.";return;}
    if(!Number.isFinite(toKm)||toKm<=km||toKm>25){if(resultBox)resultBox.textContent="To KM must be greater than From KM and within 25 KM.";return;}
    const button=document.getElementById("emergency-submit"); if(button)button.disabled=true;
    if(resultBox)resultBox.textContent="AI-2 processing emergency → safety check → AI-1 replan → AI-3 control…";
    try{
      const result=await window.RAIL_OPTIMAX_MAP?.injectEmergency({department:dept,asset_type:asset,target_track:track,location_km:km,location_to_km:toKm,duration_minutes:duration,description,disruption_type:`Emergency ${asset}`,ohe_isolated:Boolean(document.getElementById("quick-emergency-ohe-isolated")?.checked),requires_power_block:asset==="Catenary Wire",requires_traffic_block:true});
      const controls=Object.keys(result?.ai3_live_controls||{}).length;
      if(resultBox)resultBox.textContent=`${result?.status||"PROCESSED"} · ${result?.maintenance_task?.query_id||"EMERGENCY"} · ${result?.emergency_block?.block_id||"—"} · ${result?.affected_trains?.length||0} train(s) affected · ${controls} AI-3 control(s)`;
      setScheduleMode("maintenance");
    }catch(error){
      console.error(error); if(resultBox)resultBox.textContent=`Emergency rejected: ${error.message||"backend unavailable"}`;
    }finally{if(button)button.disabled=false;}
  });

  const form=document.getElementById("new-maintenance-form");
  form?.addEventListener("submit",async e=>{e.preventDefault();const payload={department:document.getElementById("dept-selector-input").value,location_from_km:Number(document.getElementById("km-from-input").value),location_to_km:Number(document.getElementById("km-to-input").value),asset_type:document.getElementById("asset-type-input").value,maintenance_type:document.getElementById("maint-type-input").value,priority:document.getElementById("priority-input").value,duration_minutes:Number(document.getElementById("duration-input").value),preferred_date:document.getElementById("date-input").value,preferred_window:document.getElementById("time-window-input").value,resources:document.getElementById("resources-input").value,emergency:document.getElementById("emergency-toggle-yes").checked,description:document.getElementById("description-input").value,requires_power_block:false,requires_traffic_block:true};try{const res=await submitMaintenanceQuery(payload);alert(`Maintenance requirement lodged under ID: ${res.query_id}`);}catch(_){alert("Presentation mode: maintenance request captured locally for demonstration.");}});
});
