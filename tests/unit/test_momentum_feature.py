
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from src.signals.signal_generator import ESGSignalGenerator

class TestMomentumFeature(unittest.TestCase):
    def setUp(self):
        self.generator = ESGSignalGenerator()

    def test_momentum_calculation(self):
        # Case 1: Strong Positive sentiment
        # New formula: direction * conviction
        # direction = sign(1.0) = 1.0
        # event_severity = 0.8
        # sentiment_strength = abs(1.0) = 1.0
        # volume_normalized = min(log1p(10.0)/log(10), 1.0) = 1.0
        # duration_normalized = min(7/7, 1.0) = 1.0
        # conviction = 0.20*0.8 + 0.40*1.0 + 0.25*1.0 + 0.15*1.0 = 0.96
        # raw_score = 1.0 * 0.96 = 0.96

        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': 1.0,
            'volume_ratio': 10.0,
            'duration_days': 7,
            'max_sentiment': 1.0,
            'polarization': 0.5
        }

        score = self.generator.compute_raw_score(event_features, reaction_features)
        self.assertAlmostEqual(score, 0.96, places=2)

    def test_negative_momentum(self):
        # Case 2: Strong Negative sentiment
        # direction = sign(-1.0) = -1.0
        # conviction components identical to Case 1 (uses abs(intensity))
        # conviction = 0.96
        # raw_score = -1.0 * 0.96 = -0.96

        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': -1.0,
            'volume_ratio': 10.0,
            'duration_days': 7
        }

        score = self.generator.compute_raw_score(event_features, reaction_features)
        self.assertAlmostEqual(score, -0.96, places=2)

    def test_neutral_momentum(self):
        # Case 3: Neutral Sentiment (abs(0.0) <= 0.01 threshold)
        # direction = 0.0 (neutral)
        # raw_score = 0.0 * conviction = 0.0

        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': 0.0,
            'volume_ratio': 10.0,
            'duration_days': 7
        }

        score = self.generator.compute_raw_score(event_features, reaction_features)
        self.assertAlmostEqual(score, 0.0, places=3)

if __name__ == '__main__':
    unittest.main()
