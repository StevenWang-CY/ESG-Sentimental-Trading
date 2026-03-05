# Contributing to ESG Sentimental Trading

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/ESG-Sentimental-Trading.git
   cd ESG-Sentimental-Trading
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   # venv\Scripts\activate   # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API credentials (Reddit, Twitter, etc.)
   ```

## Running Tests

```bash
pytest
pytest --cov=src  # with coverage
```

## How to Contribute

### Reporting Bugs

Open an issue using the **Bug Report** template. Include:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

### Suggesting Features

Open an issue using the **Feature Request** template describing your idea and its use case.

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run the test suite and ensure all tests pass
5. Commit with a clear message (`git commit -m "feat: add new feature"`)
6. Push to your fork and open a Pull Request

### Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation only
- `test:` adding or updating tests
- `refactor:` code change that neither fixes a bug nor adds a feature

## Code Style

- Follow PEP 8
- Use type hints where practical
- Keep functions focused and well-named
- Add docstrings to public functions

## Questions?

Open a discussion or issue if anything is unclear. We're happy to help!
