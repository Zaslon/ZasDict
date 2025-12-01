"""
ZasDict - 辞書検索アプリケーション
リファクタリング版
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QListWidget, QTextEdit, QMenuBar, QMenu, QFileDialog,
    QDialog, QLabel, QPushButton, QSpinBox, QFontComboBox, QMessageBox
)
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QMetaObject, Q_ARG, QSettings
import os
import sys
import json
import re
from functools import cmp_to_key
from typing import Dict, List, Set, Tuple, Optional

# ============================================================================
# 定数
# ============================================================================

APP_TITLE = "ZasDict"
CUSTOM_ORDER = "eaoiuhkstcnrmpfgzdbv- "
DEFAULT_FONT_FAMILY = "Arial"
DEFAULT_FONT_SIZE = 12
DEFAULT_WINDOW_WIDTH = 800
DEFAULT_WINDOW_HEIGHT = 600

SEARCH_MODES = ["部分", "前方", "後方", "完全"]
SEARCH_SCOPES = ["見出し語・訳語", "全文"]


# ============================================================================
# ソート・前処理ユーティリティ
# ============================================================================

class TextProcessor:
    """テキストの前処理とソート用のユーティリティクラス"""
    
    ORDER_MAP = {ch: i for i, ch in enumerate(CUSTOM_ORDER)}
    
    @staticmethod
    def preprocess(text: str) -> str:
        """前処理: ハイフン・括弧・アポストロフィを除去し小文字化"""
        text = re.sub(r"^-+", "", text)
        text = re.sub(r"-+$", "", text)
        text = text.replace("（", "").replace("）", "").replace("'", "")
        return text.lower()
    
    @classmethod
    def compare_forms(cls, a: str, b: str) -> int:
        """カスタムソート順による比較関数"""
        orig_a, orig_b = a, b
        proc_a, proc_b = cls.preprocess(a), cls.preprocess(b)
        
        # 1. カスタム順序で比較
        for ca, cb in zip(proc_a, proc_b):
            if ca != cb:
                return cls.ORDER_MAP.get(ca, 999) - cls.ORDER_MAP.get(cb, 999)
        
        # 2. 長さで比較
        if len(proc_a) != len(proc_b):
            return len(proc_a) - len(proc_b)
        
        # 3. アポストロフィの有無
        if ("'" in orig_a) != ("'" in orig_b):
            return -1 if "'" not in orig_a else 1
        
        # 4. 大文字小文字
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
        
        # 6. ハイフン位置
        if "-" in orig_a or "-" in orig_b:
            pos_a = orig_a.rfind("-") if "-" in orig_a else -1
            pos_b = orig_b.rfind("-") if "-" in orig_b else -1
            if pos_a != pos_b:
                return (len(orig_a) - pos_a) - (len(orig_b) - pos_b)
        
        # 7. 括弧位置
        if "（" in orig_a or "（" in orig_b:
            pos_a = orig_a.find("（") if "（" in orig_a else 999
            pos_b = orig_b.find("（") if "（" in orig_b else 999
            if pos_a != pos_b:
                return pos_a - pos_b
            pos_a = orig_a.find("）") if "）" in orig_a else 999
            pos_b = orig_b.find("）") if "）" in orig_b else 999
            if pos_a != pos_b:
                return pos_a - pos_b
        
        return 0
    
    @classmethod
    def sort_entries(cls, entries: List[Dict]) -> List[Dict]:
        """エントリをカスタムソート順でソート"""
        return sorted(
            entries,
            key=cmp_to_key(lambda a, b: cls.compare_forms(
                a["entry"]["form"],
                b["entry"]["form"]
            ))
        )


# ============================================================================
# 辞書データ管理
# ============================================================================

class DictionaryLoader:
    """辞書データの読み込みとインデックス構築"""
    
    @staticmethod
    def load(file_path: str) -> Dict:
        """JSONファイルから辞書データを読み込む"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def build_search_index(dictionary_data: Dict) -> Tuple[Dict[str, Set[str]], Dict[str, Dict]]:
        """検索用インデックスとIDマップを構築"""
        index = {}
        id_map = {}
        
        for word_entry in dictionary_data.get("words", []):
            entry = word_entry.get("entry", {})
            word_id = entry.get("id")
            form = entry.get("form", "")
            
            if not word_id or not form:
                continue
            
            id_map[word_id] = word_entry
            keys = [form.lower()]
            
            # 訳語
            for translation in word_entry.get("translations", []):
                keys.extend([f.lower() for f in translation.get("forms", []) if f])
            
            # バリエーション
            for variation in word_entry.get("variations", []):
                if variation.get("form"):
                    keys.append(variation["form"].lower())
            
            # 関連語
            for relation in word_entry.get("relations", []):
                rel_entry = relation.get("entry", {})
                if rel_entry.get("form"):
                    keys.append(rel_entry["form"].lower())
            
            # タグ
            keys.extend([tag.lower() for tag in word_entry.get("tags", [])])
            
            # 内容テキスト
            for content in word_entry.get("contents", []):
                text = content.get("text", "")
                if text:
                    keys.extend([word.lower() for word in text.split()])
            
            # インデックスに追加
            for key in keys:
                index.setdefault(key, set()).add(word_id)
        
        return index, id_map


# ============================================================================
# 検索ワーカー
# ============================================================================

class SearchWorker(QObject):
    """バックグラウンドで検索を実行するワーカー"""
    
    finished = Signal(int, list)
    
    def __init__(self, index: Dict[str, Set[str]], id_map: Dict[str, Dict]):
        super().__init__()
        self.index = index
        self.id_map = id_map
    
    @Slot(int, str, str, str)
    def run_search(self, job_id: int, mode: str, scope: str, text: str):
        """検索を実行"""
        results = set()
        keyword = text.lower()
        
        if scope == "見出し語・訳語":
            results = self._search_headword_translation(keyword, mode)
        else:
            results = self._search_fulltext(keyword, mode)
        
        final_results = [self.id_map[i] for i in results if i in self.id_map]
        final_results = TextProcessor.sort_entries(final_results)
        self.finished.emit(job_id, final_results)
    
    def _search_headword_translation(self, keyword: str, mode: str) -> Set[str]:
        """見出し語・訳語での検索"""
        results = set()
        
        for entry in self.id_map.values():
            word_id = entry["entry"]["id"]
            forms = [entry["entry"]["form"].lower()]
            
            for translation in entry.get("translations", []):
                forms.extend([f.lower() for f in translation.get("forms", []) if f])
            
            if self._match(forms, keyword, mode):
                results.add(word_id)
        
        return results
    
    def _search_fulltext(self, keyword: str, mode: str) -> Set[str]:
        """全文検索"""
        results = set()
        
        for key, ids in self.index.items():
            if self._match([key], keyword, mode):
                results.update(ids)
        
        return results
    
    @staticmethod
    def _match(forms: List[str], keyword: str, mode: str) -> bool:
        """マッチング判定"""
        if mode == "部分":
            text = " ".join(forms)
            return all(k in text for k in keyword.split())
        elif mode == "前方":
            return any(f.startswith(keyword) for f in forms)
        elif mode == "後方":
            return any(f.endswith(keyword) for f in forms)
        elif mode == "完全":
            return keyword in forms
        return False


# ============================================================================
# 環境設定ダイアログ
# ============================================================================

class PreferencesDialog(QDialog):
    """環境設定ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("環境設定")
        self.resize(400, 250)
        
        layout = QVBoxLayout()
        
        # ウィンドウサイズ
        layout.addLayout(self._create_window_size_layout(parent))
        
        # フォント
        layout.addLayout(self._create_font_layout(parent))
        
        # フォントサイズ
        layout.addLayout(self._create_font_size_layout(parent))
        
        # ボタン
        layout.addLayout(self._create_button_layout())
        
        self.setLayout(layout)
    
    def _create_window_size_layout(self, parent) -> QHBoxLayout:
        """ウィンドウサイズ設定レイアウト"""
        layout = QHBoxLayout()
        
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        self.width_spin.setRange(400, 1920)
        self.height_spin.setRange(300, 1080)
        self.width_spin.setValue(parent.width() if parent else DEFAULT_WINDOW_WIDTH)
        self.height_spin.setValue(parent.height() if parent else DEFAULT_WINDOW_HEIGHT)
        
        layout.addWidget(QLabel("ウィンドウサイズ:"))
        layout.addWidget(QLabel("幅"))
        layout.addWidget(self.width_spin)
        layout.addWidget(QLabel("高さ"))
        layout.addWidget(self.height_spin)
        
        return layout
    
    def _create_font_layout(self, parent) -> QHBoxLayout:
        """フォント設定レイアウト"""
        layout = QHBoxLayout()
        
        self.font_combo = QFontComboBox()
        if parent:
            self.font_combo.setCurrentFont(parent.search_input.font())
        
        layout.addWidget(QLabel("フォント:"))
        layout.addWidget(self.font_combo)
        
        return layout
    
    def _create_font_size_layout(self, parent) -> QHBoxLayout:
        """フォントサイズ設定レイアウト"""
        layout = QHBoxLayout()
        
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 48)
        
        current_size = DEFAULT_FONT_SIZE
        if parent:
            font_size = parent.search_input.font().pointSize()
            if font_size > 0:
                current_size = font_size
        
        self.size_spin.setValue(current_size)
        
        layout.addWidget(QLabel("フォントサイズ:"))
        layout.addWidget(self.size_spin)
        
        return layout
    
    def _create_button_layout(self) -> QHBoxLayout:
        """ボタンレイアウト"""
        layout = QHBoxLayout()
        
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("キャンセル")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        layout.addWidget(ok_button)
        layout.addWidget(cancel_button)
        
        return layout
    
    def get_settings(self) -> Dict:
        """設定値を取得"""
        return {
            "font": self.font_combo.currentFont().family(),
            "size": self.size_spin.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
        }


# ============================================================================
# メインウィンドウ
# ============================================================================

class DictionaryApp(QMainWindow):
    """辞書アプリケーションのメインウィンドウ"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        
        # 設定とデータの初期化
        self.settings = QSettings("settings.ini", QSettings.IniFormat)
        self.dictionary_data = {}
        self.search_index = {}
        self.id_map = {}
        self.job_counter = 0
        self.latest_job_id = 0
        
        # 設定の読み込み
        self._load_settings()
        
        # 検索ワーカーの初期化
        self._init_search_worker()
        
        # UIの構築
        self._build_ui()
        
        # 前回の辞書ファイルを読み込み
        self._load_last_dictionary()
    
    def _load_settings(self):
        """設定を読み込む"""
        font_family = self.settings.value("font", DEFAULT_FONT_FAMILY)
        font_size = int(self.settings.value("size", DEFAULT_FONT_SIZE))
        width = int(self.settings.value("width", DEFAULT_WINDOW_WIDTH))
        height = int(self.settings.value("height", DEFAULT_WINDOW_HEIGHT))
        
        self.resize(width, height)
        self.default_font = QFont(font_family, font_size)
    
    def _init_search_worker(self):
        """検索ワーカーを初期化"""
        self.thread = QThread()
        self.worker = SearchWorker(self.search_index, self.id_map)
        self.worker.moveToThread(self.thread)
        self.thread.start()
        self.worker.finished.connect(self.on_search_finished)
    
    def _build_ui(self):
        """UIを構築"""
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # 検索UI
        main_layout.addLayout(self._create_search_layout())
        
        # コンテンツUI
        main_layout.addLayout(self._create_content_layout())
        
        # メニューバー
        self._create_menu_bar()
    
    def _create_search_layout(self) -> QHBoxLayout:
        """検索レイアウトを作成"""
        layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索語を入力...")
        self.search_input.textChanged.connect(self.update_results)
        self.search_input.setFont(self.default_font)
        
        self.search_mode = QComboBox()
        self.search_mode.addItems(SEARCH_MODES)
        self.search_mode.currentTextChanged.connect(self._on_search_options_changed)
        
        self.search_scope = QComboBox()
        self.search_scope.addItems(SEARCH_SCOPES)
        self.search_scope.currentTextChanged.connect(self._on_search_options_changed)
        
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_mode)
        layout.addWidget(self.search_scope)
        
        return layout
    
    def _create_content_layout(self) -> QHBoxLayout:
        """コンテンツレイアウトを作成"""
        layout = QHBoxLayout()
        
        self.result_list = QListWidget()
        self.result_list.currentTextChanged.connect(self.show_detail)
        self.result_list.setFont(self.default_font)
        
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setFont(self.default_font)
        
        layout.addWidget(self.result_list, 1)
        layout.addWidget(self.detail_view, 2)
        
        return layout
    
    def _create_menu_bar(self):
        """メニューバーを作成"""
        menu_bar = self.menuBar()
        
        # ファイルメニュー
        file_menu = menu_bar.addMenu("ファイル")
        file_menu.addAction(self._create_action("開く", self.open_file))
        file_menu.addAction(self._create_action("保存", self.save_file))
        file_menu.addAction(self._create_action("終了", self.close))
        
        # 設定メニュー
        settings_menu = menu_bar.addMenu("設定")
        settings_menu.addAction(self._create_action("環境設定", self.open_preferences))
    
    def _create_action(self, text: str, slot) -> QAction:
        """アクションを作成"""
        action = QAction(text, self)
        action.triggered.connect(slot)
        return action
    
    def _load_last_dictionary(self):
        """前回開いた辞書ファイルを読み込む"""
        last_file = self.settings.value("last_dictionary", "")
        if not last_file:
            return
        
        last_file = os.path.abspath(last_file)
        if not os.path.exists(last_file):
            return
        
        try:
            self._load_dictionary_file(last_file)
        except Exception as e:
            QMessageBox.warning(
                self,
                "辞書読み込みエラー",
                f"{last_file}\n{e}"
            )
    
    def _load_dictionary_file(self, file_path: str):
        """辞書ファイルを読み込む"""
        self.dictionary_data = DictionaryLoader.load(file_path)
        self.search_index, self.id_map = DictionaryLoader.build_search_index(
            self.dictionary_data
        )
        
        # ワーカーのインデックスを更新
        self.worker.index = self.search_index
        self.worker.id_map = self.id_map
        
        # タイトルを更新
        file_name = os.path.basename(file_path)
        self.setWindowTitle(f"{APP_TITLE}：{file_name}")
    
    # ----------------------------------------------------------------
    # ファイル操作
    # ----------------------------------------------------------------
    
    def open_file(self):
        """辞書ファイルを開く"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "辞書ファイルを開く",
            "",
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            self._load_dictionary_file(file_path)
            
            # UIをクリア
            self.result_list.clear()
            self.detail_view.clear()
            self.search_input.setText("")
            
            # 設定に保存
            rel_path = os.path.relpath(file_path, os.getcwd())
            self.settings.setValue("last_dictionary", rel_path)
            
        except Exception as e:
            QMessageBox.critical(self, "読み込みエラー", str(e))
    
    def save_file(self):
        """辞書ファイルを保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "辞書ファイルを保存",
            "",
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.dictionary_data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(
                self,
                "保存成功",
                f"辞書ファイルを保存しました:\n{os.path.basename(file_path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))
    
    # ----------------------------------------------------------------
    # 環境設定
    # ----------------------------------------------------------------
    
    def open_preferences(self):
        """環境設定ダイアログを開く"""
        dialog = PreferencesDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        
        settings = dialog.get_settings()
        font = QFont(settings["font"], settings["size"])
        
        # フォントとサイズを適用
        self.result_list.setFont(font)
        self.detail_view.setFont(font)
        self.search_input.setFont(font)
        self.resize(settings["width"], settings["height"])
        
        # 設定を保存
        self.settings.setValue("font", settings["font"])
        self.settings.setValue("size", settings["size"])
        self.settings.setValue("width", settings["width"])
        self.settings.setValue("height", settings["height"])
    
    # ----------------------------------------------------------------
    # 検索と表示
    # ----------------------------------------------------------------
    
    def _on_search_options_changed(self):
        """検索オプション（モード・スコープ）変更時の処理"""
        text = self.search_input.text()
        if text:
            self.update_results(text)
    
    def update_results(self, text: str):
        """検索結果を更新"""
        if not text or not self.search_index:
            self.result_list.clear()
            return
        
        self.job_counter += 1
        job_id = self.job_counter
        self.latest_job_id = job_id
        
        QMetaObject.invokeMethod(
            self.worker,
            "run_search",
            Qt.QueuedConnection,
            Q_ARG(int, job_id),
            Q_ARG(str, self.search_mode.currentText()),
            Q_ARG(str, self.search_scope.currentText()),
            Q_ARG(str, text)
        )
    
    def on_search_finished(self, job_id: int, results: List[Dict]):
        """検索完了時の処理"""
        if job_id != self.latest_job_id:
            return
        
        self.result_list.clear()
        seen_ids = set()
        
        for entry in results:
            word_id = entry["entry"]["id"]
            form = entry["entry"]["form"]
            if word_id not in seen_ids:
                self.result_list.addItem(form)
                seen_ids.add(word_id)
    
    def show_detail(self, selected_text: str):
        """詳細を表示"""
        if not selected_text:
            self.detail_view.clear()
            return
        
        # formからエントリを検索
        entries = [
            entry for entry in self.id_map.values()
            if entry["entry"]["form"] == selected_text
        ]
        
        if not entries:
            return
        
        entry = entries[0]
        detail_text = self._format_entry_detail(entry)
        self.detail_view.setPlainText(detail_text)
    
    @staticmethod
    def _format_entry_detail(entry: Dict) -> str:
        """エントリの詳細をフォーマット"""
        lines = [f"単語: {entry['entry']['form']}"]
        
        # 訳語
        for translation in entry.get("translations", []):
            lines.append(f"品詞: {translation.get('title', '')}")
            forms = ", ".join(translation.get("forms", []))
            lines.append(f"訳語: {forms}")
        
        # タグ
        tags = entry.get("tags", [])
        if tags:
            lines.append(f"タグ: {', '.join(tags)}")
        
        # 内容
        for content in entry.get("contents", []):
            lines.append(f"{content.get('title', '')}: {content.get('text', '')}")
        
        # バリエーション
        for variation in entry.get("variations", []):
            lines.append(f"{variation.get('title', '')}: {variation.get('form', '')}")
        
        # 関連語
        for relation in entry.get("relations", []):
            rel_form = relation.get("entry", {}).get("form", "")
            lines.append(f"{relation.get('title', '')}: {rel_form}")
        
        return "\n".join(lines)
    
    # ----------------------------------------------------------------
    # イベントハンドラ
    # ----------------------------------------------------------------
    
    def closeEvent(self, event):
        """ウィンドウを閉じる時の処理"""
        self.thread.quit()
        self.thread.wait()
        
        # ウィンドウサイズを保存
        self.settings.setValue("width", self.width())
        self.settings.setValue("height", self.height())
        
        super().closeEvent(event)


# ============================================================================
# エントリーポイント
# ============================================================================

def main():
    """アプリケーションのエントリーポイント"""
    app = QApplication(sys.argv)
    window = DictionaryApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()