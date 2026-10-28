"""Google Dynamic World land cover."""
from geoai_support import DYNAMIC_WORLD
from geoai_window import QApplication, QFileDialog, GeoAiWindow, run_example


class Window(GeoAiWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__(app, DYNAMIC_WORLD)


if __name__ == "__main__":
    run_example(DYNAMIC_WORLD)
