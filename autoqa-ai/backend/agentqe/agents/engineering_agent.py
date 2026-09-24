
#  ├── Unit tests
#  ├── API tests
#  ├── Integration tests
#  ├── Security tests
#  └── Performance tests

from agentqe.models.test_case import CandidateTest


class EngineeringQAAgent:

    def generate(self, context):

        tests = []

        tests.extend(
            self._generate_unit_tests(context)
        )

        tests.extend(
            self._generate_api_tests(context)
        )

        tests.extend(
            self._generate_security_tests(context)
        )

        return tests

    def _generate_unit_tests(self, context):

        return [
            CandidateTest(
                test_id="ENG-UNIT-001",
                title="Unit test candidate",
                description=(
                    "Validate important "
                    "application logic."
                ),
                perspective="ENGINEERING",
                test_type="UNIT",
                target=context.module_name,
                source_agent="EngineeringQAAgent"
            )
        ]

    def _generate_api_tests(self, context):

        return []

    def _generate_security_tests(self, context):

        return []