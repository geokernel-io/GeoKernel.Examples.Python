"""Agent Map Assistant: natural-language map requests as validated, previewed and recorded workflows.

Python port of the Qt AgentMapAssistant example. A planner (an LLM, or the offline demo
with prepared plans) proposes a workflow DSL v2 plan; GeoKernel validates it, the plan is
shown before anything runs, steps that change data need the user's confirmation of that
exact plan, and every executed workflow is undoable and recorded with hash-chained
provenance. Needs a geokernel package with the agent API (newer than 1.5.40).
"""

from __future__ import annotations

import html
import json
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from common import application_icon
from geokernel import Viewer, ViewerTool

try:
    from geokernel.agent import GisAgent, GisAgentError, propose
except ImportError:  # geokernel 1.5.40 and earlier
    GisAgent = None

DATA_DIR = Path(__file__).resolve().parent / "agent_map_assistant-data"
TITLE = "Agent Map Assistant"

# Bottom to top; each new layer becomes index 0.
LAYERS = [
    ("parks.geojson", {"fillColor": "#A1D99B", "fillOpacity": 255, "lineColor": "#41AB5D", "lineWidth": 1.0}),
    ("streets.geojson", {"lineColor": "#9E9E9E", "lineWidth": 3.0}),
    ("buildings.geojson", {"fillColor": "#E7D8C3", "fillOpacity": 255, "lineColor": "#A08B70", "lineWidth": 0.8}),
    ("schools.geojson", {"pointColor": "#2171B5", "fillColor": "#2171B5", "lineColor": "#08306B", "pointSize": 12.0, "lineWidth": 1.2}),
]


def load_demo() -> dict:
    return json.loads((DATA_DIR / "agent-demo.json").read_text(encoding="utf-8"))


def planner_description() -> str | None:
    """Planner label when an LLM is configured, else None (offline demo)."""
    provider = os.environ.get("GEOKERNEL_LLM_PROVIDER", "").strip().lower()
    if not provider:
        return None
    model = os.environ.get("GEOKERNEL_LLM_MODEL", "").strip() or ("claude-opus-5-5" if provider == "anthropic" else "model not set")
    return f"Planner: {provider} ({model})"


class ProposalSignals(QObject):
    finished = Signal(str, str, str)  # request, proposal, error


class AgentMapAssistant(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.demo = load_demo()
        self.prepared = {item["request"].casefold(): json.dumps(item["proposal"]) for item in self.demo["requests"]}
        self.llm = planner_description()
        self.viewer = Viewer()
        self.viewer.set_tool(ViewerTool.PAN)
        self.viewer_widget = self.viewer.qt_widget()
        self.agent: GisAgent | None = None
        self.pending: tuple[str, dict] | None = None  # proposal text, evaluation
        self.workflow_steps: list[int] = []
        self.busy = False
        self.signals = ProposalSignals()
        self.signals.finished.connect(self.on_proposal)
        self.initialized = False

        self.setWindowTitle(TITLE)
        self.setWindowIcon(application_icon())
        self.resize(1360, 820)
        self.create_ui()

    # ------------------------------------------------------------------ UI

    def create_ui(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget(root)
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(6, 4, 6, 4)
        bar.addWidget(QLabel("Try:", toolbar))
        self.requests = QComboBox(toolbar)
        self.requests.setMinimumWidth(520)
        self.requests.addItems([item["request"] for item in self.demo["requests"]])
        bar.addWidget(self.requests)
        self.ask_button = QPushButton("Ask", toolbar)
        self.ask_button.clicked.connect(lambda: self.submit(self.requests.currentText()))
        bar.addWidget(self.ask_button)
        full = QPushButton("Full Extent", toolbar)
        full.clicked.connect(self.viewer.full_extent)
        bar.addWidget(full)
        provenance = QPushButton("Provenance...", toolbar)
        provenance.clicked.connect(self.show_provenance)
        bar.addWidget(provenance)
        bar.addStretch(1)

        panel = QWidget(root)
        side = QVBoxLayout(panel)
        side.setContentsMargins(8, 8, 8, 8)
        self.log = QTextBrowser(panel)
        self.log.setPlaceholderText('Ask for a map operation, for example: "Show the buildings within 150 m of a school in red".')
        side.addWidget(self.log, 3)
        plan_box = QGroupBox("Plan", panel)
        plan_layout = QVBoxLayout(plan_box)
        self.plan = QPlainTextEdit(plan_box)
        self.plan.setReadOnly(True)
        self.plan.setPlaceholderText("The proposed steps appear here before anything runs.")
        plan_layout.addWidget(self.plan)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.discard_button = QPushButton("Discard", plan_box)
        self.discard_button.clicked.connect(self.discard)
        self.run_button = QPushButton("Run", plan_box)
        self.run_button.clicked.connect(self.run_pending)
        buttons.addWidget(self.discard_button)
        buttons.addWidget(self.run_button)
        plan_layout.addLayout(buttons)
        side.addWidget(plan_box, 2)
        entry = QHBoxLayout()
        self.input = QLineEdit(panel)
        self.input.setPlaceholderText("Describe what to do on the map")
        self.input.returnPressed.connect(self.send_typed)
        self.send_button = QPushButton("Send", panel)
        self.send_button.clicked.connect(self.send_typed)
        entry.addWidget(self.input, 1)
        entry.addWidget(self.send_button)
        side.addLayout(entry)
        undo_row = QHBoxLayout()
        self.undo_button = QPushButton("Undo last", panel)
        self.undo_button.clicked.connect(self.undo_last)
        undo_row.addWidget(self.undo_button)
        undo_row.addStretch(1)
        side.addLayout(undo_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, root)
        splitter.addWidget(self.viewer_widget)
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([940, 420])

        layout.addWidget(toolbar)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)
        self.planner_label = QLabel(self.llm or "Planner: offline demo (prepared plans)", self)
        self.statusBar().addPermanentWidget(self.planner_label)
        self.refresh_buttons()

    def initialize_viewer(self) -> None:
        if self.initialized:
            return
        self.initialized = True
        self.viewer.resize(self.viewer_widget.width(), self.viewer_widget.height())
        self.viewer.show()
        try:
            for name, style in LAYERS:
                self.viewer.add_layer(DATA_DIR / name)
                self.viewer.set_layer_style(0, style)
            self.viewer.refresh_layers()
            self.viewer.full_extent()
            self.agent = GisAgent(self.viewer)
        except Exception as error:
            QMessageBox.critical(self, TITLE, f"The map could not be prepared:\n{error}")
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        ready = self.agent is not None and not self.busy
        self.ask_button.setEnabled(ready)
        self.send_button.setEnabled(ready)
        self.run_button.setEnabled(ready and self.pending is not None)
        self.discard_button.setEnabled(ready and self.pending is not None)
        self.undo_button.setEnabled(ready and bool(self.workflow_steps))

    def append(self, who: str, text: str, color: str | None = None) -> None:
        body = html.escape(text).replace("\n", "<br>")
        if color:
            body = f'<span style="color:{color}">{body}</span>'
        self.log.append(f"<b>{html.escape(who)}:</b> {body}")

    # ------------------------------------------------------------------ planning

    def send_typed(self) -> None:
        if self.submit(self.input.text()):
            self.input.clear()

    def submit(self, request: str) -> bool:
        request = request.strip()
        if not request or self.busy or self.agent is None:
            return False
        self.discard(log=False)
        self.append("You", request)
        if self.llm is None:
            proposal = self.prepared.get(request.casefold())
            if proposal is None:
                self.on_proposal(request, "", "offline demo mode only has plans for the sample requests. Set "
                                 "GEOKERNEL_LLM_PROVIDER (anthropic, openai or ollama) and its API key to plan your own requests.")
            else:
                self.on_proposal(request, proposal, "")
            return True
        # The model call can take a while; keep the window responsive.
        grounding = self.agent.grounding() + "\n" + self.demo["groundingNotes"]
        self.busy = True
        self.statusBar().showMessage("Planning...")
        self.refresh_buttons()

        def work() -> None:
            try:
                self.signals.finished.emit(request, propose(request, grounding, viewer=self.viewer), "")
            except Exception as error:  # GisAgentError, configuration errors
                self.signals.finished.emit(request, "", str(error))

        threading.Thread(target=work, daemon=True).start()
        return True

    def on_proposal(self, request: str, proposal: str, error: str) -> None:
        self.busy = False
        self.statusBar().clearMessage()
        if error:
            self.append("Planner", f"No plan was proposed: {error}", "#b00020")
            self.refresh_buttons()
            return
        evaluation = self.agent.evaluate(proposal)
        status = evaluation["status"]
        if status not in ("validated", "confirmation-required"):
            details = "; ".join(f"{step['stepId']}: {step['message']}" for step in evaluation.get("steps", []) if step.get("message"))
            self.append("Planner", f"The plan was rejected ({status}): {evaluation['message']}" + (f" — {details}" if details else ""), "#b00020")
            self.refresh_buttons()
            return
        self.pending = (proposal, evaluation)
        plan_id = evaluation["planId"]
        self.plan.setPlainText(evaluation["summary"].replace(plan_id, plan_id[:16] + "…", 1))
        steps = len(evaluation.get("steps", [])) or evaluation["summary"].count("\n")
        if evaluation["needsConfirmation"]:
            self.run_button.setText("Confirm and run")
            self.append("Planner", f"Plan ready. Steps {', '.join(evaluation['needsConfirmation'])} change or delete data; "
                        "review them before running.", "#8a4b00")
            self.statusBar().showMessage("The plan changes data: review it and click Confirm and run")
        else:
            self.run_button.setText("Run")
            self.append("Planner", f"Plan ready ({steps} step{'s' if steps != 1 else ''}). Review it and press Run.")
            self.statusBar().showMessage("Plan validated: review it and click Run")
        self.refresh_buttons()

    # ------------------------------------------------------------------ execution

    def run_pending(self) -> None:
        if self.pending is None or self.busy:
            return
        proposal, evaluation = self.pending
        # Clicking Run is the user's confirmation of this exact plan.
        confirmed = evaluation["planId"] if evaluation["needsConfirmation"] else None
        result = self.agent.run(proposal, confirmed)
        self.discard(log=False)
        if result.get("completedSteps", 0) > 0:
            self.workflow_steps.append(result["completedSteps"])
        if result.get("report"):
            self.append("Result", result["report"])
        completed = result.get("completedSteps", 0)
        if result["status"] == "executed":
            self.append("Map", f"Done: {completed} step{'s' if completed != 1 else ''} ran. "
                        f"Provenance {result['provenanceHash'][:12]}.", "#1b5e20")
            self.statusBar().showMessage(f"Executed {result['planId'][:16]}", 8000)
        else:
            self.append("Map", f"Stopped at step {result.get('failedStepId') or '-'}: {result['message']}. "
                        f"{completed} completed steps can be undone.", "#b00020")
        self.refresh_buttons()

    def discard(self, log: bool = True) -> None:
        had_plan = self.pending is not None
        self.pending = None
        self.plan.clear()
        self.run_button.setText("Run")
        if log and had_plan:
            self.append("Planner", "Plan discarded; nothing ran.")
            self.statusBar().clearMessage()
        self.refresh_buttons()

    def undo_last(self) -> None:
        if not self.workflow_steps or self.busy:
            return
        result = self.agent.undo(self.workflow_steps.pop())
        text = f"Undone: {', '.join(result['undoneSteps'])}."
        if result.get("irreversible"):
            text += f" Could not undo: {'; '.join(result['irreversible'])}."
        self.append("Map", text)
        self.refresh_buttons()

    def show_provenance(self) -> None:
        if self.agent is None:
            return
        records = self.agent.provenance()
        dialog = QDialog(self)
        dialog.setWindowTitle("Provenance")
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        count = len(records.get("records", []))
        layout.addWidget(QLabel("No workflow has run yet." if count == 0 else
                                f"{count} executed workflow(s). Each record holds the normalized plan, its validation "
                                "decision and the SHA-256 of every step output, chained by hash.", dialog))
        text = QPlainTextEdit(json.dumps(records, indent=2), dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(text)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dialog)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    # ------------------------------------------------------------------ lifetime

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.initialize_viewer)

    def closeEvent(self, event) -> None:
        if self.agent is not None:
            self.agent.close()
            self.agent = None
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    if GisAgent is None:
        QMessageBox.critical(None, TITLE, "This geokernel package has no agent API. AgentMapAssistant needs a "
                             "geokernel release newer than 1.5.40.")
        return 1
    window = AgentMapAssistant()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
