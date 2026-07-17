"""Weather animation engines for forecast sprites.

Each engine produces a frame-by-frame pixel delta animation that plays
in the area below (or instead of) the static weather icon.  Engines are
selected by name string via the registry.
"""