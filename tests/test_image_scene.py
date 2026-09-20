"""
Tests for ImageScene (scenes/image/image_scene.py).

Uses a fake panel (records draw_image/clear calls), a fake inbox (the
test controls what current() returns) and a module-local time rebind
(SimpleNamespace over utilities.image_scene.time) so animation timing
is deterministic - the stdlib time module is never patched globally.
"""

from types import SimpleNamespace

import pytest
from PIL import Image

from utilities import image_inbox as mod
from scenes.image import image_scene as scene_mod
from scenes.image.image_scene import ImageScene


FRAME = bytes(range(256)) * 24


def make_submission(frames=1, loops=None, frame_delay_ms=500, ttl=60, at=1000.0):
    return mod.Submission(
        frames=[FRAME] * frames,
        loops=loops,
        frame_delay_ms=frame_delay_ms,
        ttl_seconds=ttl,
        received_at=at,
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
        self.blits = []

    def clear(self, canvas):
        self.cleared += 1

    def draw_image(self, canvas, x, y, image):
        self.blits.append((x, y, image))


@pytest.fixture
def clock_box():
    return {"now": 1000.0}


@pytest.fixture
def fake_time(monkeypatch, clock_box):
    monkeypatch.setattr(
        scene_mod, "time", SimpleNamespace(time=lambda: clock_box["now"])
    )
    return clock_box


@pytest.fixture
def fake_inbox():
    return FakeInbox()


@pytest.fixture
def scene(fake_inbox, fake_panel, fake_inbox_unused):
    return ImageScene("canvas", fake_panel, inbox=fake_inbox)


@pytest.fixture
def fake_panel():
    return FakePanel()


@pytest.fixture
def fake_inbox_unused():
    return None


# ---------------------------------------------------------------------------
# Contract / priority
# ---------------------------------------------------------------------------


def test_priority_is_highest(scene):
    assert ImageScene.priority == 10
    assert ImageScene.priority > 2  # above SatelliteScene


def test_no_data_initially(scene):
    assert scene.has_data() is False
    assert scene.active() is False


def test_has_data_with_submission(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    submission = make_submission()
    fake_inbox.set(submission)
    assert scene.has_data() is True
    assert scene.active() is True


def test_on_enter_clears_canvas_and_prepares(scene, fake_panel, fake_inbox, fake_inbox_unused, fake_time):
    submission = make_submission()
    fake_inbox.set(submission)
    scene.on_enter()
    assert fake_panel.cleared == 1
    scene.draw()
    assert len(fake_panel.blits) == 1


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def test_draw_blits_full_screen_image(scene, fake_inbox, fake_panel, fake_time):
    fake_inbox.set(make_submission())
    scene.on_enter()
    scene.draw()
    x, y, image = fake_panel.blits[0]
    assert (x, y) == (0, 0)
    assert image.size == (64, 32)
    assert image.getpixel((0, 0)) == (0, 1, 2)  # RGB source preserved


def test_draw_single_frame_repeatedly(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=1))
    scene.on_enter()
    for _ in range(5):
        scene.draw()
    assert len(fake_panel.blits) == 5


def test_single_frame_never_exhausts(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=1, loops=1))
    scene.on_enter()
    fake_time["now"] += 1000
    scene.draw()
    assert scene.has_data() is True


def test_animation_advances_frames(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=3, frame_delay_ms=500))
    scene.on_enter()
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[0]
    fake_time["now"] += 0.5
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[1]
    # Below the delay: no advance, still frame 1
    fake_time["now"] += 0.2
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[1]
    fake_time["now"] += 0.3
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[2]


def test_loops_exhaustion_yields(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=2, loops=1, frame_delay_ms=100))
    scene.on_enter()
    # First pass: frames 0, 1
    scene.draw()
    fake_time["now"] += 0.1
    scene.draw()
    assert scene.has_data() is True
    # Second frame pass completes loop 1 -> exhausted
    fake_time["now"] += 0.1
    scene.draw()  # wraps to frame 0, loops_done = 1 -> exhausted, no blit
    assert scene.has_data() is False
    assert scene.active() is False
    assert len(fake_panel.blits) == 2
    scene.draw()  # exhausted: no-op
    assert len(fake_panel.blits) == 2


def test_infinite_loops_never_exhaust(scene, fake_inbox, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=1, loops=None))
    scene.on_enter()
    for _ in range(20):
        fake_time["now"] += 1
        scene.draw()
    assert scene.has_data() is True


# ---------------------------------------------------------------------------
# Replacement / expiry / reset
# ---------------------------------------------------------------------------


def test_replacement_resets_animation(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=2, frame_delay_ms=500))
    scene.on_enter()
    fake_time["now"] += 0.5
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[1]

    replacement = make_submission(frames=3, frame_delay_ms=500)
    fake_inbox.set(replacement)
    scene.poll()
    fake_time["now"] += 0.0
    scene.draw()
    assert fake_panel.blits[-1][2] is scene._images[0]
    assert scene._shown is replacement


def test_replacement_while_exhausted_revives(scene, fake_inbox, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission(frames=1, loops=1, frame_delay_ms=100))
    scene.on_enter()
    fake_time["now"] += 1
    scene.draw()  # single frame + loops=1... single frame does not exhaust
    fake_inbox.set(make_submission(frames=2, loops=1))
    scene.poll()
    assert scene.has_data() is True


def test_expiry_yields(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission())
    scene.on_enter()
    assert scene.has_data() is True
    fake_inbox.set(None)  # inbox expired the submission
    assert scene.has_data() is False
    scene.draw()  # no-op, no crash
    assert len(fake_panel.blits) == 0


def test_poll_adopts_new_submission_without_canvas_ops(scene, fake_inbox, fake_panel, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission())
    scene.on_enter()
    blits_before = len(fake_panel.blits)
    fake_inbox.set(make_submission(ttl=10))
    scene.poll()
    assert scene._shown is fake_inbox.submission
    assert len(fake_panel.blits) == blits_before


def test_reset_adopts_replacement(scene, fake_inbox, fake_inbox_unused, fake_time):
    fake_inbox.set(make_submission())
    scene.on_enter()
    fake_inbox.set(make_submission(ttl=5))
    scene.reset()
    assert scene._shown is fake_inbox.submission
    assert scene.has_data() is True