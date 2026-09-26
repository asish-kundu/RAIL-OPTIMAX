import { PresentationRuntime } from "./demo-runtime.js";

(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const VIEW = { width: 1440, height: 465, startX: 22, endX: 1410, upY: 66, dnY: 84 };
  const state = { mode:"BOOT", connected:false, selectedTrain:null, selectedBlock:null, trains:[], blocks:[], stations:[], sequence:0, ws:null, wsTimer:null, reconnectTimer:null, demo:null, visualKm:new Map(), targetKm:new Map(), paused:false, routeMode:false, blockMode:false, ai3:{controls:{},signals:[]}, };
  let parts = null;
  const num=(v,f=0)=>{const n=Number(v);return Number.isFinite(n)?n:f;};
  const svgEl=(tag,attrs={},text="")=>{const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text)n.textContent=text;return n;};
  const htmlEl=(tag,attrs={},text="")=>{const n=document.createElement(tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text)n.textContent=text;return n;};

  function xForKm(km, direction="UP"){
    if(!state.stations.length) return VIEW.startX + Math.max(0,Math.min(25,num(km)))/25*(VIEW.endX-VIEW.startX);
    const stations=[...state.stations].sort((a,b)=>num(a.km)-num(b.km));
    const k=Math.max(0,Math.min(25,num(km)));
    for(let i=0;i<stations.length-1;i++){
      const a=stations[i],b=stations[i+1],ak=num(a.km),bk=num(b.km);
      if(k>=ak && k<=bk){const ax=num(a.map?.[direction==='DN'?'dn_x':'up_x'],VIEW.startX+ak/25*(VIEW.endX-VIEW.startX));const bx=num(b.map?.[direction==='DN'?'dn_x':'up_x'],VIEW.startX+bk/25*(VIEW.endX-VIEW.startX));return ax+(bx-ax)*((k-ak)/(bk-ak||1));}
    }
    const last=stations.at(-1);return num(last?.map?.[direction==='DN'?'dn_x':'up_x'],VIEW.endX);
  }
  function visualPosition(t, km){
    const mainY=t?.track==="DN_LINE"?VIEW.dnY:VIEW.upY;
    const rc=t?.route_control||{};
    if(rc.mode!=="LOOP" || !rc.via || !["ON_LOOP","DIVERSION_PENDING","REJOINED"].includes(rc.status)){
      return {x:xForKm(km,t?.direction||"UP"),y:mainY};
    }
    const entry=Number(rc.via.entry_km ?? km);
    const exit=Number(rc.via.exit_km ?? entry);
    const span=Math.max(0.01,Math.abs(exit-entry));
    // The backend owns loop_progress_km. Never infer loop position from
    // current_km because current_km is still the corridor reference KM used
    // for signalling/block logic. This keeps the train marker physically on
    // the same loop path as the reroute overlay.
    const progressKm=Number.isFinite(Number(rc.loop_progress_km))
      ? Number(rc.loop_progress_km)
      : Math.max(0,Math.min(span,Math.abs(Number(km)-entry)));
    const progress=Math.max(0,Math.min(1,progressKm/span));
    const x1=xForKm(entry,t.direction),x2=xForKm(exit,t.direction);
    const loopY=Number(rc.via[t.direction==='UP'?'map_y_up':'map_y_dn'] ?? 156);
    if(rc.status==='DIVERSION_PENDING') return {x:xForKm(km,t.direction),y:mainY};
    if(rc.status==='REJOINED') return {x:x2,y:mainY};
    return {x:x1+(x2-x1)*progress,y:loopY};
  }
  const yForTrain=t=>visualPosition(t,num(t?.current_km)).y;

  function buildMap(container){
    container.classList.add("live-map","operational-map");container.replaceChildren();
    const base=htmlEl("img",{src:"./assets/uploaded-corridor-map.svg",alt:"RAIL-OPTIMAX custom railway corridor schematic",draggable:"false"});
    const toolbar=htmlEl("div",{class:"map-live-toolbar"});
    const connection=htmlEl("span",{class:"map-live-pill",id:"map-connection"});connection.append(htmlEl("i"),document.createTextNode(" STARTING OCC FEED"));
    const fit=htmlEl("button",{type:"button"},"↔ Fit");const pause=htmlEl("button",{type:"button"},"Ⅱ Pause");const routeBtn=htmlEl("button",{type:"button",class:"map-action-button"},"Highlight Active Route");const blockBtn=htmlEl("button",{type:"button",class:"map-action-button"},"Block Selected Track");const clearBtn=htmlEl("button",{type:"button",class:"map-action-button"},"Clear Map Status");const demo=htmlEl("button",{type:"button",class:"map-demo-button"},"▶ Presentation");toolbar.append(connection,fit,pause,routeBtn,blockBtn,clearBtn,demo);
    const readout=htmlEl("div",{class:"map-live-readout"});const title=htmlEl("b",{},"LIVE OPERATIONAL MAP");const subtitle=htmlEl("span",{},"Initializing telemetry…");const occupancy=htmlEl("div",{class:"map-route-occupancy"});readout.append(title,subtitle,occupancy);
    const selection=htmlEl("aside",{class:"map-train-detail",id:"map-train-detail","aria-live":"polite"});const detailTitle=htmlEl("b",{},"LIVE TRAIN INSPECTOR");const detailBody=htmlEl("span",{},"Click any moving train marker to inspect its live operational state.");selection.append(detailTitle,detailBody);
    const svg=svgEl("svg",{class:"map-action-layer",viewBox:`0 0 ${VIEW.width} ${VIEW.height}`,preserveAspectRatio:"xMidYMid meet",role:"img","aria-label":"Live operational overlay"});
    const defs=svgEl("defs");const shadow=svgEl("filter",{id:"liveTrainShadow",x:"-60%",y:"-60%",width:"220%",height:"220%"});shadow.append(svgEl("feDropShadow",{dx:0,dy:2,stdDeviation:2,"flood-color":"#0f172a","flood-opacity":.3}));defs.append(shadow);svg.append(defs);
    const routeLayer=svgEl("g",{class:"operational-routes"}),signalLayer=svgEl("g",{class:"operational-signals"}),stationLayer=svgEl("g",{class:"operational-stations"}),blockLayer=svgEl("g",{class:"operational-blocks"}),trainLayer=svgEl("g",{class:"operational-trains"});svg.append(routeLayer,signalLayer,stationLayer,blockLayer,trainLayer);
    const tooltip=htmlEl("div",{class:"map-tooltip",role:"status"});container.append(base,toolbar,readout,selection,svg,tooltip);
    demo.addEventListener("click",()=>startDemo("MANUAL_PRESENTATION_MODE"));pause.addEventListener("click",()=>{state.paused=!state.paused;pause.textContent=state.paused?"▶ Resume":"Ⅱ Pause";if(state.demo)state.demo.paused=state.paused;container.classList.toggle("display-paused",state.paused);});fit.addEventListener("click",()=>container.classList.toggle("map-dense"));routeBtn.addEventListener("click",()=>highlightActiveRoute());blockBtn.addEventListener("click",()=>highlightSelectedBlock());clearBtn.addEventListener("click",()=>clearMapStatus());
    return {container,svg,routeLayer,signalLayer,stationLayer,blockLayer,trainLayer,connection,title,subtitle,occupancy,detailTitle,detailBody,tooltip,demoButton:demo,routeButton:routeBtn,blockButton:blockBtn,clearButton:clearBtn};
  }

  function showTooltip(message){parts.tooltip.textContent=message;parts.tooltip.classList.add("visible");clearTimeout(parts.tooltip._timer);parts.tooltip._timer=setTimeout(()=>parts.tooltip.classList.remove("visible"),5000);}
  function trainsAtStation(s){return state.trains.filter(t=>Math.abs(num(t.current_km)-num(s.km))<=.35);}
  function renderStations(){parts.stationLayer.replaceChildren();state.stations.forEach(s=>{const x=xForKm(s.km);const g=svgEl("g",{class:"station-node",tabindex:0,role:"button","aria-label":`${s.name}, KM ${s.km}`});g.append(svgEl("rect",{x:x-25,y:34,width:50,height:180,class:"station-hitbox"}),svgEl("line",{x1:x,y1:39,x2:x,y2:212,class:"station-guide"}),svgEl("circle",{cx:x,cy:VIEW.upY,r:4,class:"station-dot-up"}),svgEl("circle",{cx:x,cy:VIEW.dnY,r:4,class:"station-dot-dn"}),svgEl("text",{x,y:28,"text-anchor":"middle",class:"station-label"},s.code),svgEl("text",{x,y:224,"text-anchor":"middle",class:"station-name"},s.name),svgEl("text",{x,y:239,"text-anchor":"middle",class:"station-km"},`KM ${num(s.km).toFixed(1)}`));const select=()=>showTooltip(`${s.name} · KM ${num(s.km).toFixed(1)} · ${trainsAtStation(s).length} live train(s)`);g.addEventListener("click",select);g.addEventListener("keydown",e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});parts.stationLayer.append(g);});}
  function blockRange(b){const a=num(b.location_from_km,NaN),z=num(b.location_to_km,NaN);if(!Number.isFinite(a)||!Number.isFinite(z))return null;return {a:Math.max(0,Math.min(25,a)),z:Math.max(0,Math.min(25,z))};}
  function renderBlocks(){parts.blockLayer.replaceChildren();state.blocks.forEach((b,i)=>{const r=blockRange(b);if(!r)return;const x1=xForKm(Math.min(r.a,r.z)),x2=xForKm(Math.max(r.a,r.z));const y=b.target_track==='DN_LINE'?VIEW.dnY-9:VIEW.upY-9;const assetClass=String(b.asset_type||b.maintenance_type||'').toLowerCase().includes('signal')?'asset-signal':String(b.asset_type||b.maintenance_type||'').toLowerCase().includes('wire')||String(b.department||'').toLowerCase().includes('traction')?'asset-ohe':'asset-track';const colorClass=`maintenance-color-${i%6}`;const statusClass=b.status==='Planned'?'planned':b.status==='PENDING_SAFETY'?'pending-safety':'active';const g=svgEl('g',{class:`live-block ${colorClass} ${assetClass} ${statusClass} ${state.selectedBlock===b.block_id?'selected-block':''}`,tabindex:0,role:'button','data-block':b.block_id});const asset=(b.asset_type||'').toString().replace('Section','').trim();const label=`${b.block_id} · ${r.a.toFixed(1)}–${r.z.toFixed(1)} KM${asset?` · ${asset}`:''}`;const type=(b.disruption_type||b.maintenance_type||'Maintenance').replaceAll('Maintenance','').trim()||'WORK';g.append(svgEl('rect',{x:x1,y,width:Math.max(14,x2-x1),height:18,rx:5,class:'block-band'}),svgEl('text',{x:(x1+x2)/2,y:y+13,'text-anchor':'middle',class:'block-label'},label),svgEl('title',{},`${b.block_id} · ${type} · ${b.status||'Active'} · ${b.target_track||'CORRIDOR'}`));const select=()=>{state.selectedBlock=b.block_id;state.blockMode=true;renderOperational();showTooltip(`${b.block_id} · ${b.disruption_type||'Maintenance'} · ${b.status} · ${b.target_track}`)};g.addEventListener('click',select);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});parts.blockLayer.append(g);});}
  function signalFor(s,track='UP_LINE'){const item=(state.ai3?.signals||[]).find(x=>x.station_id===s.id);const aspect=item?.aspects?.[track];if(aspect)return aspect;const blocked=state.blocks.some(b=>{const r=blockRange(b);return r&&b.status==='Active'&&(b.target_track==null||b.target_track===track)&&num(s.km)>=r.a-.2&&num(s.km)<=r.z+.2;});const caution=state.trains.some(t=>t.track===track&&t.block_context&&Math.abs(num(t.current_km)-num(s.km))<2);return blocked?'RED':caution?'YELLOW':'GREEN';}
  function renderSignals(){parts.signalLayer.replaceChildren();state.stations.forEach(s=>{const x=xForKm(s.km),up=signalFor(s,'UP_LINE'),dn=signalFor(s,'DN_LINE');const status=up==='RED'||dn==='RED'?'RED':up==='YELLOW'||dn==='YELLOW'?'YELLOW':'GREEN';const g=svgEl('g',{class:`map-signal signal-${status.toLowerCase()}`,tabindex:0,role:'button','aria-label':`${s.code} UP ${up}, DN ${dn}`});g.append(svgEl('line',{x1:x,y1:45,x2:x,y2:57,class:'signal-post'}),svgEl('circle',{cx:x,cy:42,r:6,class:'signal-light'}),svgEl('text',{x:x+9,y:45,class:'signal-label'},`U:${up} D:${dn}`));g.addEventListener('click',()=>showTooltip(`${s.code} · UP ${up} · DN ${dn}`));parts.signalLayer.append(g);});}
  function createTrain(id){const g=svgEl('g',{class:'live-train',tabindex:0,role:'button','data-train':id});g.append(svgEl('rect',{x:-30,y:-25,width:60,height:50,rx:10,class:'train-hitbox'}),svgEl('circle',{r:20,class:'train-halo'}),svgEl('rect',{x:-16,y:-10,width:32,height:20,rx:5,class:'train-body',filter:'url(#liveTrainShadow)'}),svgEl('path',{d:'M16 -8 L24 0 L16 8 Z',class:'train-nose'}),svgEl('path',{d:'M-9 -3 H9 M-9 3 H9',class:'train-window'}),svgEl('text',{x:0,y:-20,'text-anchor':'middle',class:'train-label'}),svgEl('text',{x:0,y:30,'text-anchor':'middle',class:'train-state-label'}));const select=()=>selectTrain(id);g.addEventListener('click',select);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});parts.trainLayer.append(g);return g;}
  function selectTrain(id){state.selectedTrain=String(id);const t=state.trains.find(x=>String(x.train_no)===state.selectedTrain);if(!t)return;renderOperational();showTooltip(`${t.train_no} · ${t.current_station} → ${t.next_station} · KM ${num(t.current_km).toFixed(2)} · ${t.status}`);}
  function renderTrains(){
    const nodes=new Map([...parts.trainLayer.querySelectorAll('g[data-train]')].map(n=>[n.dataset.train,n]));
    const active=new Set();
    const labelOffsets=new Map();
    // Keep labels readable without moving the physical train marker. Main-line
    // labels are staggered by track; loop labels are staggered independently so
    // a rerouted train can never inherit a main-line label position.
    for(const track of ['UP_LINE','DN_LINE']){
      const nearby=state.trains.filter(t=>t.track===track && !(t.route_control?.mode==='LOOP' && t.route_control?.status==='ON_LOOP')).slice().sort((a,b)=>num(a.current_km)-num(b.current_km));
      let level=0;
      for(let i=0;i<nearby.length;i++){
        if(i>0 && Math.abs(num(nearby[i].current_km)-num(nearby[i-1].current_km))<0.8) level=(level+1)%4;
        else level=0;
        labelOffsets.set(String(nearby[i].train_no),level);
      }
    }
    const loopGroups=new Map();
    for(const t of state.trains){
      if(t.route_control?.mode==='LOOP' && t.route_control?.status==='ON_LOOP'){
        const key=String(t.route_control.via?.loop_id||'LOOP');
        if(!loopGroups.has(key)) loopGroups.set(key,[]);
        loopGroups.get(key).push(t);
      }
    }
    for(const [loopId,nearby] of loopGroups){
      nearby.sort((a,b)=>num(a.route_control?.loop_progress_km)-num(b.route_control?.loop_progress_km));
      nearby.forEach((t,i)=>labelOffsets.set(String(t.train_no),i%3));
    }
    state.trains.forEach((t)=>{
      const id=String(t.train_no);active.add(id);
      const node=nodes.get(id)||createTrain(id);
      const target=Math.max(0,Math.min(25,num(t.current_km)));
      state.targetKm.set(id,target);
      if(!state.visualKm.has(id))state.visualKm.set(id,target);
      const pos=visualPosition(t,state.visualKm.get(id));
      node.setAttribute('transform',`translate(${pos.x} ${pos.y})`);
      node.classList.toggle('selected',state.selectedTrain===id);
      node.classList.toggle('train-delayed',num(t.delay_minutes)>0);
      node.classList.toggle('train-block',Boolean(t.block_context));const control=state.ai3?.controls?.[id]||{};node.classList.toggle('train-ai3-hold',control.action==='HOLD');node.classList.toggle('train-ai3-regulate',control.action==='SPEED_REGULATION'||control.action==='BLOCK_APPROACH');node.classList.toggle('train-ai3-reroute',control.action==='REROUTE_VIA_LOOP');
      const labelLevel=labelOffsets.get(id)||0;
      const onLoop=t.route_control?.mode==='LOOP'&&t.route_control?.status==='ON_LOOP';
      const stateText=onLoop
        ? `↗ ${t.route_control.via?.loop_id||'LOOP'} · ${num(t.route_control.loop_progress_km).toFixed(1)} km`
        : (t.block_context?'BLOCK':(t.control_action==='HOLD'?'HOLD':(t.control_action==='SPEED_REGULATION'?'SPEED REG.':(t.status||'LIVE'))));
      node.querySelector('.train-label').setAttribute('y',String(-20-(labelLevel*14)));
      node.querySelector('.train-state-label').setAttribute('y',String(31+(labelLevel*11)));
      node.querySelector('.train-state-label').setAttribute('dy', '0');
      node.querySelector('.train-label').textContent=id;
      node.querySelector('.train-state-label').textContent=stateText;
      node.querySelector('.train-body').dataset.direction=t.direction||'UP';
      node.querySelector('.train-nose').dataset.direction=t.direction||'UP';
      node.setAttribute('aria-label',`Train ${id}, ${t.name}, ${t.direction==='UP'?'UP':'DN'}, ${onLoop?'ON '+(t.route_control.via?.loop_id||'LOOP'):(t.track||'MAIN')}, KM ${target.toFixed(2)}, ${t.current_station} to ${t.next_station}`);
    });
    nodes.forEach((node,id)=>{if(!active.has(id)){node.remove();state.visualKm.delete(id);state.targetKm.delete(id);}});
  }
  function renderRoutes(){
    parts.routeLayer.replaceChildren();
    const controls=state.ai3?.controls||{};
    const seen=new Set();
    Object.entries(controls).forEach(([trainId,control])=>{
      if(control?.action!=="REROUTE_VIA_LOOP"||!control.route_via)return;
      const t=state.trains.find(x=>String(x.train_no)===String(trainId));
      if(!t)return;
      const via=control.route_via;
      const station=state.stations.find(s=>s.id===via.station_id);
      if(!station)return;
      const block=state.blocks.find(b=>b.block_id===control.block_id);
      const entryKm=Number(via.entry_km ?? station.km);
      const rejoinKm=block ? (t.direction==='UP' ? Number(block.location_to_km)+0.2 : Number(block.location_from_km)-0.2) : Number(via.block_entry_km ?? station.km);
      const key=`${trainId}-${via.loop_id}-${control.block_id||''}`;
      if(seen.has(key))return; seen.add(key);
      const x1=xForKm(entryKm,t.direction),x2=xForKm(rejoinKm,t.direction);
      const mainY=t.track==='DN_LINE'?VIEW.dnY:VIEW.upY;
      const loopY=Number(via[t.direction==='UP'?'map_y_up':'map_y_dn'] ?? (t.direction==='UP'?156:156));
      const path=svgEl('path',{d:`M ${x1} ${mainY} C ${x1+45} ${loopY}, ${x2-45} ${loopY}, ${x2} ${mainY}`,class:'ai3-reroute-path'});
      const label=svgEl('text',{x:(x1+x2)/2,y:loopY-8,'text-anchor':'middle',class:'ai3-reroute-label'},`${trainId} ↗ ${via.loop_id} · ${control.block_id||'BLOCK'}`);
      parts.routeLayer.append(path,label);
    });
    if(!state.routeMode)return;
    const t=state.trains.find(x=>String(x.train_no)===state.selectedTrain)||state.trains.find(x=>x.status!=='HOLD AT SIGNAL');
    if(!t)return;
    state.selectedTrain=String(t.train_no);
    const endKm=t.direction==='UP'?25:0;
    const x1=xForKm(t.current_km,t.direction),x2=xForKm(endKm,t.direction);
    parts.routeLayer.append(svgEl('line',{x1,x2,y1:yForTrain(t),y2:yForTrain(t),class:'selected-route'}));
    const tag=svgEl('text',{x:(x1+x2)/2,y:yForTrain(t)-12,'text-anchor':'middle',class:'route-label'},`${t.train_no} · ${t.direction==='UP'?'UP':'DN'} ROUTE`);
    parts.routeLayer.append(tag);
  }

  function highlightActiveRoute(){const t=state.trains.find(x=>String(x.train_no)===state.selectedTrain)||state.trains[0];if(!t){showTooltip("No train telemetry available.");return;}state.selectedTrain=String(t.train_no);state.routeMode=true;state.blockMode=false;renderOperational();showTooltip(`${t.train_no} · active ${t.direction} route highlighted from KM ${num(t.current_km).toFixed(2)} to ${t.direction==='UP'?'25.0':'0.0'}`);}
  function highlightSelectedBlock(){const b=state.blocks.find(x=>x.block_id===state.selectedBlock)||state.blocks.find(x=>x.status==='Active');if(!b){showTooltip("No active block available.");return;}state.selectedBlock=b.block_id;state.blockMode=true;state.routeMode=false;renderOperational();showTooltip(`${b.block_id} · ${b.target_track} · KM ${num(b.location_from_km).toFixed(1)}–${num(b.location_to_km).toFixed(1)}`);}
  function clearMapStatus(){state.selectedTrain=null;state.selectedBlock=null;state.routeMode=false;state.blockMode=false;renderOperational();parts.tooltip.classList.remove('visible');}
  function renderDetail(){const t=state.trains.find(x=>String(x.train_no)===state.selectedTrain);if(!t){parts.detailTitle.textContent='LIVE TRAIN INSPECTOR';parts.detailBody.textContent='Click any moving train marker to inspect its live operational state.';return;}const b=t.block_context?`${t.block_context.relation.replaceAll('_',' ')} · ${t.block_context.block_id}`:'CLEAR';parts.detailTitle.textContent=`${t.train_no} · ${t.name}`;parts.detailBody.textContent=`${t.direction==='UP'?'UP':'DN'} · KM ${num(t.current_km).toFixed(2)} · ${t.current_station} → ${t.next_station} · ${num(t.effective_speed_kmh??t.speed_kmh).toFixed(0)} km/h · ${t.status} · ${b}`;}
  function renderOperational(){renderStations();renderSignals();renderBlocks();renderRoutes();renderTrains();renderDetail();parts.title.textContent=state.mode==='PRESENTATION'?'PRESENTATION MODE · LOCAL SIMULATION':state.connected?'LIVE BACKEND TELEMETRY':'CONNECTING TELEMETRY';parts.subtitle.textContent=`${state.trains.length} trains · ${state.stations.length} stations · ${state.blocks.length} active work`;parts.connection.classList.toggle('offline',!state.connected&&state.mode!=='PRESENTATION');parts.connection.lastChild.textContent=state.mode==='PRESENTATION'?' PRESENTATION LIVE':state.connected?' LIVE BACKEND CONNECTED':' CONNECTING';const up=state.trains.filter(t=>t.track==='UP_LINE').length,dn=state.trains.filter(t=>t.track==='DN_LINE').length;const affected=[...new Set(state.blocks.filter(b=>b.status==='Active').map(b=>b.target_track).filter(Boolean))];const reroutes=state.trains.filter(t=>(t.route_control||{}).mode==='LOOP').length || Object.values(state.ai3?.controls||{}).filter(c=>c?.action==='REROUTE_VIA_LOOP').length;parts.occupancy.innerHTML=`<span class="route-pill ${affected.includes('UP_LINE')?'affected':''}">UP ${up} trains</span><span class="route-pill ${affected.includes('DN_LINE')?'affected':''}">DN ${dn} trains</span>${affected.length?`<em>${affected.map(x=>x.replace('_LINE','')).join(' + ')} blocked</em>`:'<em>Both routes available</em>'}${reroutes?`<em class="reroute-pill">↗ ${reroutes} AI-3 reroute${reroutes>1?'s':''}</em>`:''}`;const footer=document.querySelector('.track-foot');if(footer){footer.querySelector('span:first-child').textContent=state.mode==='PRESENTATION'?'● PRESENTATION LIVE':'● LIVE TRAIN MOVEMENT';footer.querySelector('span:last-child').textContent=`${state.stations.length} stations · ${state.trains.length} trains · ${state.blocks.length} active work`;}}
  function applySnapshot(payload,source){if(!payload?.trains)return;state.trains=payload.trains;state.blocks=payload.active_blocks||[];state.stations=payload.corridor?.stations||state.stations;state.ai3=payload.ai3||{controls:{},signals:[]};state.sequence=num(payload.sequence,state.sequence);state.mode=source==='PRESENTATION'?'PRESENTATION':'BACKEND';renderOperational();window.dispatchEvent(new CustomEvent('rail-telemetry',{detail:payload}));}
  function stopDemo(){if(state.demo){state.demo.stop();state.demo=null;}}
  function startDemo(reason='BACKEND_UNAVAILABLE'){stopDemo();state.connected=false;state.mode='PRESENTATION';state.demo=new PresentationRuntime(s=>applySnapshot(s,'PRESENTATION'));state.demo.start();parts.title.textContent=`PRESENTATION MODE · ${reason}`;parts.demoButton.textContent='● Presentation Live';}
  function connect(){clearTimeout(state.reconnectTimer);const protocol=location.protocol==='https:'?'wss:':'ws:';let ws;try{ws=new WebSocket(`${protocol}//${location.host}/ws/live-telemetry`);}catch(e){startDemo('NO LIVE SERVER');return;}state.ws=ws;state.wsTimer=setTimeout(()=>{if(ws.readyState===WebSocket.CONNECTING)ws.close();},2500);ws.addEventListener('open',()=>{clearTimeout(state.wsTimer);stopDemo();state.connected=true;state.mode='BACKEND';renderOperational();});ws.addEventListener('message',e=>{try{applySnapshot(JSON.parse(e.data),'WEBSOCKET');state.connected=true;state.mode='BACKEND';}catch(_){}});ws.addEventListener('close',()=>{state.connected=false;if(state.mode!=='PRESENTATION')startDemo('BACKEND DISCONNECTED');state.reconnectTimer=setTimeout(connect,6000);});ws.addEventListener('error',()=>ws.close());}
  function animate(){
    requestAnimationFrame(()=>{
      if(!state.paused){
        state.targetKm.forEach((target,id)=>{
          const current=state.visualKm.get(id);
          if(current==null)return;
          state.visualKm.set(id,current+(target-current)*.18);
          const t=state.trains.find(x=>String(x.train_no)===id);
          const node=parts.trainLayer.querySelector(`g[data-train="${CSS.escape(id)}"]`);
          if(t&&node){
            const pos=visualPosition(t,state.visualKm.get(id));
            node.setAttribute('transform',`translate(${pos.x} ${pos.y})`);
          }
        });
      }
      animate();
    });
  }
  async function init(){const c=document.querySelector('#railway-map');if(!c||c.dataset.liveMapReady)return;c.dataset.liveMapReady='1';parts=buildMap(c);connect();setTimeout(()=>{if(!state.connected&&state.mode!=='PRESENTATION')startDemo('NO LIVE BACKEND — AUTO FALLBACK');},2800);animate();window.RAIL_OPTIMAX_MAP={getState:()=>({...state}),selectTrain,focusBlock:(id)=>{state.selectedBlock=id;state.blockMode=true;state.routeMode=false;renderOperational();showTooltip(`Focused maintenance block ${id}`);},runPlan:async()=>{if(state.mode==='PRESENTATION'&&state.demo)return state.demo.plan();const r=await fetch('./ai/plan',{method:'POST'});if(!r.ok)throw new Error(`AI-1 HTTP ${r.status}`);return r.json();},injectEmergency:async(input,duration,track='UP_LINE')=>{
      const payload=(typeof input==='object'&&input!==null)?{...input}:{location_km:Number(input),duration_minutes:Number(duration),target_track:track,disruption_type:'Emergency Maintenance'};
      if(state.mode==='PRESENTATION'&&state.demo)return state.demo.emergency(payload.location_km,payload.duration_minutes,payload.target_track);
      const r=await fetch('./ai/adapt/inject-emergency',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      if(!r.ok){let detail='';try{detail=(await r.json())?.detail||'';}catch(_){}throw new Error(`AI-2 HTTP ${r.status}${detail?` · ${typeof detail==='string'?detail:JSON.stringify(detail)}`:''}`);}
      return r.json();
    }};}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
