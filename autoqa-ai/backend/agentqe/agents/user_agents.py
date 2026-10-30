from agents.generator_agent import generate_testcases

from agentqe.models.test_case import CandidateTest


class UserAgent:

    """
    User-perspective test generation.

    IMPORTANT:
    Existing generator_agent.py remains the actual generation engine.
    """

    def generate(self, context, plan=None):

        requirement = context.requirement or context.module_name or "General Application"
        
        try:
            result = generate_testcases(requirement)
        except Exception as e:
            # Fallback if generator fails
            return [
                CandidateTest(
                    test_id="USER-FB-001",
                    title=f"Verify {requirement}",
                    description=f"Fallback user test for {requirement}",
                    perspective="USER",
                    test_type="UI",
                    target=context.module_name,
                    source_agent="UserAgent",
                    expected_result="Action completes successfully",
                    evidence={"fallback": "generator_failed"}
                )
            ]

        # generator_agent returns keys: positive_tests, negative_tests,
        # boundary_tests, ui_tests — flatten all of them
        raw_tests = []
        for key in ("positive_tests", "negative_tests", "boundary_tests", "ui_tests"):
            raw_tests.extend(result.get(key, []))

        # fallback in case the shape differs
        if not raw_tests:
            raw_tests = result.get("test_cases", result.get("testcases", []))

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