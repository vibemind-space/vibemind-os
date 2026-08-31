# Visual Studio Build Tools Installation

## Problem Found

Your system has:
- OK: CUDA Toolkit 11.6 (nvcc found)
- OK: Python 3.11.0
- OK: PyTorch 2.5.1+cu118
- **MISSING: C++ Compiler (cl.exe)**

The mamba-ssm compilation requires a C++ compiler to build CUDA extensions.

## Solution: Install Visual Studio Build Tools

Time: 10-15 minutes

### Step 1: Download (2-3 Min)

1. Open this link in your browser:
   ```
   https://visualstudio.microsoft.com/visual-cpp-build-tools/
   ```

2. Click "Download Build Tools"

3. File: `vs_BuildTools.exe` (~4 MB installer, downloads more during installation)

### Step 2: Install (8-12 Min)

1. Run `vs_BuildTools.exe`

2. In the installer, select:
   - **Desktop development with C++** (main checkbox)

3. On the right side, ensure these are checked:
   - MSVC v143 - VS 2022 C++ x64/x86 build tools (Latest)
   - Windows 10/11 SDK (Latest)
   - C++ CMake tools for Windows

4. Click **Install**

5. Wait 8-12 minutes (downloads and installs ~6 GB)

### Step 3: Restart (Optional but Recommended)

After installation:
- Close all terminals
- Optionally reboot system (recommended)

### Step 4: Verify Installation

Open a **NEW** terminal and run:
```bash
where cl
```

Expected output:
```
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\...\cl.exe
```

### Step 5: Install Mamba

After Build Tools are installed, run:
```bash
python install_mamba_direct.py
```

This should now work!

## Alternative: Visual Studio Community

If you prefer the full Visual Studio IDE (includes Build Tools):

1. Download: https://visualstudio.microsoft.com/vs/community/
2. Install with "Desktop development with C++" workload
3. Same result, but includes IDE

## Quick Start After Installation

```bash
# 1. Verify C++ compiler
where cl

# 2. Install Mamba
python install_mamba_direct.py

# 3. Test
python mamba_real_integration.py
```

## Why is this needed?

Mamba-SSM and causal-conv1d include custom CUDA kernels written in C++/CUDA. These need to be compiled from source on Windows. The compilation requires:

1. **nvcc** - CUDA compiler (you have this: CUDA 11.6 OK)
2. **cl.exe** - Microsoft C++ compiler (you need this: MISSING!)

Both compilers work together to build the CUDA extensions.

## Timeline

```
Download Build Tools:  2-3 minutes
Install Build Tools:   8-12 minutes
Restart Terminal:      1 minute
Install Mamba:         5-10 minutes
-----------------------------------------
TOTAL:                 ~20-25 minutes
```

Much faster than downloading/installing CUDA 11.8 (which you don't need)!

## Next Steps

1. Download and install Visual Studio Build Tools
2. Open new terminal
3. Run: `python install_mamba_direct.py`
4. Done!

Your CUDA 11.6 is perfectly fine - it's 100% compatible with PyTorch cu118 and mamba-ssm!
