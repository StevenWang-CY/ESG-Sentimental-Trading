# Installation Guide

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Internet connection (for downloading data)

## Step-by-Step Installation

### 1. Navigate to Project Directory

```bash
cd "/Users/chuyuewang/Desktop/Finance/Personal Projects/ESG-Sentimental-Trading"
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
```

Activate the virtual environment:

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

### 3. Install Core Dependencies

```bash
pip install --upgrade pip
pip install numpy pandas scipy scikit-learn
pip install yfinance pandas-datareader
pip install beautifulsoup4 lxml requests
pip install statsmodels pyyaml tqdm
pip install matplotlib seaborn
```

Or install all at once:

```bash
pip install -r requirements.txt
```

### 4. Optional: Install Advanced NLP Features

For FinBERT and ML-based event detection:

```bash
# For CPU
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers

# For GPU (if available)
pip install torch transformers
```

### 5. Optional: Install SEC Filing Downloader

```bash
pip install sec-edgar-downloader
```

### 6. Verify Installation

Run the demo to test everything works:

```bash
python main.py --mode demo
```

You should see output like:

```
ESG EVENT-DRIVEN ALPHA STRATEGY
Mode: demo
...
>>> DEMO COMPLETE
```

## Installation Verification Checklist

- [ ] Python 3.8+ installed
- [ ] Virtual environment created
- [ ] Core dependencies installed (pandas, numpy, etc.)
- [ ] Demo mode runs successfully
- [ ] No import errors

## Troubleshooting

### Issue: "No module named 'pandas'"

**Solution:**
```bash
pip install pandas
```

### Issue: "command not found: python"

**Solution:** Try using `python3` instead:
```bash
python3 main.py --mode demo
```

### Issue: SSL Certificate Error

**Solution:**
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org <package-name>
```

### Issue: Permission Denied

**Solution:** Use `--user` flag:
```bash
pip install --user -r requirements.txt
```

## Optional Components

### Jupyter Notebooks

To run the example notebooks:

```bash
pip install jupyter notebook ipykernel
jupyter notebook
```

Then open `notebooks/01_quick_start.ipynb`

### Development Tools

For development and testing:

```bash
pip install pytest pytest-cov black flake8
```

## Minimum Installation (No External APIs)

The project works with just these core packages:

```bash
pip install numpy pandas pyyaml
```

This allows you to:
- ✓ Run demo mode with mock data
- ✓ Test signal generation
- ✓ Basic backtesting
- ✗ Download real SEC filings
- ✗ Fetch real price data
- ✗ Use advanced NLP models

## Full Installation (All Features)

For complete functionality:

```bash
# Core
pip install -r requirements.txt

# ML/NLP
pip install torch transformers

# SEC Data
pip install sec-edgar-downloader

# Social Media (requires API keys)
pip install tweepy praw

# Notebooks
pip install jupyter notebook
```

## Configuration

After installation, edit [config/config.yaml](config/config.yaml):

1. **Required:** Add your email for SEC EDGAR:
```yaml
data:
  sec:
    email: "your-email@example.com"
```

2. **Optional:** Add API keys for advanced features:
```yaml
social_media:
  twitter_bearer_token: "YOUR_TOKEN"
```

## Next Steps

1. Run the demo: `python main.py --mode demo`
2. Read the [README.md](README.md) for usage instructions
3. Try the quick start notebook: `notebooks/01_quick_start.ipynb`
4. Customize the configuration in `config/config.yaml`
5. Run with real data: `python main.py --mode full`

## Getting Help

If you encounter issues:

1. Check the [README.md](README.md) Troubleshooting section
2. Verify all dependencies are installed: `pip list`
3. Check Python version: `python --version` (should be 3.8+)
4. Try running in demo mode first to isolate issues

## Uninstallation

To remove the virtual environment:

```bash
deactivate  # Exit virtual environment
rm -rf venv/  # Delete virtual environment folder
```

To uninstall packages:

```bash
pip uninstall -r requirements.txt -y
```
