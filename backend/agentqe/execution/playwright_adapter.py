from agents.autonomous_agent import (
    _execute_test_pipeline
)


class PlaywrightAdapter:

    def execute(
        self,
        run_id,
        url,
        tests
    ):

        raw_tests = [
            self._to_existing_format(
                test
            )
            for test in tests
        ]

        return _execute_test_pipeline(
            run_id,
            url,
            raw_tests,
            len(raw_tests)
        )

    def _to_existing_format(
        self,
        test
    ):

        return {
            "id": test.test_id,
            "title": test.title,
            "objective": test.description,
            "category": test.category,
            "priority": test.priority,
            "steps": test.steps,
            "input_data": test.input_data,
            "expected_result":
                test.expected_result,
            "automatable":
                test.automatable,
            "blocked_reason":
                test.blocked_reason,
            "action":
                test.metadata.get(
                    "action",
                    "visible"
                ),
            "selector":
                test.metadata.get(
                    "selector",
                    "body"
                ),
            "action_value":
                test.metadata.get(
                    "action_value",
                    ""
                )
        }