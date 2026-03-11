from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QFileDialog, QDialog, QTextBrowser
from PySide6.QtCore import QFileSystemWatcher
import sys
import csv
import os

class LegendViewerWidget(QWidget):
    """凡例閲覧ウィジェット
    閲覧のみで編集不可。

    args:
    dictionary_data: jsonを読み込んだdictionary_data
    """
    def __init__(self, dictionary_data = None):
        super().__init__()
        self.setWindowTitle("凡例")

        self.text = QTextBrowser()

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)

        self.text.setText(dictionary_data["legend"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = LegendViewerWidget()
    w.show()
    sys.exit(app.exec())
