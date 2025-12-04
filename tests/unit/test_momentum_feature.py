
import unittest
import pandas as pd
import numpy as np
from datetime import datetime
from src.signals.signal_generator import ESGSignalGenerator

class TestMomentumFeature(unittest.TestCase):
    def setUp(self):
        self.generator = ESGSignalGenerator()
        # Ensure the weight is set (it might be 0 by default in some configs, but we want to test the logic)
        self.generator.weights['sentiment_volume_momentum'] = 0.2

    def test_momentum_calculation(self):
        # Case 1: Strong Positive
        # Intensity = 1.0 (Positive)
        # Volume Ratio = 10.0 -> log10(11) / log10(10) ~= 1.04 -> capped at 1.0
        # Expected Momentum Proxy = 1.0 * 1.0 = 1.0
        # Expected Normalized = (1.0 + 1.0) / 2.0 = 1.0
        
        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': 1.0,
            'volume_ratio': 10.0,
            'duration_days': 7,
            'max_sentiment': 1.0,
            'polarization': 0.5
        }
        
        # We need to access the internal logic or check the output score
        # Let's check compute_raw_score
        score = self.generator.compute_raw_score(event_features, reaction_features)
        
        # Calculate expected score manually
        # event: 0.2 * 0.8 = 0.16
        # intensity: 0.45 * ((1+1)/2) = 0.45 * 1.0 = 0.45
        # volume: 0.25 * 1.0 = 0.25
        # duration: 0.10 * 1.0 = 0.10
        # max_sentiment: 0.0 * ... = 0
        # polarization: 0.0 * ... = 0
        # momentum: 0.2 * 1.0 = 0.2
        # Total = 0.16 + 0.45 + 0.25 + 0.10 + 0.2 = 1.16
        
        self.assertAlmostEqual(score, 1.16, places=2)

    def test_negative_momentum(self):
        # Case 2: Strong Negative
        # Intensity = -1.0
        # Volume Ratio = 10.0 -> Normalized 1.0
        # Proxy = -1.0 * 1.0 = -1.0
        # Normalized = (-1.0 + 1.0) / 2.0 = 0.0
        
        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': -1.0,
            'volume_ratio': 10.0,
            'duration_days': 7
        }
        
        score = self.generator.compute_raw_score(event_features, reaction_features)
        
        # event: 0.16
        # intensity: 0.45 * 0.0 = 0.0
        # volume: 0.25 * 1.0 = 0.25
        # duration: 0.10
        # momentum: 0.2 * 0.0 = 0.0
        # Total = 0.16 + 0.0 + 0.25 + 0.10 + 0.0 = 0.51
        
        self.assertAlmostEqual(score, 0.51, places=2)

    def test_neutral_momentum(self):
        # Case 3: Neutral Sentiment, High Volume
        # Intensity = 0.0
        # Volume = 1.0
        # Proxy = 0.0
        # Normalized = 0.5
        
        event_features = {'confidence': 0.8}
        reaction_features = {
            'intensity': 0.0,
            'volume_ratio': 10.0,
            'duration_days': 7
        }
        
        score = self.generator.compute_raw_score(event_features, reaction_features)
        
        # event: 0.16
        # intensity: 0.45 * 0.5 = 0.225
        # volume: 0.25
        # duration: 0.10
        # momentum: 0.2 * 0.5 = 0.1
        # Total = 0.16 + 0.225 + 0.25 + 0.10 + 0.1 = 0.835
        
        self.assertAlmostEqual(score, 0.835, places=3)

if __name__ == '__main__':
    unittest.main()
