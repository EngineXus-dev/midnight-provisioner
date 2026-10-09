"""Nightglass visual identity: quiet, low-glare casual cyberhacker dark theme.

Application-level Qt Fusion palette handles native dialogs and controls while
the stylesheet handles Nightglass-specific widgets. No effects, timers or
third-party fonts. Security state is always communicated in text as well as
color; this module does not alter any virtualization or filesystem behavior.
"""
from __future__ import annotations

THEME_NAME = "Casual Cyberhacker Dark"
COLORS = {
    "window": "#090d10",
    "surface": "#0d1317",
    "sidebar": "#0b1014",
    "card": "#12191d",
    "raised": "#172126",
    "input": "#0c1317",
    "terminal": "#080e11",
    "line": "#26363b",
    "line_hover": "#35554f",
    "accent": "#72b9a2",
    "accent_hover": "#88ccb4",
    "accent_surface": "#19332c",
    "text": "#d3dcd9",
    "text_strong": "#e5ebe8",
    "text_muted": "#95a8a5",
    "disabled": "#72807e",
    "success": "#8bbda4",
    "warning": "#c9ad79",
    "danger": "#c99597",
}

# Object names intentionally match the existing PySide6 widgets.
DARK_QSS = """
QWidget {
    background-color: #090d10;
    color: #d3dcd9;
    font-family: "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 12px;
    selection-background-color: #25483d;
    selection-color: #ecf3ef;
}
QMainWindow, QDialog, QMessageBox, QInputDialog, QFileDialog {
    background-color: #090d10;
    color: #d3dcd9;
}
QFrame { border: none; }
QFrame#Sidebar {
    background-color: #0b1014;
    border-right: 1px solid #202d31;
}
QFrame#Sidebar QLabel {
    background-color: transparent;
}
QFrame#Sidebar QPushButton {
    background: transparent;
    color: #99aaa7;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 12px;
    text-align: left;
    font-weight: 500;
}
QFrame#Sidebar QPushButton:hover {
    background-color: #131e20;
    color: #d4e7dd;
    border-color: #283e38;
}
QFrame#Sidebar QPushButton:checked {
    background-color: #19332c;
    color: #cde8d9;
    border: 1px solid #345b4e;
    font-weight: 600;
}
QFrame#WorkspaceCard, QFrame#Panel {
    background-color: #12191d;
    border: 1px solid #26363b;
    border-radius: 13px;
}
QFrame#WorkspaceCard:hover { border-color: #35554f; }
QLabel {
    background: transparent;
    color: #d3dcd9;
}
QLabel#Title {
    font-size: 23px;
    font-weight: 700;
    color: #e5ebe8;
}
QLabel#Brand {
    color: #a4d5bf;
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#SubTitle { color: #95a8a5; font-size: 12px; }
QLabel#CardTitle { color: #dee7e2; font-size: 16px; font-weight: 650; }
QLabel#Badge {
    background-color: #19312a;
    border: 1px solid #31554a;
    color: #b1d4bf;
    border-radius: 7px;
    padding: 4px 8px;
}
QLabel#SectionHeading {
    color: #a4d5bf;
    font-size: 12px;
    font-weight: 650;
    letter-spacing: 0.7px;
}
QLabel#AppFooter { color: #718a85; font-size: 10px; }
QPushButton {
    background-color: #182329;
    color: #d1ddd6;
    border: 1px solid #2d4142;
    border-radius: 8px;
    padding: 8px 11px;
    min-height: 19px;
}
QPushButton:hover {
    background-color: #21312e;
    border-color: #476b5e;
    color: #e5eee8;
}
QPushButton:pressed {
    background-color: #142823;
    border-color: #4d7866;
}
QPushButton:disabled {
    color: #788985;
    background-color: #10191c;
    border-color: #1f2c2d;
}
QPushButton:focus {
    border: 1px solid #72b9a2;
}
QPushButton#Primary {
    background-color: #1c4035;
    color: #dceee3;
    border: 1px solid #467b64;
    font-weight: 600;
}
QPushButton#Primary:hover {
    background-color: #295242;
    border-color: #77ae8d;
}
QPushButton#Primary:disabled {
    background-color: #13251f;
    color: #74857d;
    border-color: #263930;
}
QPushButton#Danger {
    background-color: #322024;
    color: #e1bdc0;
    border-color: #70474c;
}
QPushButton#Danger:hover {
    background-color: #44282c;
    border-color: #99636c;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0c1317;
    color: #d5dfd9;
    border: 1px solid #293c3c;
    border-radius: 8px;
    padding: 7px 9px;
    selection-background-color: #25483d;
    selection-color: #edf7f0;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #406155;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #689c88;
}
QLineEdit:disabled, QComboBox:disabled {
    color: #798b85;
    background-color: #10181a;
    border-color: #243130;
}
QPlainTextEdit, QTextEdit {
    background-color: #080e11;
    color: #b7d1bf;
    border: 1px solid #273e39;
    font-family: "JetBrains Mono", "Cascadia Mono", "DejaVu Sans Mono", monospace;
    font-size: 12px;
    border-radius: 9px;
    padding: 9px;
}
QPlainTextEdit:read-only, QTextEdit:read-only {
    background-color: #080e11;
}
QComboBox::drop-down {
    border: none;
    background: transparent;
    width: 23px;
}
QComboBox QAbstractItemView, QListView, QListWidget, QTreeView, QTreeWidget {
    background-color: #10191c;
    color: #d7e2da;
    border: 1px solid #304640;
    selection-background-color: #25483d;
    selection-color: #e8f3ec;
    outline: none;
}
QMenu {
    background-color: #111b1e;
    color: #d5e2db;
    border: 1px solid #334a43;
    padding: 4px;
}
QMenu::item { padding: 6px 18px; }
QMenu::item:selected {
    background-color: #25483d;
    color: #edf3ec;
}
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget,
QWidget#qt_scrollarea_viewport {
    border: none;
    background-color: #090d10;
}
QScrollBar:vertical {
    background-color: #0b1114;
    width: 10px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #304a43;
    border-radius: 5px;
    min-height: 22px;
}
QScrollBar::handle:vertical:hover { background-color: #45665a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
    border: none;
}
QScrollBar:horizontal {
    background-color: #0b1114;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #304a43;
    border-radius: 5px;
    min-width: 22px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}
QCheckBox, QRadioButton {
    background: transparent;
    color: #bfcfc6;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
}
QCheckBox::indicator:unchecked {
    background-color: #0f1819;
    border: 1px solid #41534d;
}
QCheckBox::indicator:checked {
    background-color: #3c8265;
    border: 1px solid #77b597;
}
QCheckBox::indicator:disabled { background-color: #192420; border-color: #2a3933; }
QToolTip {
    background-color: #172326;
    color: #e1eee3;
    border: 1px solid #34554b;
    padding: 6px;
}
QStatusBar { background-color: #0b1014; color: #a2b4ab; }
QProgressBar {
    background-color: #0f181b;
    color: #d4e2d6;
    border: 1px solid #31443e;
    border-radius: 6px;
}
QProgressBar::chunk { background-color: #4e9473; border-radius: 5px; }
"""


def apply_theme(app) -> None:
    """Set the complete Qt palette, not just page CSS, to prevent bright dialogs.

    A Fusion style is deterministic across KDE/Wayland, X11 and CI's offscreen
    platform. The current theme is intentionally static; it is not a skinning
    system that stores user data or depends on network resources.
    """
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    palette = QPalette()
    c = QColor
    role = QPalette.ColorRole
    palette.setColor(role.Window, c(COLORS["window"]))
    palette.setColor(role.WindowText, c(COLORS["text"]))
    palette.setColor(role.Base, c(COLORS["input"]))
    palette.setColor(role.AlternateBase, c(COLORS["surface"]))
    palette.setColor(role.ToolTipBase, c(COLORS["raised"]))
    palette.setColor(role.ToolTipText, c(COLORS["text_strong"]))
    palette.setColor(role.Text, c(COLORS["text"]))
    palette.setColor(role.Button, c(COLORS["raised"]))
    palette.setColor(role.ButtonText, c(COLORS["text"]))
    palette.setColor(role.BrightText, c(COLORS["text_strong"]))
    palette.setColor(role.Highlight, c(COLORS["accent_surface"]))
    palette.setColor(role.HighlightedText, c(COLORS["text_strong"]))
    palette.setColor(role.Link, c(COLORS["accent"]))
    palette.setColor(role.PlaceholderText, c(COLORS["text_muted"]))
    palette.setColor(QPalette.ColorGroup.Disabled, role.WindowText, c(COLORS["disabled"]))
    palette.setColor(QPalette.ColorGroup.Disabled, role.Text, c(COLORS["disabled"]))
    palette.setColor(QPalette.ColorGroup.Disabled, role.ButtonText, c(COLORS["disabled"]))
    app.setPalette(palette)
    app.setStyleSheet(DARK_QSS)
