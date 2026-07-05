import urllib.request
import zipfile
from importlib.resources import files
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QProgressDialog

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
ICON_DIR = files("geokernel").joinpath("assets/images")

def tool_action(icon_name: str, text: str, window: QMainWindow) -> QAction:
    action = QAction(QIcon(str(ICON_DIR / icon_name)), text, window)
    action.setToolTip(text)
    action.setStatusTip(text)
    return action

def download_file(url: str, target: Path, app: QApplication, title: str = "GeoKernel Sample Data") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial_target = target.with_suffix(target.suffix + ".part")

    request = urllib.request.Request(url, headers={"User-Agent": "GeoKernel Python Examples"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length", "0"))
        progress = QProgressDialog(f"Preparing sample data...\nDownloading {target.name}", "Cancel", 0, total or 0)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.resize(520, 150)
        if total == 0:
            progress.setRange(0, 0)

        downloaded = 0
        try:
            with partial_target.open("wb") as file:
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break

                    file.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        progress.setValue(downloaded)
                        total_mb = total / 1024 / 1024
                        percent = downloaded / total * 100
                        progress.setLabelText(
                            f"Downloading sample data...\n"
                            f"{downloaded / 1024 / 1024:.1f} MB / {total_mb:.1f} MB ({percent:.0f}%)"
                        )
                    else:
                        progress.setLabelText(
                            f"Downloading sample data...\n"
                            f"{downloaded / 1024 / 1024:.1f} MB downloaded"
                        )
                    app.processEvents()

                    if progress.wasCanceled():
                        raise RuntimeError("Sample data download was cancelled.")
        except Exception:
            partial_target.unlink(missing_ok=True)
            raise

        progress.setValue(total if total else 0)
        partial_target.replace(target)

def extract_zip(source: Path, target_dir: Path, app: QApplication, title: str = "GeoKernel Sample Data") -> None:
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        progress = QProgressDialog(f"Installing sample data...\nExtracting {source.name}", "Cancel", 0, len(members))
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.resize(520, 150)

        target_root = target_dir.resolve()
        for index, member in enumerate(members, start=1):
            target_path = (target_dir / member.filename).resolve()
            if target_root not in target_path.parents and target_path != target_root:
                raise RuntimeError(f"Unsafe zip entry: {member.filename}")

            archive.extract(member, target_dir)
            progress.setValue(index)
            progress.setLabelText(
                f"Installing sample data...\n"
                f"Extracting {index} / {len(members)}: {member.filename}"
            )
            app.processEvents()

            if progress.wasCanceled():
                raise RuntimeError("Sample data extraction was cancelled.")

def ensure_sample_file(app: QApplication, zip_url: str, zip_name: str, target_folder: str, required_file: str, title: str = "GeoKernel Sample Data",) -> Path:

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    target_dir = DATA_DIR / target_folder
    expected_path = target_dir / required_file
    if expected_path.exists():
        return expected_path

    zip_path = DATA_DIR / zip_name

    try:
        if not zip_path.exists():
            download_file(zip_url, zip_path, app, title)

        extract_zip(zip_path, target_dir, app, title)
        zip_path.unlink(missing_ok=True)
    except Exception as error:
        QMessageBox.critical(
            None,
            title,
            f"Sample data could not be prepared.\n\n{error}",
        )
        raise

    if expected_path.exists():
        return expected_path

    matches = list(target_dir.rglob(Path(required_file).name))
    if matches:
        return matches[0]

    QMessageBox.critical(
        None,
        title,
        f"Downloaded sample data does not contain:\n{expected_path}",
    )
    raise FileNotFoundError(expected_path)
