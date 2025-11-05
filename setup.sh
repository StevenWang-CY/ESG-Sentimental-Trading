#!/bin/bash
# Setup script for ESG Sentiment Trading Strategy
# Run this script to set up your environment

set -e  # Exit on error

echo "=================================="
echo "ESG Sentiment Trading Setup"
echo "=================================="
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check Python version
echo "[1/7] Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version detected"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[2/7] Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "[2/7] Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "[3/7] Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "[4/7] Upgrading pip..."
pip install --upgrade pip --quiet
echo "✓ pip upgraded"
echo ""

# Install requirements
echo "[5/7] Installing dependencies..."
echo "This may take a few minutes..."
pip install -r requirements.txt --quiet
echo "✓ All dependencies installed"
echo ""

# Create necessary directories
echo "[6/7] Creating project directories..."
mkdir -p data/raw data/processed data/signals
mkdir -p models
mkdir -p results/backtest results/plots
mkdir -p logs
mkdir -p notebooks
mkdir -p tests
echo "✓ Directories created"
echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "[7/7] Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created from template"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your API keys!"
else
    echo "[7/7] .env file already exists"
fi
echo ""

# Verify installation
echo "=================================="
echo "Verifying Installation"
echo "=================================="
echo ""

echo "Testing imports..."
python3 << 'EOF'
import sys
import warnings
warnings.filterwarnings('ignore')

print("✓ Core packages:")
import numpy as np
print(f"  - numpy {np.__version__}")
import pandas as pd
print(f"  - pandas {pd.__version__}")
import scipy
print(f"  - scipy {scipy.__version__}")
import sklearn
print(f"  - scikit-learn {sklearn.__version__}")

print("\n✓ Financial packages:")
import yfinance as yf
print(f"  - yfinance {yf.__version__}")
import tweepy
print(f"  - tweepy {tweepy.__version__}")

print("\n✓ New ML modules:")
sys.path.insert(0, '.')
from src.nlp.word_correlation_analyzer import WordCorrelationAnalyzer
print("  - word_correlation_analyzer")
from src.nlp.temporal_feature_extractor import TemporalFeatureExtractor
print("  - temporal_feature_extractor")
from src.nlp.esg_sentiment_dictionaries import ESGSentimentDictionaries
print("  - esg_sentiment_dictionaries")
from src.ml.categorical_classifier import CategoricalSignalClassifier
print("  - categorical_classifier")
from src.ml.feature_selector import FeatureSelector
print("  - feature_selector")
from src.ml.enhanced_pipeline import EnhancedESGPipeline
print("  - enhanced_pipeline")

print("\n✅ All imports successful!")
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "=================================="
    echo "✅ Setup Complete!"
    echo "=================================="
    echo ""
    echo "Next steps:"
    echo "1. Edit .env file with your API keys (especially Twitter bearer token)"
    echo "2. Run the example: python examples/enhanced_pipeline_example.py"
    echo "3. Read documentation: QUICK_START.md"
    echo ""
    echo "To activate the environment in future sessions:"
    echo "  source venv/bin/activate"
    echo ""
else
    echo ""
    echo "❌ Setup encountered errors"
    echo "Please check the error messages above"
    exit 1
fi
