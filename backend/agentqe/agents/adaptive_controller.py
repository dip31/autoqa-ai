class AdaptiveController:

    def select(
        self,
        tests,
        top_k=10
    ):

        for test in tests:

            transformer_score = (
                test.transformer_score or 0
            )

            test.final_score = (
                0.50 * transformer_score
                +
                0.25 * test.risk_score
                +
                0.15 * test.coverage_gain
                +
                0.10 * test.change_impact
            )

        ranked = sorted(
            tests,
            key=lambda t:
                getattr(
                    t,
                    "final_score",
                    0
                ),
            reverse=True
        )

        return ranked[:top_k]