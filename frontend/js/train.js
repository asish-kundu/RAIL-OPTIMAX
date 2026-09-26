export function renderLiveTrains(containerId, trainList) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = trainList
    .map((t) => {
      const isDelayed = t.delay_minutes > 0;
      const badgeClass = isDelayed ? "b-yellow" : "b-green";
      return `
      <div class="train-crd">
        <div class="train-name">${t.train_no} ${t.name}</div>
        <div style="color:var(--text-muted)">${t.origin} → ${t.destination}</div>
        <div style="font-weight:600">KM ${t.current_km}</div>
        <span class="badge ${badgeClass}">${t.status}</span>
      </div>
    `;
    })
    .join("");
}
