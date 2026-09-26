export async function submitMaintenanceQuery(formData) {
  const response = await fetch("./maintenance/", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formData),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return await response.json();
}

export function renderSubmittedQueriesTable(tableBodyId, queries) {
  const tbody=document.getElementById(tableBodyId); if(!tbody)return; tbody.replaceChildren();
  for(const q of (Array.isArray(queries)?queries:[])){
    const tr=document.createElement("tr");
    const cells=[q.query_id||"N/A",`KM ${q.location_from_km} - ${q.location_to_km}`,q.maintenance_type||"Maintenance",`${q.duration_minutes||0} min`,q.priority||"Medium",q.status||"Under Review",q.submitted_on||"Today"];
    for(const value of cells){const td=document.createElement("td");td.textContent=String(value);tr.appendChild(td);} tbody.appendChild(tr);
  }
}
