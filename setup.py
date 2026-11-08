# -*- coding: utf-8 -*-
"""
Setup script for orderbook-reconstruction project.
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="orderbook-reconstruction",
    version="0.2.0",
    author="Jerry",  # 请替换为你的名字
    author_email="dominatorid001@163.com",  # 请替换为你的邮箱
    description="Reconstruct 10-level order book from tick-by-tick data and evaluate OBI factor",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dominatorid001Jerry/orderbook-reconstruction",  # 请替换为你的仓库地址
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Financial and Insurance Industry",
        "Intended Audience :: Science/Research",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "pyarrow>=12.0.0",
        "matplotlib>=3.7.0",
        "py7zr>=0.20.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "flake8>=6.0.0",
            "black>=23.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "orderbook-validate=validate_real:main",
            "orderbook-demo=run_demo:main",
        ],
    },
    keywords="orderbook, market microstructure, high-frequency trading, factor, quantitative finance",
    project_urls={
        "Bug Reports": "https://github.com/dominatorid001Jerry/orderbook-reconstruction/issues",
        "Source": "https://github.com/dominatorid001Jerry/orderbook-reconstruction",
        "Documentation": "https://github.com/dominatorid001Jerry/orderbook-reconstruction/blob/main/README.md",
    },
)
