"""
NullLoadingIndicator - no-op indicator when loading feedback is disabled.

Shares the same constructor signature and tick() API as
LoadingPulseIndicator and LoadingLEDIndicator so the display loop can
treat all three interchangeably.
"""


class NullLoadingIndicator:
    def __init__(self, canvas, panel, overhead):
        # Accepted for API symmetry; nothing is used.
        pass

    def tick(self, frame: int) -> None:
        """No-op - no loading indicator is drawn."""
        return
