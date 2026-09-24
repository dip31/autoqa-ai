from agents.generator_agent import generate_testcases

from agentqe.models.test_case import CandidateTest


class UserAgent:

    """
    User-perspective test generation.

    IMPORTANT:
    Existing generator_agent.py remains the actual generation engine.
    """

    def generate(self, requirement: str):

        result = generate_testcases(
            requirement
        )

        raw_tests = result.get(
            "test_cases",
            result.get("testcases", [])
        )

        return [
            self._normalize(test, index)
            for index, test in enumerate(raw_tests)
        ]

    def _normalize(self, test, index):

        return CandidateTest(
            test_id=test.get(
                "id",
                f"USER-{index + 1:03d}"
            ),

            title=test.get(
                "title",
                f"User Test {index + 1}"
            ),

            description=test.get(
                "objective",
                test.get("description", "")
            ),

            perspective="USER",

            test_type=self._detect_type(test),

            target=test.get(
                "module",
                ""
            ),

            priority=test.get(
                "priority",
                "Medium"
            ),

            category=test.get(
                "category",
                ""
            ),

            steps=test.get(
                "steps",
                []
            ),

            input_data=test.get(
                "input_data"
            ),

            expected_result=test.get(
                "expected_result",
                ""
            ),

            automatable=test.get(
                "automatable",
                True
            ),

            blocked_reason=test.get(
                "blocked_reason"
            ),

            source_agent="UserAgent",

            metadata=test
        )

    @staticmethod
    def _detect_type(test):

        category = str(
            test.get("category", "")
        ).lower()

        if "api" in category:
            return "API"

        if "security" in category:
            return "SECURITY"

        if "unit" in category:
            return "UNIT"

        return "UI"