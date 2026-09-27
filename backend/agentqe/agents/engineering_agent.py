
#  ├── Unit tests
#  ├── API tests
#  ├── Integration tests
#  ├── Security tests
#  └── Performance tests

from agentqe.models.test_case import CandidateTest


class EngineeringQAAgent:

    def generate(self, context, plan=None):

        tests = []

        tests.extend(
            self._generate_api_tests(context)
        )

        tests.extend(
            self._generate_validation_tests(context)
        )

        if not tests:
            tests.extend(
                self._generate_unit_tests(context)
            )

        return tests

    def _generate_unit_tests(self, context):

        return [
            CandidateTest(
                test_id="ENG-UNIT-001",
                title=f"Unit test candidate for {context.module_name or 'General'}",
                description=(
                    "Validate core application logic."
                ),
                perspective="ENGINEERING",
                test_type="UNIT",
                target=context.module_name,
                source_agent="EngineeringQAAgent",
                evidence={"source": "heuristic_fallback"}
            )
        ]

    def _generate_api_tests(self, context):
        tests = []
        if context.api_endpoints:
            for i, endpoint in enumerate(context.api_endpoints):
                tests.append(
                    CandidateTest(
                        test_id=f"ENG-API-{i+1:03d}",
                        title=f"API validation for {endpoint}",
                        description=f"Verify {endpoint} returns expected responses for valid and invalid inputs",
                        perspective="ENGINEERING",
                        test_type="API",
                        target=endpoint,
                        source_agent="EngineeringQAAgent",
                        expected_result="Correct HTTP status and schema",
                        evidence={"source": "api_endpoints_context"}
                    )
                )
        return tests

    def _generate_validation_tests(self, context):
        tests = []
        if context.forms:
            for i, form in enumerate(context.forms):
                form_name = form.get("name", f"Form {i}")
                tests.append(
                    CandidateTest(
                        test_id=f"ENG-VAL-{i+1:03d}",
                        title=f"Boundary validation for {form_name}",
                        description=f"Verify {form_name} correctly rejects malformed input at the API/Data layer",
                        perspective="ENGINEERING",
                        test_type="INTEGRATION",
                        target=form_name,
                        source_agent="EngineeringQAAgent",
                        expected_result="Malformed data is rejected before processing",
                        evidence={"source": "forms_context"}
                    )
                )
        return tests