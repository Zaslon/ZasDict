"""
ZasDict - 辞書検索アプリケーション
インターフェース
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

import const
from func import DictionaryLoader, SearchWorker

from editor import EntryEditorDialog

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
        self.width_spin.setValue(parent.width() if parent else const.DEFAULT_WINDOW_WIDTH)
        self.height_spin.setValue(parent.height() if parent else const.DEFAULT_WINDOW_HEIGHT)
        
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
        
        current_size = const.DEFAULT_FONT_SIZE
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
        self.setWindowTitle(const.APP_TITLE)
        
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
        font_family = self.settings.value("font", const.DEFAULT_FONT_FAMILY)
        font_size = int(self.settings.value("size", const.DEFAULT_FONT_SIZE))
        width = int(self.settings.value("width", const.DEFAULT_WINDOW_WIDTH))
        height = int(self.settings.value("height", const.DEFAULT_WINDOW_HEIGHT))
        
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
        
        # 検索UI（固定サイズ、ストレッチ0）
        main_layout.addLayout(self._create_search_layout(), 0)
        
        # コンテンツUI（可変サイズ、ストレッチ1で残りの領域を使用）
        main_layout.addLayout(self._create_content_layout(), 1)
        
        # メニューバー
        self._create_menu_bar()
    
    def _create_search_layout(self) -> QHBoxLayout:
        """検索レイアウトを作成"""
        layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索語を入力...")
        self.search_input.textChanged.connect(self.update_results)
        self.search_input.returnPressed.connect(self._on_search_enter)
        self.search_input.setFont(self.default_font)
        
        self.search_mode = QComboBox()
        self.search_mode.addItems(const.SEARCH_MODES)
        self.search_mode.currentTextChanged.connect(self._on_search_options_changed)
        
        self.search_scope = QComboBox()
        self.search_scope.addItems(const.SEARCH_SCOPES)
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
        self.result_list.itemDoubleClicked.connect(self._on_result_double_click)
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
        
        # menu_bar.setStyleSheet("QMenuBar { border-bottom: 1px solid gray; }")
        
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
        self.setWindowTitle(f"{const.APP_TITLE}：{file_name}")
    
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
                json.dump(self.dictionary_data, f, ensure_ascii=False, separators=(",", ":"))
            
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
        self.result_entries = []  # インデックス順にエントリを保持
        
        for entry in results:
            form = entry["entry"]["form"]
            
            # 同音異義語の場合は番号を付ける
            display_form = form
            count = sum(1 for e in self.result_entries 
                       if e["entry"]["form"] == form)
            if count > 0:
                display_form = f"{form} ({count + 1})"
            
            self.result_list.addItem(display_form)
            self.result_entries.append(entry)
    
    def show_detail(self, selected_text: str):
        """詳細を表示"""
        if not selected_text:
            self.detail_view.clear()
            return
        
        if not selected_text:
            self.detail_view.clear()
            return
        
        # 選択されたリストのインデックスを取得
        current_index = self.result_list.currentRow()
        
        if 0 <= current_index < len(self.result_entries):
            entry = self.result_entries[current_index]
            detail_text = self._format_entry_detail(entry)
            self.detail_view.setPlainText(detail_text)
    
    @staticmethod
    def _format_entry_detail(entry: Dict) -> str:
        """エントリの詳細をフォーマット。すべて結合した文字列データとして出力する。"""
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

    # ----------------------------------------------------------------
    # 単語登録
    # ----------------------------------------------------------------

    def _on_search_enter(self):
        """検索欄でEnterキー押下時の処理"""
        modifiers = QApplication.keyboardModifiers()
        
        # Ctrl+Enter: 新規登録
        if modifiers == Qt.ControlModifier:
            self._open_editor_new()
        # Enter: 検索実行（既に実装済み）
        else:
            pass

    def _on_result_double_click(self, item):
        """結果リストでダブルクリック時の処理"""
        self._open_editor_edit()

    def _open_editor_new(self):
        """新規登録用エディタを開く"""
        if not self.dictionary_data:
            QMessageBox.warning(
                self,
                "辞書未読込",
                "先に辞書ファイルを開いてください。"
            )
            return
        
        initial_form = self.search_input.text().strip()
        
        dialog = EntryEditorDialog(
            self.dictionary_data,
            self.search_index,
            self.id_map,
            initial_form=initial_form,
            parent=self
        )
        
        if dialog.exec() == QDialog.Accepted:
            entry_data = dialog.get_entry_data()
            self._register_entry(entry_data)

    def _open_editor_edit(self):
        """編集用エディタを開く"""
        current_row = self.result_list.currentRow()
        
        if current_row < 0 or current_row >= len(self.result_entries):
            return
        
        # 選択されたエントリを取得
        entry = self.result_entries[current_row]
        
        dialog = EntryEditorDialog(
            self.dictionary_data,
            self.search_index,
            self.id_map,
            initial_form="",
            existing_entry=entry,
            parent=self
        )
        
        if dialog.exec() == QDialog.Accepted:
            entry_data = dialog.get_entry_data()
            self._update_entry(entry_data)

    def _register_entry(self, entry_data: Dict):
        """エントリを登録"""
        entry_id = entry_data["entry"]["id"]
        form = entry_data["entry"]["form"]
        
        # wordsリストに追加
        if "words" not in self.dictionary_data:
            self.dictionary_data["words"] = []
        
        self.dictionary_data["words"].append(entry_data)
        
        # 検索インデックスを再構築
        self.search_index, self.id_map = DictionaryLoader.build_search_index(
            self.dictionary_data
        )
        
        # ワーカーのインデックスを更新
        self.worker.index = self.search_index
        self.worker.id_map = self.id_map
        
        QMessageBox.information(
            self,
            "登録完了",
            f"「{form}」を登録しました。"
        )
        
        # 検索結果を更新
        current_text = self.search_input.text()
        if current_text:
            self.update_results(current_text)

    def _update_entry(self, entry_data: Dict):
        """エントリを更新"""
        entry_id = entry_data["entry"]["id"]
        form = entry_data["entry"]["form"]
        
        # 既存エントリを検索して更新
        words = self.dictionary_data.get("words", [])
        for i, entry in enumerate(words):
            if entry.get("entry", {}).get("id") == entry_id:
                self.dictionary_data["words"][i] = entry_data
                break
        
        # 検索インデックスを再構築
        self.search_index, self.id_map = DictionaryLoader.build_search_index(
            self.dictionary_data
        )
        
        # ワーカーのインデックスを更新
        self.worker.index = self.search_index
        self.worker.id_map = self.id_map
        
        QMessageBox.information(
            self,
            "更新完了",
            f"「{form}」を更新しました。"
        )
        
        # 検索結果を更新
        current_text = self.search_input.text()
        if current_text:
            self.update_results(current_text)


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