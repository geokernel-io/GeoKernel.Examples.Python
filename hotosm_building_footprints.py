"""HOTOSM DINOv3-S building footprints."""
from geoai_support import HOTOSM
from geoai_window import QApplication, QFileDialog, GeoAiWindow, run_example


class Window(GeoAiWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app, HOTOSM)


if __name__ == "__main__":
    run_example(HOTOSM)
