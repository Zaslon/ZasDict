from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QListWidget, QTextEdit, QMenuBar, QMenu, QFileDialog,
    QDialog, QLabel, QPushButton, QSpinBox, QCheckBox, QFontComboBox, QMessageBox
)
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QMetaObject, Q_ARG, QSettings
import os, sys, json, re
from functools import cmp_to_key

APP_TITLE = "ZasDict"

# カスタム文字順序
ORDER = "eaoiuhkstcnrmpfgzdbv- "
ORDER_MAP = {ch: i for i, ch in enumerate(ORDER)}

def preprocess(s: str):
    """処理した文字列を返す"""
    # 語頭と語末の '-' を削除
    s = re.sub(r"^-+", "", s)
    s = re.sub(r"-+$", "", s)
    # （）、’ を削除
    s = s.replace("（", "").replace("）", "").replace("'", "")
    # 小文字化
    return s.lower()

def compare_forms(a: str, b: str):
    orig_a, orig_b = a, b
    proc_a, proc_b = preprocess(a), preprocess(b)

    # 1. 処理した文字列を先頭から比較
    for ca, cb in zip(proc_a, proc_b):
        if ca != cb:
            return ORDER_MAP.get(ca, 999) - ORDER_MAP.get(cb, 999)
    # 2. 短い方を先
    if len(proc_a) != len(proc_b):
        return len(proc_a) - len(proc_b)

    # 3. ’ の有無
    if ("'" in orig_a) != ("'" in orig_b):
        return -1 if "'" not in orig_a else 1

    # 4. 大文字の位置
    for ca, cb in zip(orig_a, orig_b):
        if ca != cb:
            if ca.isupper() and cb.islower():
                return -1
            if cb.isupper() and ca.islower():
                return 1

    # 5. 記号の有無
    symbols = set("-()")
    a_has_symbol = any(ch in symbols for ch in orig_a)
    b_has_symbol = any(ch in symbols for ch in orig_b)
    if a_has_symbol != b_has_symbol:
        return -1 if not a_has_symbol else 1

    # 6. '-' の位置（語末に近い方を先）
    if "-" in orig_a or "-" in orig_b:
        pos_a = orig_a.rfind("-") if "-" in orig_a else -1
        pos_b = orig_b.rfind("-") if "-" in orig_b else -1
        if pos_a != pos_b:
            return (len(orig_a) - pos_a) - (len(orig_b) - pos_b)

    # 7. 括弧の位置
    if "（" in orig_a or "（" in orig_b:
        pos_a = orig_a.find("（") if "（" in orig_a else 999
        pos_b = orig_b.find("（") if "（" in orig_b else 999
        if pos_a != pos_b:
            return pos_a - pos_b
        # 同じなら「）」の位置
        pos_a = orig_a.find("）") if "）" in orig_a else 999
        pos_b = orig_b.find("）") if "）" in orig_b else 999
        if pos_a != pos_b:
            return pos_a - pos_b

    return 0

# ソート関数
def sort_entries(entries):
    return sorted(entries, key=cmp_to_key(lambda a, b: compare_forms(a["entry"]["form"], b["entry"]["form"])))

# --- 検索ロジック部分 ---
def load_dictionary(json_file_path):
    with open(json_file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_search_index(dictionary_data):
    index = {}
    for word_entry in dictionary_data.get("words", []):
        # 基本形
        form = word_entry.get("entry", {}).get("form", "")
        if form:
            index.setdefault(form.lower(), []).append(word_entry)

        # 訳語
        for t in word_entry.get("translations", []):
            for f in t.get("forms", []):
                if f:
                    index.setdefault(f.lower(), []).append(word_entry)

        # バリエーション
        for v in word_entry.get("variations", []):
            f = v.get("form", "")
            if f:
                index.setdefault(f.lower(), []).append(word_entry)

        # 関連語
        for r in word_entry.get("relations", []):
            f = r.get("entry", {}).get("form", "")
            if f:
                index.setdefault(f.lower(), []).append(word_entry)

        # タグ
        for tag in word_entry.get("tags", []):
            if tag:
                index.setdefault(tag.lower(), []).append(word_entry)

        # コンテンツ本文（部分一致用）
        for c in word_entry.get("contents", []):
            text = c.get("text", "")
            if text:
                for word in text.split():
                    index.setdefault(word.lower(), []).append(word_entry)

    return index

def search_prefix(index, keyword):
    keyword_lower = keyword.lower()
    results = []
    for key in index.keys():
        if key.startswith(keyword_lower):
            results.extend(index[key])
    return results

# UI側と検索処理を分けるためのワーカクラス
class SearchWorker(QObject):
    finished = Signal(int, list)  # (job_id, results)

    def __init__(self, index, dictionary_data):
        super().__init__()
        self.index = index
        self.dictionary_data = dictionary_data
        self.current_job_id = 0
        self.cancelled_jobs = set()

    @Slot(int, str, str, str)
    def run_search(self, job_id, mode, scope, text):
        # 古いジョブなら無視
        if job_id in self.cancelled_jobs:
            return

        results = []

        # --- 検索対象を制御 ---
        if scope == "見出し語・訳語":
            results = []
            for entry in self.dictionary_data.get("words", []):
                forms = []
                form = entry.get("entry", {}).get("form", "")
                if form:
                    forms.append(form.lower())
                for t in entry.get("translations", []):
                    for f in t.get("forms", []):
                        if f:
                            forms.append(f.lower())

                # 検索方法に応じて判定
                if mode == "部分":
                    if all(k in " ".join(forms) for k in text.lower().split()):
                        results.append(entry)
                elif mode == "前方":
                    if any(f.startswith(text.lower()) for f in forms):
                        results.append(entry)
                elif mode == "後方":
                    if any(f.endswith(text.lower()) for f in forms):
                        results.append(entry)
                elif mode == "完全":
                    if text.lower() in forms:
                        results.append(entry)
        else:
            filtered_index = self.index

            # --- 検索方法 ---
            if mode == "部分":   # ← self.mode ではなく mode
                keywords = text.lower().split()
                results = [entry for key, entries in filtered_index.items()
                        if all(k in key for k in keywords)   # AND検索
                        for entry in entries]
            elif mode == "前方":
                keyword = text.lower()
                results = [entry for key, entries in filtered_index.items()
                        if key.startswith(keyword) for entry in entries]
            elif mode == "後方":
                keyword = text.lower()
                results = [entry for key, entries in filtered_index.items()
                        if key.endswith(keyword) for entry in entries]
            elif mode == "完全":
                keyword = text.lower()
                results = filtered_index.get(keyword, [])

        results = sort_entries(results)
        self.finished.emit(job_id, results)  # ← job_id を渡す

# --- GUIアプリケーション ---
class DictionaryApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)

        # --- 設定読み込み ---
        self.settings = QSettings("settings.ini", QSettings.IniFormat)
        font_family = self.settings.value("font", "Arial")
        font_size = int(self.settings.value("size", 12))
        width = int(self.settings.value("width", 800))
        height = int(self.settings.value("height", 600))
        last_file = self.settings.value("last_dictionary", "")
        if last_file:
            last_file = os.path.abspath(last_file)  # 相対パスを絶対パスに変換
            if os.path.exists(last_file):
                try:
                    self.dictionary_data = load_dictionary(last_file)
                    self.search_index = build_search_index(self.dictionary_data)

                    file_name = os.path.basename(last_file)
                    self.setWindowTitle(f"{APP_TITLE}：{file_name}")
                except Exception as e:
                    QMessageBox.warning(self, "辞書読み込みエラー", f"{last_file}\n{e}")

        # ウィンドウサイズ適用
        self.resize(width, height)

        # フォント適用
        default_font = QFont(font_family, font_size)

        # スレッドとワーカーを1つだけ作成
        self.thread = QThread()
        self.worker = SearchWorker(self.search_index, self.dictionary_data)
        self.worker.moveToThread(self.thread)
        self.thread.start()

        # 結果を受け取る
        self.worker.finished.connect(self.on_search_finished)

        # ジョブID管理
        self.job_counter = 0
        self.latest_job_id = 0

        # メインウィジェットとレイアウト
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # 検索バーとモード選択
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索語を入力...")
        self.search_input.textChanged.connect(self.update_results)
        self.search_input.setFont(default_font)

        self.search_mode = QComboBox()
        self.search_mode.addItems(["部分","前方", "後方", "完全",])
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_mode)
        main_layout.addLayout(search_layout)

        # 検索対象選択
        self.search_scope = QComboBox()
        self.search_scope.addItems(["見出し語・訳語", "全文"])
        search_layout.addWidget(self.search_scope)

        # 検索結果と内容表示のレイアウト
        content_layout = QHBoxLayout()
        self.result_list = QListWidget()
        self.result_list.currentTextChanged.connect(self.show_detail)
        self.result_list.setFont(default_font)

        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setFont(default_font)

        content_layout.addWidget(self.result_list, 1)
        content_layout.addWidget(self.detail_view, 2)
        main_layout.addLayout(content_layout)
        
        # メニューバー
        menu_bar = QMenuBar()

        # ファイルメニュー
        file_menu = QMenu("ファイル", self)
        open_action = QAction("開く", self)
        save_action = QAction("保存", self)
        exit_action = QAction("終了", self)

        open_action.triggered.connect(self.open_file)
        save_action.triggered.connect(self.save_file)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(exit_action)

        # 設定メニュー
        settings_menu = QMenu("設定", self)
        preferences_action = QAction("環境設定", self)

        preferences_action.triggered.connect(self.open_preferences)

        settings_menu.addAction(preferences_action)

        # メニューバーに追加
        menu_bar.addMenu(file_menu)
        menu_bar.addMenu(settings_menu)

        self.setMenuBar(menu_bar)


    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "辞書ファイルを開く", "", "JSON Files (*.json)")
        if file_path:
            try:
                self.dictionary_data = load_dictionary(file_path)
                self.search_index = build_search_index(self.dictionary_data)
                self.result_list.clear()
                self.detail_view.clear()
                self.search_input.setText("")

                # タイトルを更新
                file_name = os.path.basename(file_path)
                self.setWindowTitle(f"{APP_TITLE}：{file_name}")

                # 最後に開いたファイルを保存
                rel_path = os.path.relpath(file_path, os.getcwd())
                self.settings.setValue("last_dictionary", rel_path)

            except Exception as e:
                QMessageBox.critical(self, "読み込みエラー", str(e))


    def save_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "辞書ファイルを保存", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.dictionary_data, f, ensure_ascii=False, indent=2)

                # --- 成功時のポップアップ ---
                file_name = os.path.basename(file_path)
                QMessageBox.information(self, "保存成功", f"辞書ファイルを保存しました:\n{file_name}")

            except Exception as e:
                # --- エラー時のポップアップ ---
                QMessageBox.critical(self, "保存エラー", str(e))

    def open_preferences(self):
        dialog = PreferencesDialog(self)
        if dialog.exec() == QDialog.Accepted:
            settings = dialog.get_settings()

            # フォント適用
            font = QFont(settings["font"], settings["size"])
            self.result_list.setFont(font)
            self.detail_view.setFont(font)
            self.search_input.setFont(font)

            # ウィンドウサイズ適用
            self.resize(settings["width"], settings["height"])

            # --- 設定保存 ---
            self.settings.setValue("font", settings["font"])
            self.settings.setValue("size", settings["size"])
            self.settings.setValue("width", settings["width"])
            self.settings.setValue("height", settings["height"])

    def show_detail(self, selected_text):
        if not selected_text:
            self.detail_view.clear()
            return
        entries = self.search_index.get(selected_text.lower(), [])
        if entries:
            entry = entries[0]
            form = entry.get("entry", {}).get("form", "")
            translations = entry.get("translations", [])
            tags = entry.get("tags", [])
            contents = entry.get("contents", [])
            variations = entry.get("variations", [])
            relations = entry.get("relations", [])

            detail_lines = [f"単語: {form}"]

            # 訳語
            for t in translations:
                detail_lines.append(f"品詞: {t.get('title','')}")
                detail_lines.append("訳語: " + ", ".join(t.get("forms", [])))

            # タグ
            if tags:
                detail_lines.append("タグ: " + ", ".join(tags))

            # コンテンツ
            for c in contents:
                detail_lines.append(f"{c.get('title','')}: {c.get('text','')}")

            # バリエーション
            for v in variations:
                detail_lines.append(f"{v.get('title','')}: {v.get('form','')}")

            # 関連語
            for r in relations:
                rel_form = r.get("entry", {}).get("form", "")
                detail_lines.append(f"{r.get('title','')}: {rel_form}")

            self.detail_view.setPlainText("\n".join(detail_lines))

    def update_results(self, text):
        if not text or not self.search_index:
            self.result_list.clear()
            return

        self.job_counter += 1
        job_id = self.job_counter
        self.latest_job_id = job_id

        # Workerに検索を依頼
        QMetaObject.invokeMethod(
            self.worker,
            "run_search",
            Qt.QueuedConnection,
            Q_ARG(int, job_id),
            Q_ARG(str, self.search_mode.currentText()),
            Q_ARG(str, self.search_scope.currentText()),
            Q_ARG(str, text)
        )

    def on_search_finished(self, job_id, results):
        # 最新ジョブのみ反映
        if job_id != self.latest_job_id:
            return

        self.result_list.clear()
        seen = set()
        for entry in results:
            form = entry.get("entry", {}).get("form", "")
            if form and form not in seen:
                self.result_list.addItem(form)
                seen.add(form)

    def closeEvent(self, event):
        # 終了時にスレッドを安全に停止
        self.thread.quit()
        self.thread.wait()
        # 現在のウィンドウサイズを保存
        # ウィンドウサイズだけは環境設定画面以外から変更可能であるため、終了時に保存する
        self.settings.setValue("width", self.width())
        self.settings.setValue("height", self.height())

        # 親クラスの処理を呼び出して終了
        super().closeEvent(event)

class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("環境設定")
        self.resize(400, 250)

        layout = QVBoxLayout()
 
        # 親ウィンドウの現在のフォントを取得
        current_font = parent.search_input.font() if parent else QFont()
        current_size = current_font.pointSize()

        # ウィンドウサイズ選択（幅・高さ）
        window_layout = QHBoxLayout()
        window_label = QLabel("ウィンドウサイズ:")
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        self.width_spin.setRange(400, 1920)
        self.height_spin.setRange(300, 1080)

        # 親ウィンドウの現在サイズに連動
        if parent:
            self.width_spin.setValue(parent.width())
            self.height_spin.setValue(parent.height())
        else:
            self.width_spin.setValue(800)
            self.height_spin.setValue(600)

        window_layout.addWidget(window_label)
        window_layout.addWidget(QLabel("幅"))
        window_layout.addWidget(self.width_spin)
        window_layout.addWidget(QLabel("高さ"))
        window_layout.addWidget(self.height_spin)
        layout.addLayout(window_layout)

        # フォント選択
        font_layout = QHBoxLayout()
        font_label = QLabel("フォント:")
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(current_font)
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_combo)
        layout.addLayout(font_layout)

        # フォントサイズ選択
        size_layout = QHBoxLayout()
        size_label = QLabel("フォントサイズ:")
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 48)
        self.size_spin.setValue(current_size if current_size > 0 else 14)
        size_layout.addWidget(size_label)
        size_layout.addWidget(self.size_spin)
        layout.addLayout(size_layout)

        # OK/キャンセルボタン
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("キャンセル")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def get_settings(self):
        return {
            "font": self.font_combo.currentFont().family(),
            "size": self.size_spin.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
        }
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DictionaryApp()
    window.show()
    sys.exit(app.exec())
