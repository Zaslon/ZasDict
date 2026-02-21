from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit, QFileDialog, QDialog, QTextBrowser
from PySide6.QtCore import QFileSystemWatcher
import sys
import csv
import os

class ChangelogViewerWidget(QWidget):
    """変更履歴閲覧ウィジェット
    閲覧のみで編集不可。対称ファイルに変更があれば自動で開きなおす。

    args:
    filepath 閲覧履歴ファイルのフルパス
    """
    def __init__(self, filepath = None):
        super().__init__()
        self.setWindowTitle("Changelog Viewer")

        self.text = QTextBrowser()

        layout = QVBoxLayout(self)
        layout.addWidget(self.text)

        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.on_file_changed)

        # test.csv を自動で読み込み
        self.load_csv(filepath)

        # 存在するなら監視開始
        if os.path.exists(filepath):
            self.watcher.addPath(filepath)

    def load_csv(self, path):
        if not os.path.exists(path):
            self.text.setText("test.csv が存在しません")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                content = "\n".join([", ".join(row) for row in reader])
                self.text.setText(content)
        except Exception as e:
            self.text.setText(f"読み込みエラー: {e}")

    def on_file_changed(self, path):
        # ファイル変更を検知したら再読み込み
        self.load_csv(path)

        # Excel などが「削除→再作成」する場合があるため再監視
        if os.path.exists(path) and path not in self.watcher.files():
            self.watcher.addPath(path)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ChangelogViewerWidget()
    w.show()
    sys.exit(app.exec())
