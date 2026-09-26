from ortools.sat.python import cp_model
from typing import List, Dict, Any

class BlockOptimizer:
    @staticmethod
    def optimize_blocks(tasks: List[Dict[str, Any]], windows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        model = cp_model.CpModel()
        x = {}

        for t in tasks:
            for w in windows:
                x[(t["query_id"], w["block_id"])] = model.NewBoolVar(f"x_{t['query_id']}_{w['block_id']}")

        for t in tasks:
            model.Add(sum(x[(t["query_id"], w["block_id"])] for w in windows) <= 1)

        for w in windows:
            model.Add(
                sum(
                    int(t.get("duration_minutes", 60)) * x[(t["query_id"], w["block_id"])]
                    for t in tasks
                ) <= int(w.get("duration_minutes", 90))
            )

        objective_terms = []
        for t in tasks:
            p_score = int(t.get("priority_score", 50))
            for w in windows:
                objective_terms.append(p_score * x[(t["query_id"], w["block_id"])])

        model.Maximize(sum(objective_terms))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 2.0
        status = solver.Solve(model)

        bundled_assignments = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for w in windows:
                assigned = [
                    t["query_id"]
                    for t in tasks
                    if solver.Value(x[(t["query_id"], w["block_id"])]) == 1
                ]
                if assigned:
                    bundled_assignments.append({
                        "block_id": w["block_id"],
                        "assigned_tasks": assigned,
                        "task_count": len(assigned)
                    })
        return bundled_assignments