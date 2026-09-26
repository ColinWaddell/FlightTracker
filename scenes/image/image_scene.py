"""
ImageScene - displays images pushed over the Image Upload API.

Priority 10: the highest normal scene, so a pushed image preempts
flight/satellite display immediately and holds the screen until its
animation completes (SceneManager falls back automatically once
has_data() goes False).

Frames arrive as raw RGB bytes (see utilities/image_inbox.py).  Every
submission is an animation: each frame is held for frame_ms
(quantised to whole render cycles) and the sequence repeats `loops`
times before the scene yields back to the normal display.  A single
frame is a one-frame animation, so its frame_ms sets how long it
stays on screen.

A replacement submission - one pushed while an image is already on
screen - is detected in poll() by comparing submission identity; the
frame buffers are rebuilt and the animation counters reset with no
canvas operations, because draw_image repaints every pixel anyway.

Animation timing is quantised to the panel's render loop: the display
runs at a fixed frame period, so a multi-frame submission holds each
image for a whole number of draw() cycles (frame_ms ms rounded to
the nearest cycle, minimum one).  Timing never drifts because the
scene counts actual render cycles instead of wall-clock milliseconds.
"""

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
        self._held = 0  # Render cycles the current frame has been shown
        self._hold = 1  # Cycles to hold each frame (from frame_ms ms)
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
        if self._shown is None or self._exhausted or self.inbox.current() is None:
            return
        self.panel.draw_image(self.canvas, 0, 0, self._images[self._frame_index])
        self._held += 1
        if self._held >= self._hold:
            self._held = 0
            self._frame_index += 1
            if self._frame_index >= len(self._shown.frames):
                self._frame_index = 0
                self._loops_done += 1
                if self._loops_done >= self._shown.loops:
                    self._exhausted = True

    # -- internals ------------------------------------------------------------

    def _valid(self):
        """A submission is on screen and its animation has not finished."""
        submission = self.inbox.current()
        if submission is None:
            return False
        if submission is not self._shown:
            return True  # a replacement is waiting to be adopted
        return not self._exhausted

    def _prepare(self, submission):
        from PIL import Image

        from utilities.image_inbox import quantise_frame_ms

        self._shown = submission
        self._images = [
            Image.frombytes("RGB", (screen.WIDTH, screen.HEIGHT), frame)
            for frame in submission.frames
        ]
        self._hold, _ = quantise_frame_ms(submission.frame_ms)
        self._frame_index = 0
        self._loops_done = 0
        self._held = 0
        self._exhausted = False
