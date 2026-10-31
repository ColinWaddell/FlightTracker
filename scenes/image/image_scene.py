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
frame buffers are swapped and the animation counters reset with no
canvas operations.

Only pixels that differ from what is already on the canvas are drawn.
The canvas keeps its contents between render cycles, so a held frame
costs nothing and a scrolling frame touches only the pixels that move.
Repainting all 2048 pixels every cycle takes over a second on a Pi Zero,
which stalls the render loop and makes animations stutter.

Animation timing is quantised to the panel's render loop: the display
runs at a fixed frame period, so a multi-frame submission holds each
image for a whole number of draw() cycles (frame_ms ms rounded to
the nearest cycle, minimum one).  Timing never drifts because the
scene counts actual render cycles instead of wall-clock milliseconds.
"""

from setup import screen

PRIORITY = 10

ROW_BYTES = screen.WIDTH * 3
BLANK = bytes(ROW_BYTES * screen.HEIGHT)  # The canvas after panel.clear()


class ImageScene:
    """Full-panel image display driven by the in-memory image inbox."""

    priority = PRIORITY

    def __init__(self, canvas, panel, inbox=None):
        from utilities.image_inbox import INBOX

        self.canvas = canvas
        self.panel = panel
        self.inbox = inbox if inbox is not None else INBOX

        self._shown = None  # Submission on screen (identity key)
        self._on_canvas = BLANK  # RGB bytes currently drawn on the canvas
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
        self._on_canvas = BLANK
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
        self._draw_frame(self._shown.frames[self._frame_index])
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

    def _draw_frame(self, frame):
        """Draw the pixels of *frame* that differ from the canvas."""
        old = self._on_canvas
        if frame == old:
            return

        set_pixel = self.panel.set_pixel
        for y in range(screen.HEIGHT):
            start = y * ROW_BYTES
            row = frame[start : start + ROW_BYTES]
            old_row = old[start : start + ROW_BYTES]
            if row == old_row:
                continue

            # XOR the rows as integers and jump from one changed pixel
            # to the next, rather than comparing every pixel in Python
            diff = int.from_bytes(row, "little") ^ int.from_bytes(old_row, "little")
            x = 0
            while diff:
                skip = ((diff & -diff).bit_length() - 1) // 24
                x += skip
                i = x * 3
                set_pixel(self.canvas, x, y, row[i], row[i + 1], row[i + 2])
                diff >>= (skip + 1) * 24
                x += 1

        self._on_canvas = frame

    def _prepare(self, submission):
        from utilities.image_inbox import quantise_frame_ms

        self._shown = submission
        self._hold, _ = quantise_frame_ms(submission.frame_ms)
        self._frame_index = 0
        self._loops_done = 0
        self._held = 0
        self._exhausted = False
