"""
Setup script for building ATM-R C++ extensions with pybind11.

Usage:
    python setup_cpp.py build_ext --inplace
"""

from setuptools import setup, Extension
from pybind11.setup_helpers import Pybind11Extension, build_ext
import sys
import os

# Determine C++ compiler flags
if sys.platform == 'win32':
    extra_compile_args = ['/O2', '/std:c++17']
elif sys.platform == 'darwin':
    extra_compile_args = ['-O3', '-std=c++17', '-stdlib=libc++']
else:  # Linux
    extra_compile_args = ['-O3', '-std=c++17', '-march=native']

# Define extension
ext_modules = [
    Pybind11Extension(
        "atmr_cpp",
        ["cpp/atmr_core.cpp"],
        extra_compile_args=extra_compile_args,
        cxx_std=17,
    ),
]

setup(
    name="atmr_cpp",
    version="0.1.0",
    author="ATM-R Project",
    description="High-performance C++ core for ATM-R",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
    python_requires=">=3.8",
)
