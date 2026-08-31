"""
Display & Audio — MCP Server
================================
Monitor info, display settings, audio devices and volume.

Read-Only:
  - monitors: Connected monitors with resolution, refresh rate
  - display_settings: Scaling, DPI, orientation
  - audio_devices: Audio input/output devices
  - audio_volume: Current volume and mute state

Actions:
  - set_volume: Set system volume (0-100) or toggle mute
  - set_default_audio: Set default audio output device
"""

import asyncio
import json
import os
import subprocess
import tempfile

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Display & Audio",
    instructions=(
        "Display and audio management. Use 'monitors' for screen info, "
        "'audio_devices' for sound devices, 'audio_volume' for current level. "
        "'set_volume' to change volume."
    ),
)


def ps(cmd, timeout=15):
    script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + cmd.strip()
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False, encoding="utf-8") as f:
            f.write(script)
            path = f.name
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, timeout=timeout, encoding="utf-8", errors="replace"
        )
        try: os.unlink(path)
        except: pass
        return r.stdout.strip() if r.returncode == 0 and r.stdout else None
    except: return None


def ps_json(cmd, timeout=15):
    script = f"& {{\n{cmd.strip()}\n}} | ConvertTo-Json -Depth 3 -Compress"
    raw = ps(script, timeout)
    if raw:
        try: return json.loads(raw)
        except: pass
    return None


@mcp.tool()
async def monitors():
    """Connected monitors: name, resolution, refresh rate, video controller."""
    gpus = ps_json("""
        Get-CimInstance Win32_VideoController | ForEach-Object {
            @{
                Name = $_.Name
                Resolution = $_.VideoModeDescription
                RefreshRate = $_.CurrentRefreshRate
                DriverVersion = $_.DriverVersion
                RAM_MB = [math]::Round($_.AdapterRAM / 1MB, 0)
                Status = $_.Status
            }
        }
    """)

    monitors = ps_json("""
        Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue | ForEach-Object {
            @{
                Name = $_.Name
                ScreenWidth = $_.ScreenWidth
                ScreenHeight = $_.ScreenHeight
                MonitorType = $_.MonitorType
                DeviceID = $_.DeviceID
            }
        }
    """)

    # Also try WMI for more detail
    screens = ps_json("""
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
            @{
                DeviceName = $_.DeviceName
                Primary = $_.Primary
                Width = $_.Bounds.Width
                Height = $_.Bounds.Height
                BitsPerPixel = $_.BitsPerPixel
                WorkingArea = '{0}x{1}' -f $_.WorkingArea.Width, $_.WorkingArea.Height
            }
        }
    """)

    gpu_list = gpus if isinstance(gpus, list) else [gpus] if gpus else []
    mon_list = monitors if isinstance(monitors, list) else [monitors] if monitors else []
    scr_list = screens if isinstance(screens, list) else [screens] if screens else []

    return json.dumps({"video_controllers": gpu_list, "monitors": mon_list, "screens": scr_list}, indent=2, default=str)


@mcp.tool()
async def display_settings():
    """Display configuration: scaling, DPI, orientation."""
    settings = ps_json("""
        $dpi = Get-ItemProperty 'HKCU:\\Control Panel\\Desktop' -ErrorAction SilentlyContinue
        $scale = Get-ItemProperty 'HKCU:\\Control Panel\\Desktop\\WindowMetrics' -ErrorAction SilentlyContinue
        @{
            LogPixels = $dpi.LogPixels
            Win8DpiScaling = $dpi.Win8DpiScaling
            DpiScalingVer = $dpi.DpiScalingVer
            Wallpaper = $dpi.Wallpaper
            ScreenSaveActive = $dpi.ScreenSaveActive
            ScreenSaveTimeOut = $dpi.ScreenSaveTimeOut
        }
    """)

    return json.dumps({"display_settings": settings}, indent=2, default=str)


@mcp.tool()
async def audio_devices():
    """List all audio input and output devices."""
    devices = ps_json("""
        Get-CimInstance Win32_SoundDevice | ForEach-Object {
            @{
                Name = $_.Name
                Manufacturer = $_.Manufacturer
                Status = $_.Status
                DeviceID = $_.DeviceID
            }
        }
    """)

    # Try to get playback/recording devices via registry
    playback = ps_json("""
        Get-ChildItem 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render' -ErrorAction SilentlyContinue |
        ForEach-Object {
            $props = Get-ItemProperty "$($_.PSPath)\\Properties" -ErrorAction SilentlyContinue
            if ($props) {
                $name = $props.'{a45c254e-df1c-4efd-8020-67d146a850e0},2'
                if ($name) {
                    @{ Name = $name; DeviceId = $_.PSChildName; Type = 'Playback' }
                }
            }
        }
    """)

    dev_list = devices if isinstance(devices, list) else [devices] if devices else []
    play_list = playback if isinstance(playback, list) else [playback] if playback else []

    return json.dumps({"sound_devices": dev_list, "playback_devices": play_list}, indent=2, default=str)


@mcp.tool()
async def audio_volume():
    """Current system volume level and mute state."""
    volume = ps_json("""
        Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
    int _0(); int _1(); int _2(); int _3(); int _4(); int _5(); int _6();
    int GetMasterVolumeLevelScalar(out float level);
    int _8();
    int SetMasterVolumeLevelScalar(float level, System.Guid eventContext);
    int GetMute(out bool mute);
    int SetMute(bool mute, System.Guid eventContext);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice { int Activate(ref System.Guid id, int clsCtx, int activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface); }
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator { int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device); }
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}
public class Audio {
    public static float GetVolume() {
        var enumerator = new MMDeviceEnumerator() as IMMDeviceEnumerator;
        IMMDevice dev; enumerator.GetDefaultAudioEndpoint(0, 1, out dev);
        var iid = typeof(IAudioEndpointVolume).GUID;
        object o; dev.Activate(ref iid, 1, 0, out o);
        var vol = (IAudioEndpointVolume)o;
        float level; vol.GetMasterVolumeLevelScalar(out level);
        return level;
    }
    public static bool GetMute() {
        var enumerator = new MMDeviceEnumerator() as IMMDeviceEnumerator;
        IMMDevice dev; enumerator.GetDefaultAudioEndpoint(0, 1, out dev);
        var iid = typeof(IAudioEndpointVolume).GUID;
        object o; dev.Activate(ref iid, 1, 0, out o);
        var vol = (IAudioEndpointVolume)o;
        bool mute; vol.GetMute(out mute);
        return mute;
    }
}
'@ -ErrorAction SilentlyContinue

        $level = [Audio]::GetVolume()
        $mute = [Audio]::GetMute()
        @{ Volume_Percent = [math]::Round($level * 100, 0); Muted = $mute }
    """)

    if not volume:
        return json.dumps({"note": "Could not read volume — COM interop may need different permissions"})

    return json.dumps({"volume": volume}, indent=2, default=str)


@mcp.tool()
async def set_volume(level: int):
    """
    Set system volume level.

    Args:
        level: Volume 0-100
    """
    if level < 0 or level > 100:
        return json.dumps({"error": "Level must be 0-100"})

    scalar = level / 100.0
    ps(f"""
        Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
    int _0(); int _1(); int _2(); int _3(); int _4(); int _5(); int _6();
    int GetMasterVolumeLevelScalar(out float level);
    int _8();
    int SetMasterVolumeLevelScalar(float level, System.Guid eventContext);
    int GetMute(out bool mute);
    int SetMute(bool mute, System.Guid eventContext);
}}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {{ int Activate(ref System.Guid id, int clsCtx, int activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface); }}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {{ int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device); }}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {{}}
public class Audio {{
    public static void SetVolume(float level) {{
        var enumerator = new MMDeviceEnumerator() as IMMDeviceEnumerator;
        IMMDevice dev; enumerator.GetDefaultAudioEndpoint(0, 1, out dev);
        var iid = typeof(IAudioEndpointVolume).GUID;
        object o; dev.Activate(ref iid, 1, 0, out o);
        ((IAudioEndpointVolume)o).SetMasterVolumeLevelScalar(level, System.Guid.Empty);
    }}
}}
'@ -ErrorAction SilentlyContinue
        [Audio]::SetVolume({scalar}f)
    """)

    return json.dumps({"action": "set_volume", "level": level}, indent=2)


@mcp.tool()
async def set_default_audio(device_name: str):
    """
    Set default audio output device by name (partial match).
    Note: May not work on all Windows versions without third-party tools.

    Args:
        device_name: Audio device name (partial match)
    """
    # Try with nircmd if available
    nircmd = run_cmd(["where", "nircmd"])
    if nircmd:
        subprocess.run(["nircmd", "setdefaultsounddevice", device_name], capture_output=True, timeout=5)
        return json.dumps({"action": "set_default_audio", "device": device_name, "method": "nircmd"}, indent=2)

    return json.dumps({
        "action": "set_default_audio",
        "device": device_name,
        "error": "nircmd not found — install nircmd.exe or use Windows Sound Settings manually",
        "alternative": "ms-settings:sound"
    }, indent=2)


def run_cmd(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else None
    except: return None


if __name__ == "__main__":
    mcp.run()
