# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import aqt
import aqt.main
from aqt.qt import *
from aqt.utils import disable_help_button, restoreGeom, saveGeom, setWindowIcon, tr
from aqt.webview import AnkiWebView, AnkiWebViewKind


class LlmSettingsDialog(QDialog):
    "Connection profiles and usage totals for the AI features."

    GEOMETRY_KEY = "llmSettings"
    silentlyClose = True

    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        super().__init__(mw, Qt.WindowType.Window)
        self.mw = mw
        self._setup_ui()
        self.show()

    def _setup_ui(self) -> None:
        self.mw.garbage_collect_on_dialog_finish(self)
        self.setWindowTitle(tr.llm_settings_title())
        self.setMinimumSize(400, 300)
        disable_help_button(self)
        restoreGeom(self, self.GEOMETRY_KEY, default_size=(700, 700))
        setWindowIcon(self)

        self.web: AnkiWebView | None = AnkiWebView(kind=AnkiWebViewKind.LLM_SETTINGS)
        self.web.load_sveltekit_page("llm-settings")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

    def reject(self) -> None:
        assert self.web is not None
        self.web.cleanup()
        self.web = None
        saveGeom(self, self.GEOMETRY_KEY)
        QDialog.reject(self)
