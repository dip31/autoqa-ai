from typing import Dict


class HumanReview:
    APPROVE = "APPROVE"
    REPLAN = "REPLAN"

    VALID_DECISIONS = {
        APPROVE,
        REPLAN,
    }

    def validate_decision(self, decision: str) -> str:
        """
        Validate and normalize the human decision.
        """
        if not decision:
            raise ValueError("Human decision is required.")

        decision = decision.strip().upper()

        if decision not in self.VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision}'. "
                f"Expected one of: {sorted(self.VALID_DECISIONS)}"
            )

        return decision

    def create_review(
        self,
        run_id: int,
        decision: str,
        feedback: str = "",
        cycle: int = 1,
    ) -> Dict:
        """
        Create a normalized human-review result.

        Database persistence is intentionally kept outside this class
        so the review logic is independent from the database layer.
        """

        decision = self.validate_decision(decision)

        feedback = (feedback or "").strip()

        return {
            "run_id": run_id,
            "decision": decision,
            "feedback": feedback,
            "cycle": cycle,
            "replan": decision == self.REPLAN,
            "approved": decision == self.APPROVE,
        }