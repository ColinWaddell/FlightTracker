"""
ImageScene - displays images pushed over the Image Upload API.

Priority 10: the highest normal scene, so a pushed image preempts
flight/satellite display immediately and holds the screen until its TTL
expires (SceneManager falls back automatically once has_data() goes
False).

Frames arrive as raw RGB bytes (see utilities/image_inbox.py).  A single
frame is shown statically; multiple frames cycle at the submission's
frame_delay.  Once the optional loops count completes the scene yields
(falls back to the next scene) even if the TTL has not expired.

A replacement submission - one pushed while an image is already on
screen - is detected in poll() by comparing submission identity; the
frame buffers are rebuilt and the animation counters reset with no
canvas operations, because draw_image repaints every pixel anyway.
"""

import time

from setup import screen

PRIORITY = 10


class ImageScene:
    """Full-panel image display driven by the in-memory image inbox."""

    priority = PRIORITY

    def __init__(self, canvas, panel, inbox=None):
        from utilities.image_inbox import INBOX

        self.canvas = canvas
        self.panel = panel
        self.inbox = inbox if inbox is not None else INBOX

        self._shown = None  # Submission on screen (identity key)
        self._images = []  # PIL images for that submission
        self._frame_index = 0
        self._loops_done = 0
        self._last_flip = 0.0
        self._exhausted = False

    # -- scene contract -----------------------------------------------------

    def has_data(self):
        return self._valid()

    def active(self):
        return self._valid()

    def poll(self):
        """Detect a replacement submission; swap buffers without canvas ops."""
        submission = self.inbox.current()
        if submission is not None and submission is not self._shown:
            self._prepare(submission)

    def on_enter(self):
        self.panel.clear(self.canvas)
        submission = self.inbox.current()
        if submission is not None:
            self._prepare(submission)

    def reset(self):
        # Never called by SceneManager - part of the scene contract.
        # Behaves like poll(): adopt any replacement submission.
        self.poll()

    def draw(self):
        if (
            self._shown is None
            or self._exhausted
            or self.inbox.current() is None
        ):
            return
        submission = self._shown
        if len(submission.frames) > 1:
            now = time.time()
            if now - self._last_flip >= submission.frame_delay_ms / 1000.0:
                self._last_flip = now
                self._frame_index += 1
                if self._frame_index >= len(submission.frames):
                    self._frame_index = 0
                    if submission.loops is not None:
                        self._loops_done += 1
                        if self._loops_done >= submission.loops:
                            self._exhausted = True
                            return
        self.panel.draw_image(
            self.canvas, 0, 0, self._images[self._frame_index]
        )

    # -- internals ------------------------------------------------------------

    def _valid(self):
        """A submission is on screen, not exhausted, and inside its TTL."""
        return self.inbox.current() is not None and not self._exhausted

    def _prepare(self, submission):
        from PIL import Image

        self._shown = submission
        self._images = [
            Image.frombytes("RGB", (screen.WIDTH, screen.HEIGHT), frame)
            for frame in submission.frames
        ]
        self._frame_index = 0
        self._loops_done = 0
        self._last_flip = time.time()
        self._exhausted = False