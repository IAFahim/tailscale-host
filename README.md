# tailscale-host

Cross-platform host telemetry helper for Tailscale + Deskflow fleets:
- `discover_gui_env()` — finds live Wayland/Hyprland/X11/DBus session variables on Linux
- `get_tailscale_info()` — queries Tailscale IPv4, hostname, and MagicDNS name
- `get_os_info()` — reports normalized OS name and distro/release details
- `get_displays()` — reads active monitor geometry (`Win32`, `hyprctl`, `wlr-randr`, `xrandr`) with safe fallback
- `find_deskflow_core()` — locates the `deskflow-core` executable
