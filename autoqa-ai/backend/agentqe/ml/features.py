import numpy as np


class TestFeatureExtractor:

    def extract(self, test):

        priority = {
            "Low": 0.0,
            "Medium": 0.5,
            "High": 1.0
        }.get(
            test.priority,
            0.5
        )

        test_type = {
            "UNIT": 0.1,
            "API": 0.3,
            "UI": 0.5,
            "INTEGRATION": 0.7,
            "SECURITY": 0.9,
            "PERFORMANCE": 1.0
        }.get(
            test.test_type,
            0.5
        )

        perspective = {
            "USER": 0.0,
            "ENGINEERING": 1.0
        }.get(
            test.perspective,
            0.0
        )

        return np.array([
            priority,
            test_type,
            perspective,
            test.risk_score,
            test.execution_cost,
            test.historical_pass_rate,
            test.historical_failure_rate,
            test.coverage_gain,
            test.change_impact
        ], dtype=np.float32)