class TestStrategyAgent:

    def plan(self, context):

        strategy = {
            "test_types": [
                "UI",
                "UNIT",
                "API",
                "SECURITY"
            ],

            "priorities": [
                "HIGH_RISK",
                "CHANGED_CODE",
                "LOW_COVERAGE",
                "HISTORICAL_FAILURE"
            ],

            "max_candidates": 50,

            "execution_budget": 20
        }

        return strategy