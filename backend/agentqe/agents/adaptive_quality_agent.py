from typing import Any, Dict, List


class AdaptiveQualityAgent:
    """
    Evaluates the result of a QA cycle and decides whether
    the system should proceed or request another cycle.
    """

    FAILURE_STATUSES = {
        "FAIL",
        "FAILED",
        "ERROR"
    }

    def _get_status(self, result: Any) -> str:
        """
        Supports both:
            result.status
        and:
            result["status"]
        """

        if isinstance(result, dict):
            return str(
                result.get("status", "")
            ).upper()

        return str(
            getattr(result, "status", "")
        ).upper()

    def evaluate(
        self,
        execution_results: List[Any],
        current_cycle: int,
        max_cycles: int
    ) -> Dict[str, Any]:

        failures = []

        for result in execution_results:

            status = self._get_status(result)

            if status in self.FAILURE_STATUSES:
                failures.append(result)

        failure_count = len(failures)

        if (
            failure_count > 0
            and current_cycle < max_cycles
        ):

            return {
                "decision": "REPLAN",
                "reason": (
                    f"{failure_count} test(s) failed or errored. "
                    "The next cycle should adapt the testing strategy."
                ),
                "failure_count": failure_count,
                "current_cycle": current_cycle,
                "next_cycle": current_cycle + 1
            }

        return {
            "decision": "PROCEED",
            "reason": (
                "Current QA cycle is complete."
            ),
            "failure_count": failure_count,
            "current_cycle": current_cycle,
            "next_cycle": None
        }