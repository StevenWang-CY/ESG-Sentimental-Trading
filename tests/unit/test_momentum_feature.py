
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
        
        # Calculate expected score manually (CORRECTED weights sum to 1.0)
        # event: 0.15 * 0.8 = 0.12
        # intensity: 0.35 * ((1+1)/2) = 0.35 * 1.0 = 0.35
        # volume: 0.20 * 1.0 = 0.20
        # duration: 0.10 * 1.0 = 0.10
        # max_sentiment: 0.0 * ... = 0
        # polarization: 0.0 * ... = 0
        # momentum: 0.2 * 1.0 = 0.2
        # Total = 0.12 + 0.35 + 0.20 + 0.10 + 0.2 = 0.97
        
        self.assertAlmostEqual(score, 0.97, places=2)

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
        
        # CORRECTED weights (sum to 1.0)
        # event: 0.15 * 0.8 = 0.12
        # intensity: 0.35 * 0.0 = 0.0
        # volume: 0.20 * 1.0 = 0.20
        # duration: 0.10
        # momentum: 0.2 * 0.0 = 0.0
        # Total = 0.12 + 0.0 + 0.20 + 0.10 + 0.0 = 0.42
        
        self.assertAlmostEqual(score, 0.42, places=2)

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
        
        # CORRECTED weights (sum to 1.0)
        # event: 0.15 * 0.8 = 0.12
        # intensity: 0.35 * 0.5 = 0.175
        # volume: 0.20
        # duration: 0.10
        # momentum: 0.2 * 0.5 = 0.1
        # Total = 0.12 + 0.175 + 0.20 + 0.10 + 0.1 = 0.695
        
        self.assertAlmostEqual(score, 0.695, places=3)

if __name__ == '__main__':
    unittest.main()
