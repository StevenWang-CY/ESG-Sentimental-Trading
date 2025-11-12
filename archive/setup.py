"""
Setup script for ESG Event-Driven Alpha Strategy
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
if readme_file.exists():
    with open(readme_file, encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = "ESG Event-Driven Alpha Strategy"

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    with open(requirements_file) as f:
        requirements = [
            line.strip() for line in f
            if line.strip() and not line.startswith('#')
        ]
else:
    requirements = []

setup(
    name="esg-event-alpha",
    version="1.0.0",
    author="ESG Quant Research Team",
    author_email="research@example.com",
    description="Quantitative ESG Event-Driven Alpha Strategy",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/esg-event-alpha",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        'ml': ['transformers>=4.30.0', 'torch>=2.0.0'],
        'social': ['tweepy>=4.14.0', 'praw>=7.7.0'],
        'notebooks': ['jupyter>=1.0.0', 'ipykernel>=6.25.0'],
        'dev': ['pytest>=7.3.0', 'pytest-cov>=4.1.0', 'black>=23.0.0'],
    },
    entry_points={
        'console_scripts': [
            'esg-strategy=main:main',
        ],
    },
)
