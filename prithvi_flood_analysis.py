"""Prithvi EO 2.0 Sen1Floods11 water/flood mapping."""
from geoai_support import PRITHVI
from geoai_window import QApplication, QFileDialog, GeoAiWindow, run_example


class Window(GeoAiWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app, PRITHVI)


if __name__ == "__main__":
    run_example(PRITHVI)
