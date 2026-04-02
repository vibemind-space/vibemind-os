"""
Setup script for Cell CLI.
"""

from setuptools import setup, find_packages

setup(
    name="cell-cli",
    version="0.1.0",
    description="CLI tool for managing Cell Colony deployments",
    author="Coding Engine",
    author_email="info@codingengine.dev",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.0.0",
        "rich>=13.0.0",
        "httpx>=0.24.0",
    ],
    entry_points={
        "console_scripts": [
            "cell=cell_cli.main:main",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
    ],
)
