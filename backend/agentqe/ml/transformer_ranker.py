import torch
import torch.nn as nn


class TransformerTestRanker(
    nn.Module
):

    def __init__(
        self,
        input_dim=9,
        d_model=64,
        nhead=4,
        num_layers=2
    ):

        super().__init__()

        self.input_projection = nn.Linear(
            input_dim,
            d_model
        )

        encoder_layer = (
            nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                batch_first=True
            )
        )

        self.encoder = (
            nn.TransformerEncoder(
                encoder_layer,
                num_layers=num_layers
            )
        )

        self.ranking_head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )

    def forward(self, x):

        x = self.input_projection(x)

        encoded = self.encoder(x)

        pooled = encoded.mean(
            dim=1
        )

        score = self.ranking_head(
            pooled
        )

        return score.squeeze(-1)