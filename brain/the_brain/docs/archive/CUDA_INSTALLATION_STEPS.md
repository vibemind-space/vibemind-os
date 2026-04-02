# CUDA 11.8 Installation - Schritt für Schritt

**Geschätzte Zeit:** 40-60 Minuten
**Status:** In Progress...

---

## ✅ **Schritt 1: Download (10-15 Min)**

**JETZT:** Öffnen Sie diesen Link in Ihrem Browser:

```
https://developer.nvidia.com/cuda-11-8-0-download-archive
```

**Auf der Webseite wählen:**
- [ ] Operating System: **Windows**
- [ ] Architecture: **x86_64**
- [ ] Version: **10**
- [ ] Installer Type: **exe (local)** ← WICHTIG: LOCAL!

**Download Button klicken:**
- Datei: `cuda_11.8.0_522.06_windows.exe`
- Größe: 3.5 GB
- Speichern: Desktop oder Downloads

**Download läuft...** ⏳

Zeit für einen Kaffee! ☕

---

## ⏸️ **Schritt 2: Vorbereitung (während Download)**

**Programme schließen:**
- [ ] Alle Python-Terminals
- [ ] Laufende Python-Scripts
- [ ] Jupyter Notebooks
- [ ] IDEs (VSCode, PyCharm, etc.)

**Speichern Sie Ihre Arbeit!**

**Monitoring-Dashboards stoppen:**
Wenn noch aktiv:
```
Ctrl+C in den Terminal-Fenstern mit:
- monitor_web.py
- monitor_web_ctm.py
```

---

## 📦 **Schritt 3: Installation (20-30 Min)**

**Wenn Download fertig:**

1. **Doppelklick auf:**
   ```
   cuda_11.8.0_522.06_windows.exe
   ```

2. **UAC Dialog:** Klicken Sie "Ja" (Admin-Rechte)

3. **CUDA Installer öffnet sich:**

   **Schritt 3.1: Temp Extraction**
   - Installer entpackt Dateien (~2 Min)
   - Fortschrittsbalken wird angezeigt
   - Warten Sie...

   **Schritt 3.2: System Check**
   - Installer prüft Ihr System
   - Prüft GPU-Kompatibilität
   - ✓ Sollte erfolgreich sein (RTX 3060 ist kompatibel)

   **Schritt 3.3: Installation Type**
   ⚡ **WICHTIG:** Wählen Sie:
   ```
   ○ Custom (Advanced)
   ● Express (Recommended)  ← WÄHLEN SIE DIESE!
   ```

   **Warum Express?**
   - Installiert alles was Sie brauchen
   - Keine manuelle Komponentenauswahl
   - Automatische Konfiguration

   **Schritt 3.4: Installation läuft**
   - Dauer: 20-30 Minuten
   - Fortschrittsbalken zeigt Status
   - **NICHT abbrechen!**

   Sie sehen Meldungen wie:
   ```
   Installing CUDA Toolkit...
   Installing CUDA Runtime...
   Installing CUDA Documentation...
   Installing CUDA Samples...
   Configuring Environment Variables...
   ```

   **Schritt 3.5: Fertigstellung**
   - Installer zeigt "Installation Complete"
   - Klicken Sie "Close"

---

## 🔄 **Schritt 4: System Reboot (2 Min)**

**⚡ WICHTIG: System-Neustart ist PFLICHT!**

Warum?
- Environment Variables werden geladen
- CUDA Driver wird aktiviert
- Path-Einträge werden übernommen

**Aktion:**
```
Windows → Neustart
```

**Oder im Terminal:**
```
shutdown /r /t 0
```

---

## ⏳ **PAUSE: Warten auf Reboot...**

System startet neu...

---

## ✅ **Schritt 5: Verifikation (2 Min)**

**Nach Reboot, Terminal öffnen und testen:**

```bash
# Test 1: NVCC Compiler
nvcc --version

# Erwartete Ausgabe:
# Cuda compilation tools, release 11.8, V11.8.89
```

**Wenn das funktioniert:** ✅ CUDA Toolkit installiert!

**Wenn "nvcc not found":**
- Terminal neu öffnen (wichtig!)
- Wenn immer noch nicht: Environment Variables prüfen (siehe unten)

---

## 🐍 **Schritt 6: Mamba Installation (5-15 Min)**

**Im Terminal:**

```bash
cd C:\Users\User\Desktop\Tahlamus

# Status prüfen
python check_mamba_installation.py

# Sollte zeigen: nvcc gefunden!
```

**Installation starten:**

```bash
# Schritt 6.1: causal-conv1d (3-5 Min)
pip install causal-conv1d>=1.2.0 --no-cache-dir

# Sie sehen:
# Building wheel for causal-conv1d...
# Compiling CUDA kernels...
# [Fortschritt...]
# Successfully installed causal-conv1d-X.X.X

# Schritt 6.2: mamba-ssm (5-10 Min)
pip install mamba-ssm --no-cache-dir

# Sie sehen:
# Building wheel for mamba-ssm...
# Compiling CUDA kernels...
# [Fortschritt...]
# Successfully installed mamba-ssm-X.X.X
```

---

## 🧪 **Schritt 7: Test (2 Min)**

**Test 1: Import**
```bash
python -c "from mamba_ssm import Mamba; print('✓ Mamba imported!')"
```

**Test 2: CUDA Funktionalität**
```bash
python -c "import torch; from mamba_ssm import Mamba; m = Mamba(d_model=64).cuda(); print('✓ Mamba on CUDA works!')"
```

**Test 3: Vollständiger Test**
```bash
python mamba_real_integration.py
```

**Erwartete Ausgabe:**
```
OK: Echtes Mamba verfuegbar!
>> Initialisiere ECHTES Mamba fuer jede Modalitaet...
  vision: RealMambaModule initialized (CUDA)
  ...
```

---

## 🎉 **Schritt 8: Fertig!**

**Sie haben jetzt:**
- ✅ CUDA Toolkit 11.8
- ✅ NVCC Compiler
- ✅ Mamba-SSM mit CUDA
- ✅ 100x Performance-Boost!

**Testen Sie Ihre CTM-ATM-R Anwendungen:**
```bash
python ctm_use_cases.py       # Mit echtem Mamba
python monitor_web_ctm.py     # Dashboard
python mamba_real_integration.py  # Demo
```

---

## 🔧 **Troubleshooting**

### Problem 1: "nvcc not found" nach Installation

**Lösung:**
1. Terminal NEU öffnen (wichtig!)
2. `nvcc --version` erneut probieren
3. Wenn immer noch nicht:

**Environment Variables prüfen:**
```
Windows-Suche: "Umgebungsvariablen"
→ "Umgebungsvariablen für dieses Konto bearbeiten"
→ PATH Variable prüfen
→ Sollte enthalten:
  C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\bin
```

### Problem 2: "Building wheel failed" bei pip install

**Mögliche Ursachen:**
- C++ Compiler fehlt (Visual Studio Build Tools)
- CUDA Toolkit nicht richtig installiert
- PATH nicht gesetzt

**Lösung:**
```bash
# Visual Studio Build Tools installieren:
# https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
```

### Problem 3: "CUDA out of memory" bei Test

**Lösung:**
- Reduzieren Sie d_model (z.B. 64 statt 128)
- Oder nutzen Sie CPU: `device='cpu'`

---

## 📊 **Zeit-Tracking**

| Schritt | Zeit | Status |
|---------|------|--------|
| Download | 10-15 Min | ⏳ |
| Vorbereitung | 2 Min | ⏳ |
| Installation | 20-30 Min | ⏳ |
| Reboot | 2 Min | ⏳ |
| Verifikation | 2 Min | ⏳ |
| Mamba Install | 5-15 Min | ⏳ |
| Testing | 2 Min | ⏳ |
| **TOTAL** | **40-60 Min** | ⏳ |

---

## 📞 **Support**

**Bei Fragen oder Problemen:**
- Führen Sie aus: `python check_mamba_installation.py`
- Lesen Sie: `MAMBA_INSTALLATION_GUIDE.md`
- Oder melden Sie sich zurück!

---

**Erstellt:** 2025-10-13
**Status:** ⏳ In Progress...
**Ziel:** 100x Performance mit echtem Mamba! 🚀
