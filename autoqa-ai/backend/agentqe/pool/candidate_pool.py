class CandidateTestPool:

    def merge(
        self,
        user_tests,
        engineering_tests
    ):

        combined = (
            user_tests +
            engineering_tests
        )

        return self._deduplicate(
            combined
        )

    def _deduplicate(self, tests):

        seen = set()
        result = []

        for test in tests:

            key = (
                test.title.lower().strip(),
                test.test_type,
                test.target
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(test)

        return result