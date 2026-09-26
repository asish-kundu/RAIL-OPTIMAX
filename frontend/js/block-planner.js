export async function loadBlockPlanner() {
  const container = document.getElementById("block-planner-mount");
  if (!container) return;

  const blocks = await fetch("/blocks/").then((r) => r.json());
  container.innerHTML = blocks
    .map(
      (b) => `
    <div class="card" style="margin-bottom:10px;">
      <div style="display:flex; justify-content:space-between;">
        <strong>${b.block_id} (${b.section})</strong>
        <span class="badge ${b.approved ? "b-green" : "b-yellow"}">${b.status}</span>
      </div>
      <div style="font-size:12px; margin-top:6px; color:var(--text-muted);">
        Window: ${b.start_time} - ${b.end_time} (${b.duration_minutes} min) | Impact Delay: ${b.train_impact_delay_minutes} min
      </div>
    </div>
  `,
    )
    .join("");
}
