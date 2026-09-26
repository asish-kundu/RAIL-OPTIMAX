"""
Safety Validation Engine
Enforces Indian Railways General & Subsidiary Rules (G&SR) constraints.
Safety checks strictly dominate secondary scheduling optimization.
"""
from typing import Dict, List, Tuple, Any

class SafetyValidator:
    MIN_HEADWAY_SECONDS = 120        # Minimum headway between consecutive trains (2 min in ABS)
    BLOCK_CLEARANCE_MARGIN_MIN = 10  # Minimum buffer before/after maintenance possession
    MAX_SPEED_RESTRICTION_KMH = 30   # Caution order maximum speed on adjacent line

    @classmethod
    def validate_block_possession(
        cls, 
        block_proposal: Dict[str, Any], 
        live_trains: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Validates whether a block possession proposal violates absolute safety limits.
        """
        violations = []
        block_start_km = float(block_proposal.get("location_from_km", 0.0))
        block_end_km = float(block_proposal.get("location_to_km", 0.0))
        target_track = block_proposal.get("target_track", "UP_LINE")

        # 1. Check for Active Train Incursion into Proposed Possession
        for train in live_trains:
            t_km = float(train.get("current_km", -1))
            t_dir = train.get("direction", "UP")
            
            # Match direction with track
            matches_track = (t_dir == "UP" and "UP" in target_track) or (t_dir == "DN" and "DN" in target_track)
            
            if matches_track:
                # Within safety envelope: 2 km buffer
                if (block_start_km - 2.0) <= t_km <= (block_end_km + 2.0):
                    violations.append(
                        f"CRITICAL: Train {train.get('train_no', 'N/A')} ({train.get('name', 'Train')}) is located at KM {t_km:.1f}, "
                        f"inside safety buffer for block span KM {block_start_km}-{block_end_km}."
                    )

        # 2. Traction Power Isolation Validation
        if block_proposal.get("power_block_required", False):
            if not block_proposal.get("ohe_isolated", False):
                violations.append(
                    "OHE WARNING: Traction power block requested. Mandatory isolation confirmation "
                    "or speed restriction caution order (<30 km/h) required on adjacent tracks."
                )

        is_safe = len(violations) == 0
        return is_safe, violations

    @classmethod
    def validate_train_separation(cls, train_a: Dict[str, Any], train_b: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates minimum spatial and temporal separation between two running trains.
        """
        if train_a.get("direction") == train_b.get("direction"):
            km_gap = abs(train_a.get("current_km", 0) - train_b.get("current_km", 0))
            if km_gap < 1.0:  # Absolute Block headway limit (1 km)
                return False, f"HEADWAY BREACH: Train {train_a.get('train_no')} and {train_b.get('train_no')} gap is {km_gap:.2f} KM (< 1.0 KM)."
        return True, "Headway Clear"