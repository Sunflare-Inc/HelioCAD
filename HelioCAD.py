import sys
import os
import json
import importlib.util
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QDialog, QLabel, QComboBox, QDialogButtonBox, QCheckBox,
    QTabWidget
)
from PyQt6.QtGui import QPainter, QPen, QColor, QIcon
from PyQt6.QtCore import Qt, QPointF, QRectF, QSettings

import svgwrite

GRID_SIZE = 20
PLUGIN_FOLDER = "modules"

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.shapes = []
        self.current_tool = "line"
        self.drawing = False
        self.start_point = None
        self.end_point = None
        self.color_mode = "light"  # default

    def set_color_mode(self, mode):
        self.color_mode = mode
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.start_point = self.snap(event.position())

    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = self.snap(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drawing:
            self.end_point = self.snap(event.position())
            self.shapes.append((self.current_tool, self.start_point, self.end_point))
            self.drawing = False
            self.start_point = self.end_point = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw_grid(painter)
        pen_color = QColor(0, 0, 0) if self.color_mode == "light" else QColor(255, 255, 255)
        pen = QPen(pen_color, 2)
        painter.setPen(pen)

        for shape in self.shapes:
            self.draw_shape(painter, *shape)

        if self.drawing and self.start_point and self.end_point:
            self.draw_shape(painter, self.current_tool, self.start_point, self.end_point)

    def draw_grid(self, painter):
        if self.color_mode == "light":
            grid_color = QColor(220, 220, 220)
        else:
            grid_color = QColor(60, 60, 60)
        pen = QPen(grid_color, 1)
        painter.setPen(pen)
        for x in range(0, self.width(), GRID_SIZE):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), GRID_SIZE):
            painter.drawLine(0, y, self.width(), y)

    def draw_shape(self, painter, tool, start, end):
        if tool == "line":
            painter.drawLine(start, end)
        elif tool == "rectangle":
            x, y, w, h = self.rect_from_points(start, end)
            painter.drawRect(QRectF(x, y, w, h))
        elif tool == "circle":
            radius = (start - end).manhattanLength()
            painter.drawEllipse(start, radius, radius)

    def rect_from_points(self, p1, p2):
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        return min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)

    def snap(self, point):
        x = round(point.x() / GRID_SIZE) * GRID_SIZE
        y = round(point.y() / GRID_SIZE) * GRID_SIZE
        return QPointF(x, y)

    def export_svg(self, filename, color_mode="light"):
        stroke_color = 'black' if color_mode == "light" else 'white'
        dwg = svgwrite.Drawing(filename, profile='tiny')
        for tool, start, end in self.shapes:
            x1, y1 = start.x(), start.y()
            x2, y2 = end.x(), end.y()
            if tool == "line":
                dwg.add(dwg.line((x1, y1), (x2, y2), stroke=stroke_color))
            elif tool == "rectangle":
                dwg.add(dwg.rect(insert=(min(x1, x2), min(y1, y2)),
                                 size=(abs(x2 - x1), abs(y2 - y1)),
                                 stroke=stroke_color, fill='none'))
            elif tool == "circle":
                radius = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
                dwg.add(dwg.circle(center=(x1, y1), r=radius, stroke=stroke_color, fill='none'))
        dwg.save()

    def save_hcad(self, filename):
        data = []
        for tool, start, end in self.shapes:
            data.append({
                "tool": tool,
                "start": [start.x(), start.y()],
                "end": [end.x(), end.y()]
            })
        with open(filename, "w") as f:
            json.dump(data, f)

    def load_hcad(self, filename):
        with open(filename, "r") as f:
            data = json.load(f)
        self.shapes = []
        for item in data:
            tool = item["tool"]
            start = QPointF(*item["start"])
            end = QPointF(*item["end"])
            self.shapes.append((tool, start, end))
        self.update()

class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings=None, plugin_loader=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = settings
        self.plugin_loader = plugin_loader

        layout = QVBoxLayout()

        self.color_label = QLabel("Color Mode:")
        self.color_combo = QComboBox()
        self.color_combo.addItems(["light", "dark"])
        saved_mode = self.settings.value("color_mode", "light")
        idx = self.color_combo.findText(saved_mode)
        if idx >= 0:
            self.color_combo.setCurrentIndex(idx)

        layout.addWidget(self.color_label)
        layout.addWidget(self.color_combo)

        layout.addWidget(QLabel("Modules:"))
        self.module_checks = {}
        if self.plugin_loader:
            enabled_modules = self.settings.value("enabled_modules", [])
            if not isinstance(enabled_modules, list):
                enabled_modules = []  # safety fallback
            for name in self.plugin_loader.plugins.keys():
                checkbox = QCheckBox(name)
                checked = True
                if name in enabled_modules:
                    checked = True
                else:
                    checked = False
                checkbox.setChecked(checked)
                checkbox.stateChanged.connect(lambda state, n=name: self.toggle_module(n, state))
                layout.addWidget(checkbox)
                self.module_checks[name] = checkbox

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def toggle_module(self, name, state):
        if self.plugin_loader:
            if state == Qt.CheckState.Checked.value:
                self.plugin_loader.enable_plugin(name)
            else:
                self.plugin_loader.disable_plugin(name)

    def get_settings(self):
        return {
            "color_mode": self.color_combo.currentText(),
            # Save enabled modules dynamically
            "enabled_modules": [name for name, cb in self.module_checks.items() if cb.isChecked()]
        }

class PluginLoader:
    def __init__(self, app, main_window, canvas, tab_widget):
        self.app = app
        self.main_window = main_window
        self.canvas = canvas
        self.tab_widget = tab_widget
        self.plugins = {}
        self.plugin_widgets = {}

    def load_plugin(self, path):
        if not os.path.isfile(path):
            print(f"Plugin not found: {path}")
            return
        try:
            name = os.path.splitext(os.path.basename(path))[0]
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "register_plugin"):
                widget = module.register_plugin(self.app, self.main_window, self.canvas)
                self.plugins[name] = module
                if widget:
                    self.plugin_widgets[name] = widget
                print(f"Plugin loaded: {name}")
            else:
                print(f"Plugin {name} missing register_plugin() function.")
        except Exception as e:
            print(f"Failed to load plugin {path}: {e}")

    def load_plugins_from_folder(self, folder):
        if not os.path.isdir(folder):
            print(f"Plugin folder not found: {folder}")
            return
        for filename in os.listdir(folder):
            if filename.endswith(".py"):
                full_path = os.path.join(folder, filename)
                self.load_plugin(full_path)

    def _tab_for_plugin(self, name):
        for i in range(self.tab_widget.count()):
            if self.tab_widget.widget(i) == self.plugin_widgets.get(name):
                return True
        return False

    def enable_plugin(self, name):
        if name in self.plugin_widgets:
            widget = self.plugin_widgets[name]
            if not self._tab_for_plugin(name):
                self.tab_widget.addTab(widget, name.capitalize())
            widget.show()
            print(f"Enabled plugin: {name}")

    def disable_plugin(self, name):
        if name in self.plugin_widgets:
            widget = self.plugin_widgets[name]
            index = self.tab_widget.indexOf(widget)
            if index != -1:
                self.tab_widget.removeTab(index)
            print(f"Disabled plugin: {name}")

class HelioCAD(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HelioCAD v0.6 Plugin State Save Fix")
        self.settings = QSettings("Sunflare-Inc", "HelioCAD")

        icon_path = "resources/icon.png"
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.canvas = Canvas()

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.canvas, "Core (2D)")

        self.plugin_loader = PluginLoader(QApplication.instance(), self, self.canvas, self.tab_widget)

        container = QWidget()
        container_layout = QVBoxLayout()

        tool_row = QHBoxLayout()
        for name in ["line", "rectangle", "circle"]:
            btn = QPushButton(name.capitalize())
            btn.clicked.connect(lambda _, t=name: self.set_tool(t))
            tool_row.addWidget(btn)

        export_btn = QPushButton("Export SVG")
        export_btn.clicked.connect(self.export_svg)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_file)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_file)

        load_plugin_btn = QPushButton("Load Plugin")
        load_plugin_btn.clicked.connect(self.load_plugin_dialog)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)

        for btn in [export_btn, save_btn, load_btn, load_plugin_btn, settings_btn]:
            tool_row.addWidget(btn)

        container_layout.addLayout(tool_row)
        container_layout.addWidget(self.tab_widget)
        container.setLayout(container_layout)
        self.setCentralWidget(container)
        self.resize(1000, 700)

        # Load all plugins first
        self.plugin_loader.load_plugins_from_folder(PLUGIN_FOLDER)

        # Now check saved enabled modules and disable the rest immediately
        enabled_modules = self.settings.value("enabled_modules", [])
        if not isinstance(enabled_modules, list):
            enabled_modules = []
        # Enable only saved enabled modules
        for mod_name in self.plugin_loader.plugins.keys():
            if mod_name in enabled_modules:
                self.plugin_loader.enable_plugin(mod_name)
            else:
                self.plugin_loader.disable_plugin(mod_name)

        self.apply_color_mode(self.settings.value("color_mode", "light"))

    def set_tool(self, tool):
        if self.tab_widget.currentWidget() == self.canvas:
            self.canvas.current_tool = tool

    def export_svg(self):
        if self.tab_widget.currentWidget() == self.canvas:
            path, _ = QFileDialog.getSaveFileName(self, "Export SVG", "", "SVG Files (*.svg)")
            if path:
                color_mode = self.settings.value("color_mode", "light")
                self.canvas.export_svg(path, color_mode=color_mode)

    def save_file(self):
        if self.tab_widget.currentWidget() == self.canvas:
            path, _ = QFileDialog.getSaveFileName(self, "Save", "", "HelioCAD Files (*.hcad)")
            if path:
                self.canvas.save_hcad(path)

    def load_file(self):
        if self.tab_widget.currentWidget() == self.canvas:
            path, _ = QFileDialog.getOpenFileName(self, "Load", "", "HelioCAD Files (*.hcad)")
            if path:
                self.canvas.load_hcad(path)

    def load_plugin_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Plugin", "", "Python Files (*.py)")
        if path:
            self.plugin_loader.load_plugin(path)

    def open_settings(self):
        dlg = SettingsDialog(self, self.settings, self.plugin_loader)
        if dlg.exec():
            new_settings = dlg.get_settings()
            self.settings.setValue("color_mode", new_settings["color_mode"])
            self.settings.setValue("enabled_modules", new_settings["enabled_modules"])
            self.apply_color_mode(new_settings["color_mode"])

    def apply_color_mode(self, mode):
        self.canvas.set_color_mode(mode)
        if mode == "dark":
            self.setStyleSheet("""
                QWidget {
                    background-color: #222;
                    color: #ddd;
                }
                QPushButton {
                    background-color: #444;
                    color: #ddd;
                    border: none;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #666;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: white;
                    color: black;
                }
                QPushButton {
                    background-color: #eee;
                    color: black;
                    border: 1px solid #ccc;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #ddd;
                }
            """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HelioCAD()

    if len(sys.argv) > 1:
        filename = sys.argv[1]
        if os.path.isfile(filename):
            window.canvas.load_hcad(filename)

    window.show()
    sys.exit(app.exec())
