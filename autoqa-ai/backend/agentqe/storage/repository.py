import json
from database.db import execute_query

class AgentQERepository:

    # ---------------------------------------------------------
    # Existing candidate-test methods can remain here
    # ---------------------------------------------------------

    def save_human_review(
        self,
        run_id: int,
        decision: str,
        feedback: str = "",
        cycle: int = 1,
    ):
        """
        Save human review information to autonomous_runs.
        """

        status = (
            "Approved"
            if decision == "APPROVE"
            else "Re-planning"
        )

        query = """
            UPDATE autonomous_runs
            SET
                human_decision = ?,
                human_feedback = ?,
                cycle = ?,
                status = ?
            WHERE id = ?
        """

        params = (
            decision,
            feedback,
            cycle,
            status,
            run_id,
        )

        return execute_query(query, params)

    def get_run_review(self, run_id: int):
        """
        Retrieve the latest human-review information.
        """

        query = """
            SELECT
                id,
                human_decision,
                human_feedback,
                cycle,
                max_cycles,
                strategy_json,
                status
            FROM autonomous_runs
            WHERE id = ?
        """

        return execute_query(
            query,
            (run_id,),
            fetch=True,
        )