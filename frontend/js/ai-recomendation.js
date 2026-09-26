export async function triggerOptimizer() {
  const res = await fetch("/ai/optimize", { method: "POST" });
  return await res.json();
}
