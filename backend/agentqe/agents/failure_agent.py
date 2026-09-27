class FailureAnalysisAgent:

    def analyze(
        self,
        execution_results
    ):

        failures = []

        for result in execution_results:

            if result.status in (
                "FAIL",
                "ERROR"
            ):

                failures.append({
                    "test_id":
                        result.test_id,

                    "error":
                        result.error_message,

                    "screenshot":
                        result.screenshot_path,

                    "healing_attempted":
                        result.healing_attempted,

                    "healing_successful":
                        result.healing_successful
                })

        return failures