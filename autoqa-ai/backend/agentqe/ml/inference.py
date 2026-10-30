import torch


class TestRanker:

    def __init__(
        self,
        model,
        feature_extractor
    ):

        self.model = model
        self.feature_extractor = (
            feature_extractor
        )

    def rank(self, tests):

        if not tests:
            return []

        features = [
            self.feature_extractor.extract(test)
            for test in tests
        ]

        import numpy as np
        # Convert to single numpy array first — avoids slow tensor-from-list warning
        x = torch.tensor(np.array(features), dtype=torch.float32)

        # Add sequence dimension
        x = x.unsqueeze(0)

        with torch.no_grad():

            scores = self.model(x)

        scores = scores.squeeze(0)

        for test, score in zip(
            tests,
            scores
        ):

            test.transformer_score = (
                float(score)
            )

        return sorted(
            tests,
            key=lambda t:
                t.transformer_score or 0,
            reverse=True
        )