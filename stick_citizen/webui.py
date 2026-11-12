"""Stick Citizen v3: the cockpit screen in a native window (pywebview, Edge WebView2 on Windows)."""
from __future__ import annotations

import sys
from pathlib import Path

from . import __version__

WEB = Path(__file__).parent / "web"


def main():
    import webview

    from .webapi import Api

    api = Api()
    window = webview.create_window(
        f"Stick Citizen {__version__}", url=str(WEB / "index.html"), js_api=api,
        width=1500, height=920, min_size=(1100, 720), background_color="#05070b")
    api._window = window

    def on_closing():
        if not api.is_dirty():
            return True
        return window.create_confirmation_dialog(
            "Unsaved changes", "You have bindings you haven't saved for Star Citizen. Close anyway?")

    window.events.closing += on_closing
    # private_mode: no page cache or cookies kept between runs, so a new version never shows an old screen
    webview.start(debug="--debug" in sys.argv, private_mode=True)
    return 0
