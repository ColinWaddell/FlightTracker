"""
Tests for ImageScene (scenes/image/image_scene.py).

Animation timing is counted in render cycles (draw calls), not
wall-clock: each animation frame is held for `hold` cycles, derived
from frame_ms ms quantised to the panel's frame period (80ms at
default display speed in the hermetic test config).  The panel driver
is faked (a pixel buffer that records set_pixel/clear), the inbox is a
stub the tests control directly.
"""

import pytest

from scenes.image.image_scene import ImageScene
from utilities import image_inbox as mod

FRAME = bytes(range(256)) * 24


def make_submission(frames=1, loops=1, frame_ms=500):
    # Distinct frames (varying first pixel) so animation tests can tell
    # the panel frames apart; frame 0 stays the reference FRAME.
    distinct = [
        FRAME if i == 0 else bytes([i, 0, 0]) + FRAME[3:] for i in range(frames)
    ]
    return mod.Submission(
        frames=distinct,
        loops=loops,
        frame_ms=frame_ms,
    )


class FakeInbox:
    def __init__(self):
        self.submission = None

    def current(self):
        return self.submission

    def set(self, submission):
        self.submission = submission


class FakePanel:
    def __init__(self):
        self.cleared = 0
        self.pixels = bytearray(64 * 32 * 3)
        self.writes = 0  # set_pixel calls

    def clear(self, canvas):
        self.cleared += 1
        self.pixels = bytearray(64 * 32 * 3)

    def set_pixel(self, canvas, x, y, r, g, b):
        i = (y * 64 + x) * 3
        self.pixels[i : i + 3] = bytes((r, g, b))
        self.writes += 1


@pytest.fixture
def fake_inbox():
    return FakeInbox()


@pytest.fixture
def fake_panel():
    return FakePanel()


@pytest.fixture
def scene(fake_inbox, fake_panel):
    return ImageScene("canvas", fake_panel, inbox=fake_inbox)


def shown_frames(scene, fake_panel, cycles):
    """Draw *cycles* times; return the submission frame index on screen after each."""
    frames = scene._shown.frames
    shown = []
    for _ in range(cycles):
        scene.draw()
        shown.append(frames.index(bytes(fake_panel.pixels)))
    return shown


# ---------------------------------------------------------------------------
# Contract / priority
# ---------------------------------------------------------------------------


def test_priority_is_highest(scene):
    assert ImageScene.priority == 10
    assert ImageScene.priority > 2  # above SatelliteScene


def test_no_data_initially(scene):
    assert scene.has_data() is False
    assert scene.active() is False


def test_has_data_with_submission(scene, fake_inbox):
    fake_inbox.set(make_submission())
    assert scene.has_data() is True
    assert scene.active() is True


def test_on_enter_clears_canvas_and_prepares(scene, fake_panel, fake_inbox):
    fake_inbox.set(make_submission())
    scene.on_enter()
    assert fake_panel.cleared == 1
    scene.draw()
    assert bytes(fake_panel.pixels) == FRAME


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def test_draw_paints_full_screen_image(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission())
    scene.on_enter()
    scene.draw()
    assert bytes(fake_panel.pixels) == FRAME
    assert fake_panel.pixels[0:3] == bytes((0, 1, 2))  # RGB source preserved


def test_draw_skips_pixels_already_on_canvas(scene, fake_inbox, fake_panel):
    # Black out the top row: the cleared canvas already holds those
    # pixels, so only the other rows are written.
    frame = bytes(64 * 3) + FRAME[64 * 3 :]
    fake_inbox.set(mod.Submission(frames=[frame], loops=1, frame_ms=500))
    scene.on_enter()
    scene.draw()
    assert fake_panel.writes == 64 * 31
    assert bytes(fake_panel.pixels) == frame


def test_held_frame_is_not_redrawn(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission(frames=1, frame_ms=480))
    scene.on_enter()
    scene.draw()
    writes = fake_panel.writes
    for _ in range(4):
        scene.draw()
    assert fake_panel.writes == writes


def test_next_frame_draws_only_changed_pixels(scene, fake_inbox, fake_panel):
    # Frames 0 and 1 differ only in the first pixel
    fake_inbox.set(make_submission(frames=2, frame_ms=80))
    scene.on_enter()
    scene.draw()
    writes = fake_panel.writes
    scene.draw()
    assert fake_panel.writes == writes + 1
    assert bytes(fake_panel.pixels) == scene._shown.frames[1]


def test_single_frame_holds_for_frame_ms(scene, fake_inbox, fake_panel):
    # A single frame is a one-frame animation: held round(480/80) = 6
    # cycles, then the scene yields.
    fake_inbox.set(make_submission(frames=1, frame_ms=480))
    scene.on_enter()
    for _ in range(5):
        scene.draw()
    assert scene.has_data() is True
    scene.draw()  # hold 6/6 -> exhausted
    assert scene.has_data() is False
    assert scene._hold == 6


def test_single_frame_honours_frame_ms(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission(frames=1, frame_ms=160))
    scene.on_enter()
    scene.draw()
    assert scene.has_data() is True
    scene.draw()
    # Held for hold=2 cycles (160ms/80ms), then the scene yields
    assert scene._hold == 2
    assert scene.has_data() is False


def test_animation_holds_frames_for_the_quantised_cycles(scene, fake_inbox, fake_panel):
    # hold = round(160ms / 80ms) = 2 cycles per animation frame
    fake_inbox.set(make_submission(frames=3, frame_ms=160))
    scene.on_enter()
    assert shown_frames(scene, fake_panel, 5) == [0, 0, 1, 1, 2]


def test_short_delay_collapses_to_one_cycle(scene, fake_inbox, fake_panel):
    # 40ms -> hold 1: a new animation frame every draw
    fake_inbox.set(make_submission(frames=3, frame_ms=40))
    scene.on_enter()
    assert shown_frames(scene, fake_panel, 3) == [0, 1, 2]


def test_loops_exhaustion_yields(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission(frames=2, loops=1, frame_ms=80))
    scene.on_enter()
    assert shown_frames(scene, fake_panel, 1) == [0]  # advance to frame 1
    assert scene.has_data() is True
    assert shown_frames(scene, fake_panel, 1) == [1]  # loop 1 complete
    assert scene.has_data() is False
    assert scene.active() is False
    writes = fake_panel.writes
    scene.draw()  # exhausted: no-op
    assert fake_panel.writes == writes


def test_long_loops_keep_cycling(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission(frames=1, loops=100000))
    scene.on_enter()
    for _ in range(20):
        scene.draw()
    assert scene.has_data() is True


# ---------------------------------------------------------------------------
# Replacement / expiry / reset
# ---------------------------------------------------------------------------


def test_replacement_resets_animation(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission(frames=2, frame_ms=160))
    scene.on_enter()
    scene.draw()  # frame 0, held 1/2
    scene.draw()  # frame 0, held 2/2 -> next draw shows frame 1
    scene.draw()
    assert bytes(fake_panel.pixels) == scene._shown.frames[1]

    fake_inbox.set(make_submission(frames=3, frame_ms=160))
    scene.poll()
    scene.draw()
    # Fresh submission: its frame 0 is on screen, drawn over the old
    # frame without a clear
    assert scene._shown is fake_inbox.submission
    assert bytes(fake_panel.pixels) == scene._shown.frames[0]
    assert fake_panel.cleared == 1


def test_replacement_while_exhausted_revives(scene, fake_inbox):
    fake_inbox.set(make_submission(frames=2, loops=1, frame_ms=80))
    scene.on_enter()
    scene.draw()
    scene.draw()  # exhausted after one play-through
    assert scene.has_data() is False

    fake_inbox.set(make_submission(frames=2, loops=1))
    scene.poll()
    assert scene.has_data() is True


def test_current_none_draws_nothing(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission())
    scene.on_enter()
    assert scene.has_data() is True
    fake_inbox.set(None)  # inbox cleared / nothing current
    assert scene.has_data() is False
    scene.draw()  # no-op, no crash
    assert fake_panel.writes == 0


def test_poll_adopts_new_submission_without_canvas_ops(scene, fake_inbox, fake_panel):
    fake_inbox.set(make_submission())
    scene.on_enter()
    fake_inbox.set(make_submission(frame_ms=160))
    scene.poll()
    assert scene._shown is fake_inbox.submission
    assert fake_panel.writes == 0
    assert fake_panel.cleared == 1


def test_reset_adopts_replacement(scene, fake_inbox):
    fake_inbox.set(make_submission())
    scene.on_enter()
    fake_inbox.set(make_submission(frame_ms=320))
    scene.reset()
    assert scene._shown is fake_inbox.submission
    assert scene.has_data() is True
