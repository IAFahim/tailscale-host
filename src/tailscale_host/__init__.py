"""Cross-platform Tailscale, OS, monitor geometry, and deskflow-core detector."""
from __future__ import annotations

import glob
import json
import os
import platform
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "discover_gui_env",
    "find_tailscale_bin",
    "get_tailscale_info",
    "get_os_info",
    "get_displays",
    "find_deskflow_core",
]

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _run(cmd: List[str], timeout: float = 3.0, env: Optional[Dict[str, str]] = None) -> Optional[str]:
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            creationflags=_NO_WINDOW,
        )
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None


def discover_gui_env() -> Dict[str, str]:
    """Discover live Wayland/Hyprland/X11 env vars on Linux when launched from SSH/systemd."""
    env = os.environ.copy()
    if os.name != "posix" or platform.system().lower() == "darwin":
        return env
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    runtime_dir = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    if os.path.isdir(runtime_dir):
        env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
        if not env.get("WAYLAND_DISPLAY"):
            socks = sorted(glob.glob(os.path.join(runtime_dir, "wayland-*")))
            socks = [s for s in socks if not s.endswith(".lock")]
            if socks:
                env["WAYLAND_DISPLAY"] = os.path.basename(socks[0])
        if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
            hypr_dirs = sorted(glob.glob(os.path.join(runtime_dir, "hypr", "*")))
            if hypr_dirs:
                env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(hypr_dirs[-1])
        if not env.get("DBUS_SESSION_BUS_ADDRESS"):
            bus = os.path.join(runtime_dir, "bus")
            if os.path.exists(bus):
                env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={bus}"
    if not env.get("DISPLAY"):
        x_socks = sorted(glob.glob("/tmp/.X11-unix/X*"))
        if x_socks:
            num = os.path.basename(x_socks[0])[1:]
            if num.isdigit():
                env["DISPLAY"] = f":{num}"
    return env


def find_tailscale_bin() -> Optional[str]:
    found = shutil.which("tailscale")
    if found:
        return found
    win_default = r"C:\Program Files\Tailscale\tailscale.exe"
    if os.name == "nt" and os.path.exists(win_default):
        return win_default
    return None


def get_tailscale_info() -> Dict[str, Any]:
    ts_bin = find_tailscale_bin()
    fallback_host = socket.gethostname()
    if not ts_bin:
        return {"tailscale_ok": False, "ip": "", "hostname": fallback_host, "dns_name": ""}
    out = _run([ts_bin, "status", "--self", "--json"], timeout=3.0)
    if not out:
        return {"tailscale_ok": False, "ip": "", "hostname": fallback_host, "dns_name": ""}
    try:
        data = json.loads(out)
        self_info = data.get("Self") or {}
        ips = self_info.get("TailscaleIPs") or []
        ipv4 = next((ip for ip in ips if "." in ip), ips[0] if ips else "")
        hostname = str(self_info.get("HostName") or fallback_host)
        dns_name = str(self_info.get("DNSName") or "").rstrip(".")
        running = data.get("BackendState", "Running") == "Running"
        return {
            "tailscale_ok": bool(ipv4) and running,
            "ip": ipv4,
            "hostname": hostname,
            "dns_name": dns_name,
        }
    except Exception:
        return {"tailscale_ok": False, "ip": "", "hostname": fallback_host, "dns_name": ""}


def get_os_info() -> Dict[str, str]:
    sysname = platform.system().lower()
    if sysname == "windows":
        return {"os": "windows", "os_detail": f"Windows {platform.release()}"}
    if sysname == "darwin":
        return {"os": "macos", "os_detail": "macOS"}
    detail = "Linux"
    try:
        os_rel = Path("/etc/os-release")
        if os_rel.exists():
            txt = os_rel.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', txt, re.M)
            if m:
                detail = m.group(1)
    except Exception:
        pass
    return {"os": "linux", "os_detail": detail}


def _windows_displays_ctypes() -> Optional[Dict[str, Any]]:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        monitors: List[Dict[str, Any]] = []
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
        )

        def _cb(hmon, _hdc, _lprect, _lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                monitors.append(
                    {
                        "name": info.szDevice or f"Display{len(monitors) + 1}",
                        "x": int(r.left),
                        "y": int(r.top),
                        "width": int(r.right - r.left),
                        "height": int(r.bottom - r.top),
                        "primary": bool(info.dwFlags & 1),
                    }
                )
            return True

        cb = MONITORENUMPROC(_cb)
        user32.EnumDisplayMonitors(None, None, cb, 0)
        if monitors:
            min_x = min(m["x"] for m in monitors)
            min_y = min(m["y"] for m in monitors)
            max_x = max(m["x"] + m["width"] for m in monitors)
            max_y = max(m["y"] + m["height"] for m in monitors)
            return {"width": max(1, max_x - min_x), "height": max(1, max_y - min_y), "monitors": monitors}
    except Exception:
        pass
    return None


def _linux_displays(env: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if shutil.which("hyprctl") and env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        out = _run(["hyprctl", "monitors", "-j"], timeout=2.5, env=env)
        if out:
            try:
                raw = json.loads(out)
                monitors = []
                for m in raw:
                    scale = float(m.get("scale") or 1.0)
                    w = int(round(float(m.get("width", 1920)) / scale))
                    h = int(round(float(m.get("height", 1080)) / scale))
                    monitors.append(
                        {
                            "name": str(m.get("name") or "Monitor"),
                            "x": int(m.get("x", 0)),
                            "y": int(m.get("y", 0)),
                            "width": w,
                            "height": h,
                            "primary": bool(m.get("focused", False)),
                        }
                    )
                if monitors:
                    if not any(m["primary"] for m in monitors):
                        monitors[0]["primary"] = True
                    min_x = min(m["x"] for m in monitors)
                    min_y = min(m["y"] for m in monitors)
                    max_x = max(m["x"] + m["width"] for m in monitors)
                    max_y = max(m["y"] + m["height"] for m in monitors)
                    return {"width": max(1, max_x - min_x), "height": max(1, max_y - min_y), "monitors": monitors}
            except Exception:
                pass
    if shutil.which("wlr-randr") and env.get("WAYLAND_DISPLAY"):
        out = _run(["wlr-randr", "--json"], timeout=2.5, env=env)
        if out:
            try:
                raw = json.loads(out)
                monitors = []
                for m in raw:
                    if not m.get("enabled", True):
                        continue
                    pos = m.get("position") or {}
                    cur_mode = next((md for md in (m.get("modes") or []) if md.get("current")), None)
                    if not cur_mode:
                        continue
                    scale = float(m.get("scale") or 1.0)
                    w = int(round(float(cur_mode.get("width", 1920)) / scale))
                    h = int(round(float(cur_mode.get("height", 1080)) / scale))
                    monitors.append(
                        {
                            "name": str(m.get("name") or "Monitor"),
                            "x": int(pos.get("x", 0)),
                            "y": int(pos.get("y", 0)),
                            "width": w,
                            "height": h,
                            "primary": False,
                        }
                    )
                if monitors:
                    monitors[0]["primary"] = True
                    min_x = min(m["x"] for m in monitors)
                    min_y = min(m["y"] for m in monitors)
                    max_x = max(m["x"] + m["width"] for m in monitors)
                    max_y = max(m["y"] + m["height"] for m in monitors)
                    return {"width": max(1, max_x - min_x), "height": max(1, max_y - min_y), "monitors": monitors}
            except Exception:
                pass
    if shutil.which("xrandr") and env.get("DISPLAY"):
        out = _run(["xrandr", "--current"], timeout=2.5, env=env)
        if out:
            monitors = []
            for m in re.finditer(r"^(\S+)\s+connected\s+(primary\s+)?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", out, re.M):
                monitors.append(
                    {
                        "name": m.group(1),
                        "x": int(m.group(5)),
                        "y": int(m.group(6)),
                        "width": int(m.group(3)),
                        "height": int(m.group(4)),
                        "primary": bool(m.group(2)),
                    }
                )
            if monitors:
                if not any(mon["primary"] for mon in monitors):
                    monitors[0]["primary"] = True
                min_x = min(mon["x"] for mon in monitors)
                min_y = min(mon["y"] for mon in monitors)
                max_x = max(mon["x"] + mon["width"] for mon in monitors)
                max_y = max(mon["y"] + mon["height"] for mon in monitors)
                return {"width": max(1, max_x - min_x), "height": max(1, max_y - min_y), "monitors": monitors}
    return None


def get_displays(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    if os.name == "nt":
        res = _windows_displays_ctypes()
        if res:
            return res
    else:
        res = _linux_displays(env or discover_gui_env())
        if res:
            return res
    return {"width": 1920, "height": 1080, "monitors": [{"name": "Primary", "x": 0, "y": 0, "width": 1920, "height": 1080, "primary": True}]}


def find_deskflow_core() -> Optional[str]:
    found = shutil.which("deskflow-core")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Deskflow\deskflow-core.exe",
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Deskflow", "deskflow-core.exe"),
        "/usr/bin/deskflow-core",
        "/usr/local/bin/deskflow-core",
        "/run/current-system/sw/bin/deskflow-core",
        "/Applications/Deskflow.app/Contents/MacOS/deskflow-core",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None
