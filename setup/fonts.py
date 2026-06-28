import os
from rgbmatrix import graphics

# Fonts
DIR_PATH = os.path.dirname(os.path.realpath(__file__))

extrasmall = graphics.Font()
small = graphics.Font()
small_symbols = graphics.Font()  # custom 5x8: ^=altitude, ~=speed, *=degrees, }=heading
regular = graphics.Font()
large = graphics.Font()
large_bold = graphics.Font()

extrasmall.LoadFont(f"{DIR_PATH}/../fonts/4x6.bdf")
small.LoadFont(f"{DIR_PATH}/../fonts/5x8.bdf")
small_symbols.LoadFont(f"{DIR_PATH}/../fonts/5x8-custom.bdf")
regular.LoadFont(f"{DIR_PATH}/../fonts/6x12.bdf")
large.LoadFont(f"{DIR_PATH}/../fonts/8x13.bdf")
large_bold.LoadFont(f"{DIR_PATH}/../fonts/8x13B.bdf")
