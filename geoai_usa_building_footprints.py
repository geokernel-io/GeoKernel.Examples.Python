"""GeoAI USA Mask R-CNN building footprints on the fixed RGB sample."""
from geoai_support import GEOAI_USA
from geoai_window import QApplication, QFileDialog, GeoAiWindow, run_example


class Window(GeoAiWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app, GEOAI_USA)


if __name__ == "__main__":
    run_example(GEOAI_USA)
