"""PRUE CC-BY field segmentation on the fixed two-period Sentinel-2 sample."""
from geoai_support import PRUE
from geoai_window import QApplication, QFileDialog, GeoAiWindow, run_example


class Window(GeoAiWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app, PRUE)


if __name__ == "__main__":
    run_example(PRUE)
