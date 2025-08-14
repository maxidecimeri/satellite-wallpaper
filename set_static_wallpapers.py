# set_static_wallpapers.py
# Sets per-monitor static wallpapers on Windows (leaves your WE/live monitor untouched)
# Requires: pip install comtypes

import os
import random
from pathlib import Path
from datetime import datetime
from typing import List

from config_loader import STATIC_DIR  # points to .../static_backgrounds
# Optional: live monitor index from config; default to last monitor if missing
try:
    from config_loader import _cfg  # we just peek for 'live_monitor_index'
    LIVE_MONITOR_INDEX = int(_cfg.get("live_monitor_index", -1))
except Exception:
    LIVE_MONITOR_INDEX = -1

# --- COM setup via comtypes (IDesktopWallpaper) ---
import comtypes
from comtypes import GUID, HRESULT, COMMETHOD
from comtypes.automation import BSTR
from ctypes import wintypes, POINTER, Structure, c_uint

# RECT for GetMonitorRECT if you want to inspect geometry (not strictly needed here)
class RECT(Structure):
    _fields_ = [
        ("left",   wintypes.LONG),
        ("top",    wintypes.LONG),
        ("right",  wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

# IDesktopWallpaper interface
# https://learn.microsoft.com/windows/win32/api/shobjidl_core/nn-shobjidl_core-idesktopwallpaper
class IDesktopWallpaper(comtypes.IUnknown):
    _iid_ = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
    _methods_ = [
        # HRESULT SetWallpaper([in] LPCWSTR monitorID, [in] LPCWSTR wallpaper);
        COMMETHOD([], HRESULT, 'SetWallpaper', (['in'], wintypes.LPCWSTR, 'monitorID'),
                                             (['in'], wintypes.LPCWSTR, 'wallpaper')),
        # HRESULT GetWallpaper([in] LPCWSTR monitorID, [out] LPWSTR *wallpaper);
        COMMETHOD([], HRESULT, 'GetWallpaper', (['in'], wintypes.LPCWSTR, 'monitorID'),
                                             (['out'], POINTER(BSTR), 'wallpaper')),
        # HRESULT GetMonitorDevicePathAt([in] UINT monitorIndex, [out] LPWSTR *monitorID);
        COMMETHOD([], HRESULT, 'GetMonitorDevicePathAt', (['in'], c_uint, 'monitorIndex'),
                                                    (['out'], POINTER(BSTR), 'monitorID')),
        # HRESULT GetMonitorDevicePathCount([out] UINT *count);
        COMMETHOD([], HRESULT, 'GetMonitorDevicePathCount', (['out'], POINTER(c_uint), 'count')),
        # HRESULT GetMonitorRECT([in] LPCWSTR monitorID, [out] RECT *displayRect);
        COMMETHOD([], HRESULT, 'GetMonitorRECT', (['in'], wintypes.LPCWSTR, 'monitorID'),
                                              (['out'], POINTER(RECT), 'displayRect')),
        # HRESULT SetBackgroundColor([in] COLORREF color);
        COMMETHOD([], HRESULT, 'SetBackgroundColor', (['in'], wintypes.UINT, 'color')),
        # HRESULT GetBackgroundColor([out] COLORREF *color);
        COMMETHOD([], HRESULT, 'GetBackgroundColor', (['out'], POINTER(wintypes.UINT), 'color')),
        # HRESULT SetPosition([in] DESKTOP_WALLPAPER_POSITION position);
        COMMETHOD([], HRESULT, 'SetPosition', (['in'], c_uint, 'position')),
        # HRESULT GetPosition([out] DESKTOP_WALLPAPER_POSITION *position);
        COMMETHOD([], HRESULT, 'GetPosition', (['out'], POINTER(c_uint), 'position')),
        # HRESULT SetSlideshow([in] IShellItemArray *items);
        COMMETHOD([], HRESULT, 'SetSlideshow', (['in'], comtypes.c_void_p, 'items')),
        # HRESULT GetSlideshow([out] IShellItemArray **items);
        COMMETHOD([], HRESULT, 'GetSlideshow', (['out'], POINTER(comtypes.c_void_p), 'items')),
        # HRESULT SetSlideshowOptions([in] DESKTOP_SLIDESHOW_OPTIONS options, [in] UINT slideshowTick);
        COMMETHOD([], HRESULT, 'SetSlideshowOptions', (['in'], c_uint, 'options'),
                                                   (['in'], c_uint, 'slideshowTick')),
        # HRESULT GetSlideshowOptions([out] DESKTOP_SLIDESHOW_OPTIONS *options, [out] UINT *slideshowTick);
        COMMETHOD([], HRESULT, 'GetSlideshowOptions', (['out'], POINTER(c_uint), 'options'),
                                                   (['out'], POINTER(c_uint), 'slideshowTick')),
        # HRESULT AdvanceSlideshow([in] LPCWSTR monitorID, [in] DESKTOP_SLIDESHOW_DIRECTION direction);
        COMMETHOD([], HRESULT, 'AdvanceSlideshow', (['in'], wintypes.LPCWSTR, 'monitorID'),
                                                  (['in'], c_uint, 'direction')),
        # HRESULT GetStatus([out] DESKTOP_SLIDESHOW_STATE *state);
        COMMETHOD([], HRESULT, 'GetStatus', (['out'], POINTER(c_uint), 'state')),
        # HRESULT Enable([in] BOOL enable);
        COMMETHOD([], HRESULT, 'Enable', (['in'], wintypes.BOOL, 'enable')),
    ]

CLSID_DesktopWallpaper = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")

DWPOS_CENTER = 0
DWPOS_TILE   = 1
DWPOS_STRETCH= 2
DWPOS_FIT    = 3
DWPOS_FILL   = 4
DWPOS_SPAN   = 5  # best for multi-monitor panoramas, but we’re per-monitor here

def get_desktop_wallpaper() -> IDesktopWallpaper:
    obj = comtypes.client.CreateObject(CLSID_DesktopWallpaper, interface=IDesktopWallpaper)
    return obj

# --- image picking helpers ---

def time_band_now() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    # late night
    return "evening"

def pick_images_for_monitors(static_root: Path, count: int) -> List[Path]:
    """Pick 'count' images matching time-of-day; if folder sparse, fall back to any."""
    band = time_band_now()
    band_dir = static_root / band
    candidates = []
    if band_dir.is_dir():
        candidates = [p for p in band_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    # Optional: at night, sometimes pull from 'space'
    if not candidates or random.random() < 0.25:
        space_dir = static_root / "space"
        if space_dir.is_dir():
            candidates += [p for p in space_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    # Final fallback: any
    if not candidates:
        candidates = [p for p in static_root.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    random.shuffle(candidates)
    return candidates[:count]

def main():
    static_root = Path(STATIC_DIR)
    if not static_root.is_dir():
        print(f"❌ STATIC_DIR not found: {static_root}")
        return

    dw = get_desktop_wallpaper()

    # Enumerate monitors
    count = c_uint()
    hr = dw.GetMonitorDevicePathCount(count)
    if hr:
        print(f"❌ GetMonitorDevicePathCount failed (HRESULT={hr})")
        return
    n = count.value
    monitor_ids: List[str] = []
    for i in range(n):
        bstr = BSTR()
        dw.GetMonitorDevicePathAt(i, bstr)
        monitor_ids.append(str(bstr))

    print("[INFO] Monitors (0-based):")
    for i, mid in enumerate(monitor_ids):
        print(f"  {i}: {mid}")

    # Decide which monitors to set (skip the live WE monitor)
    if LIVE_MONITOR_INDEX < 0 or LIVE_MONITOR_INDEX >= n:
        live_idx = max(0, n - 1)  # default to last monitor if not configured
        print(f"[WARN] live_monitor_index missing/out of range; defaulting to {live_idx}")
    else:
        live_idx = LIVE_MONITOR_INDEX

    targets = [i for i in range(n) if i != live_idx]
    if not targets:
        print("[INFO] Only one monitor detected or only live monitor available; nothing to set.")
        return

    # Pick images
    imgs = pick_images_for_monitors(static_root, len(targets))
    if len(imgs) < len(targets):
        print(f"[WARN] Not enough images found for {len(targets)} monitors; will reuse.")
        while len(imgs) < len(targets):
            imgs += imgs
        imgs = imgs[:len(targets)]

    # Set position style (Fill usually looks best)
    dw.SetPosition(DWPOS_FILL)

    # Apply per monitor
    for idx, img in zip(targets, imgs):
        path = str(img.resolve())
        monitor_id = monitor_ids[idx]
        print(f"[APPLY] Monitor {idx} ← {path}")
        hr = dw.SetWallpaper(monitor_id, path)
        if hr:
            print(f"  ⚠️  SetWallpaper failed on monitor {idx} (HRESULT={hr})")

    print("✅ Static wallpapers applied to non-live monitors.")

if __name__ == "__main__":
    # Lazy import to avoid comtypes import time unless script runs
    from ctypes import c_uint
    import comtypes.client
    main()
