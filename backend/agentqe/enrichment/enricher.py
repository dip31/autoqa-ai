class TestEnricher:

    def enrich(
        self,
        tests,
        execution_history=None,
        repository_data=None
    ):

        execution_history = (
            execution_history or {}
        )

        repository_data = (
            repository_data or {}
        )

        for test in tests:

            test.risk_score = (
                self._risk(test)
            )

            history = execution_history.get(
                test.test_id,
                {}
            )

            test.historical_pass_rate = (
                history.get(
                    "pass_rate",
                    0.0
                )
            )

            test.historical_failure_rate = (
                history.get(
                    "failure_rate",
                    0.0
                )
            )

            test.execution_cost = (
                self._cost(test)
            )

            test.change_impact = (
                self._change_impact(
                    test,
                    repository_data
                )
            )

        return tests

    def _risk(self, test):

        if test.test_type == "SECURITY":
            return 1.0

        if test.priority == "High":
            return 0.9

        if test.test_type == "API":
            return 0.7

        return 0.5

    def _cost(self, test):

        return {
            "UNIT": 1.0,
            "API": 2.0,
            "UI": 4.0,
            "INTEGRATION": 5.0,
            "SECURITY": 6.0,
            "PERFORMANCE": 8.0
        }.get(
            test.test_type,
            3.0
        )

    def _change_impact(
        self,
        test,
        repository_data
    ):

        return 0.5