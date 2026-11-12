"""Spoken callouts via Windows SAPI. Silently disabled anywhere else."""
from __future__ import annotations

import os
import queue
import threading

SVSF_ASYNC = 1
SVSF_PURGE = 2


class Speaker:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and os.name == "nt"
        self.available = False
        self._q: queue.Queue = queue.Queue()
        if self.enabled:
            threading.Thread(target=self._run, daemon=True).start()

    def say(self, text: str):
        if self.enabled and text:
            self._q.put(text)

    def _run(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            voice.Rate = 2
        except Exception:
            return
        self.available = True
        while True:
            text = self._q.get()
            try:
                # New callout cuts off the old one, like a real wingman.
                voice.Speak(text, SVSF_ASYNC | SVSF_PURGE)
            except Exception:
                pass
