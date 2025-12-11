"""
ZasDict - 辞書検索アプリケーション
インターフェース
"""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QWidgetAction, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QLineEdit, QComboBox, QListWidget, QTextEdit, QMenuBar, QMenu, QFileDialog,
    QDialog, QLabel, QPushButton, QSpinBox, QFontComboBox, QMessageBox, QCheckBox
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
from kaiomom import convert_idyer
from ipa import ipaToSpell
from editor import EntryEditorDialog

# ============================================================================
# 環境設定ダイアログ
# ============================================================================

class PreferencesDialog(QDialog):
    """環境設定ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("環境設定")
        self.resize(400, 300)
        
        layout = QVBoxLayout()
        
        # ウィンドウサイズ
        layout.addLayout(self._create_window_size_layout(parent))
        
        # フォント
        layout.addLayout(self._create_font_layout(parent))
        
        # フォントサイズ
        layout.addLayout(self._create_font_size_layout(parent))

        # UIフォント
        layout.addLayout(self._create_ui_font_layout(parent))
        
        # UIフォントサイズ
        layout.addLayout(self._create_ui_font_size_layout(parent))
        
        # 自動保存
        layout.addLayout(self._create_auto_save_layout(parent))
        
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
    
    def _create_ui_font_layout(self, parent) -> QHBoxLayout:
        """UIフォント設定レイアウト"""
        layout = QHBoxLayout()
        
        self.ui_font_combo = QFontComboBox()
        if parent:
            self.ui_font_combo.setCurrentFont(parent.font())
        
        layout.addWidget(QLabel("UIフォント:"))
        layout.addWidget(self.ui_font_combo)
        
        return layout
    
    def _create_ui_font_size_layout(self, parent) -> QHBoxLayout:
        """UIフォントサイズ設定レイアウト"""
        layout = QHBoxLayout()
        
        self.ui_font_size_spin = QSpinBox()
        self.ui_font_size_spin.setRange(8, 48)
        
        current_size = const.DEFAULT_FONT_SIZE
        if parent:
            font_size = parent.font().pointSize()
            if font_size > 0:
                current_size = font_size
        
        self.ui_font_size_spin.setValue(current_size)
        
        layout.addWidget(QLabel("UIフォントサイズ:"))
        layout.addWidget(self.ui_font_size_spin)
        
        return layout
    
    def _create_auto_save_layout(self, parent) -> QHBoxLayout:
        """自動保存設定レイアウト"""
        layout = QHBoxLayout()
        
        self.auto_save_check = QCheckBox("自動上書き保存を有効にする")
        if parent:
            auto_save = parent.settings.value("auto_save", "false")
            self.auto_save_check.setChecked(auto_save == "true")
        
        layout.addWidget(self.auto_save_check)
        
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
            "ui_font": self.ui_font_combo.currentFont().family(),
            "size": self.size_spin.value(),
            "ui_font_size": self.ui_font_size_spin.value(),
            "width": self.width_spin.value(),
            "height": self.height_spin.value(),
            "auto_save": self.auto_save_check.isChecked(),
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
        self.has_unsaved_changes = False
        self.current_file_path = None
        
        # 設定の読み込み
        self._load_settings()
        
        # 前回の辞書ファイルを読み込み
        self._load_last_dictionary()

        # 検索ワーカーの初期化
        # 辞書ファイルの読み込み後に呼び出すこと
        self._init_search_worker()
        
        # UIの構築
        self._build_ui()
        
    
    def _load_settings(self):
        """設定を読み込む"""
        font_family = self.settings.value("font", const.DEFAULT_FONT_FAMILY)
        font_size = int(self.settings.value("size", const.DEFAULT_FONT_SIZE))
        ui_font_family = self.settings.value("ui_font", const.DEFAULT_FONT_FAMILY)
        ui_font_size = int(self.settings.value("ui_font_size", const.DEFAULT_FONT_SIZE))
        width = int(self.settings.value("width", const.DEFAULT_WINDOW_WIDTH))
        height = int(self.settings.value("height", const.DEFAULT_WINDOW_HEIGHT))
        
        self.resize(width, height)
        self.default_font = QFont(font_family, font_size)
        
        # UIフォントをアプリケーション全体に適用
        ui_font = QFont(ui_font_family, ui_font_size)
        QApplication.instance().setFont(ui_font)
    
    def _init_search_worker(self):
        """検索ワーカーを初期化"""
        self.thread = QThread()
        self.worker = SearchWorker(self.search_index, self.id_map, self.dictionary_data)
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
        self.result_list.itemActivated.connect(self._on_result_enter)
        self.result_list.itemDoubleClicked.connect(self._on_result_double_click)
        self.result_list.setFont(self.default_font)
        self.result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_list.customContextMenuRequested.connect(self._on_result_right_click)
        
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
        file_menu.addAction(self._create_action("上書き保存", self.save_file))
        file_menu.addAction(self._create_action("名前を付けて保存", self.save_as_file))
        file_menu.addAction(self._create_action("終了", self.close))
        
        # 設定メニュー
        settings_menu = menu_bar.addMenu("設定")
        settings_menu.addAction(self._create_action("環境設定", self.open_preferences))
        settings_menu.addAction(self._create_action("辞書依存設定", self.open_dictionary_settings))
        settings_menu.addAction(self._create_action("変換", self.open_idyer_converter))
        settings_menu.addAction(self._create_action("IPA", self.open_ipa_converter))

        # 右端に表示したい文字列
        label = QLabel("Hello World")
        label.setStyleSheet("padding-right: 10px;")  # 少し余白をつけると綺麗

        menu_bar.setCornerWidget(label, Qt.TopRightCorner)

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
        
        # ワーカーが存在する場合はインデックスを更新
        if hasattr(self, 'worker'):
            self.worker.index = self.search_index
            self.worker.id_map = self.id_map
        
        # 現在のファイルパスを記憶
        self.current_file_path = file_path
        self.has_unsaved_changes = False
        
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
        """辞書ファイルを上書き保存"""
        # 既存ファイルがあれば上書き保存
        if self.current_file_path:
            return self._save_to_file(self.current_file_path)
        
        # 新規保存
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "辞書ファイルを上書き保存",
            "",
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return False
        
        return self._save_to_file(file_path)
    
    def save_as_file(self):
        """辞書ファイルを名前を付けて保存"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "辞書ファイルを名前を付けて保存",
            "",
            "JSON Files (*.json)"
        )
        if not file_path:
            return False
        return self._save_to_file(file_path)

    def _save_to_file(self, file_path: str) -> bool:
        """指定されたパスにファイルを保存"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.dictionary_data, f, ensure_ascii=False, separators=(",", ":"))
            
            self.current_file_path = file_path
            self.has_unsaved_changes = False
            
            # タイトルから「*」を削除
            file_name = os.path.basename(file_path)
            self.setWindowTitle(f"{const.APP_TITLE}：{file_name}")
            
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", str(e))
            return False
    
    def _auto_save_if_enabled(self):
        """自動保存が有効な場合に保存を実行"""
        auto_save = self.settings.value("auto_save", "false")
        if auto_save == "true" and self.current_file_path:
            self._save_to_file(self.current_file_path)
    
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
        ui_font = QFont(settings["ui_font"], settings["ui_font_size"])
        
        # フォントとサイズを適用
        QApplication.instance().setFont(ui_font)
        self.result_list.setFont(font)
        self.detail_view.setFont(font)
        self.search_input.setFont(font)
        self.resize(settings["width"], settings["height"])
        
        # 設定を保存
        self.settings.setValue("font", settings["font"])
        self.settings.setValue("size", settings["size"])
        self.settings.setValue("width", settings["width"])
        self.settings.setValue("height", settings["height"])
        self.settings.setValue("ui_font", settings["ui_font"])
        self.settings.setValue("ui_font_size", settings["ui_font_size"])
        self.settings.setValue("auto_save", "true" if settings["auto_save"] else "false")

    def open_idyer_converter(self):
        """変換ダイアログを開く"""
        dialog = DialectConverterDialog(self)
        dialog.show()

    def open_ipa_converter(self):
        """IPA変換ダイアログを開く"""
        dialog = IPAConverterDialog(self)
        dialog.show()
    
    def open_dictionary_settings(self):
        """辞書依存設定ダイアログを開く"""
        if not self.dictionary_data:
            QMessageBox.warning(
                self,
                "辞書未読込",
                "先に辞書ファイルを開いてください。"
            )
            return
        
        dialog = DictionarySettingsDialog(self.dictionary_data, self)
        if dialog.exec() != QDialog.Accepted:
            return
        
        # 設定を反映
        punctuations = dialog.get_punctuations()
        
        # zpdicOnlineセクションがなければ作成
        if "zpdicOnline" not in self.dictionary_data:
            self.dictionary_data["zpdicOnline"] = {}
        
        self.dictionary_data["zpdicOnline"]["punctuations"] = punctuations
        
        # 変更フラグを立てる
        self._mark_as_modified()
        
        # 自動保存
        self._auto_save_if_enabled()
        
        QMessageBox.information(
            self,
            "設定完了",
            f"区切り文字を設定しました: {''.join(punctuations)}"
        )

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
        # 未保存の変更がある場合は確認
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "未保存の変更",
                "保存されていない変更があります。保存しますか？",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Yes:
                # 保存処理
                if not self.save_file():
                    # 保存がキャンセルされた場合は終了処理を中断
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                # キャンセルの場合は終了処理を中断
                event.ignore()
                return
            # No の場合は保存せずに終了
        
        self.thread.quit()
        self.thread.wait()
        
        # ウィンドウサイズを保存
        self.settings.setValue("width", self.width())
        self.settings.setValue("height", self.height())
        
        super().closeEvent(event)

    def _on_search_enter(self):
        """検索欄でEnterキー押下時の処理"""
        modifiers = QApplication.keyboardModifiers()
        
        # Ctrl+Enter: 新規登録
        if modifiers == Qt.ControlModifier:
            self._open_editor_new()
        # Enter: 検索結果がある場合、一番上を選択し、コンテンツ欄にフォーカス
        elif self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            self.result_list.setFocus()

    def _on_result_enter(self):
        """コンテンツ欄でEnterキー押下時の処理"""
        modifiers = QApplication.keyboardModifiers()
        
        # Ctrl+Enter: フォーカスのある語の編集画面を開く
        if modifiers == Qt.ControlModifier:
            self._open_editor_edit()
        # Enter: 検索欄にフォーカス
        else:
            self.search_input.setFocus()

    def _on_result_double_click(self, item):
        """結果リストでダブルクリック時の処理"""
        self._open_editor_edit()

    def _on_result_right_click(self, position):
        """リスト項目の右クリックメニューを表示"""
        item = self.result_list.itemAt(position)
        if item is None:
            return
        
        menu = QMenu(self)
        
        edit_action = menu.addAction("編集")
        # duplicate_action = menu.addAction("複製")
        delete_action = menu.addAction("削除")
        
        action = menu.exec(self.result_list.mapToGlobal(position))
        
        if action == edit_action:
            self._open_editor_edit()
        # elif action == duplicate_action:
        #     self._open_editor_duplicate()
        elif action == delete_action:
            self._delete_entry()

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
        
        dialog.setWindowModality(Qt.WindowModal)
        dialog.accepted.connect(lambda: self._register_entry_with_relations(dialog))
        dialog.show()

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

        dialog.setWindowModality(Qt.WindowModal)
        dialog.accepted.connect(lambda: self._update_entry_with_relations(dialog))
        dialog.show()

    # ----------------------------------------------------------------
    # 単語登録
    # ----------------------------------------------------------------

    def _register_entry_with_relations(self, dialog):
        """エントリを登録し、相手方に逆方向の関連語を追加
        
        Args:
            dialog: EntryEditorDialog インスタンス
        """
        entry_data = dialog.get_entry_data()
        entry_id = entry_data["entry"]["id"]
        form = entry_data["entry"]["form"]
        
        # wordsリストに追加
        if "words" not in self.dictionary_data:
            self.dictionary_data["words"] = []
        
        self.dictionary_data["words"].append(entry_data)
        
        # 相手方に逆方向の関連語を追加
        dialog.apply_reciprocal_relations()
        
        # 変更フラグを立てる
        self._mark_as_modified()
        
        # 自動保存
        self._auto_save_if_enabled()
        
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

    def _update_entry_with_relations(self, dialog):
        """エントリを更新し、相手方に逆方向の関連語を追加
        
        Args:
            dialog: EntryEditorDialog インスタンス
        """
        entry_data = dialog.get_entry_data()
        entry_id = entry_data["entry"]["id"]
        form = entry_data["entry"]["form"]
        
        # 既存エントリを検索して更新
        words = self.dictionary_data.get("words", [])
        for i, entry in enumerate(words):
            if entry.get("entry", {}).get("id") == entry_id:
                self.dictionary_data["words"][i] = entry_data
                break
        
        # 相手方に逆方向の関連語を追加
        dialog.apply_reciprocal_relations()
        
        # 変更フラグを立てる
        self._mark_as_modified()
        
        # 自動保存
        self._auto_save_if_enabled()
        
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

    def _delete_entry(self):
        """選択中のエントリを削除"""
        current_row = self.result_list.currentRow()
        
        if current_row < 0 or current_row >= len(self.result_entries):
            QMessageBox.warning(
                self,
                "エントリ未選択",
                "削除するエントリを選択してください。"
            )
            return
        
        # 選択されたエントリを取得
        entry = self.result_entries[current_row]
        entry_id = entry.get("entry", {}).get("id")
        form = entry.get("entry", {}).get("form", "")
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "エントリの削除",
            f"「{form}」を削除しますか？\n\n他のエントリの関連語からも削除されます。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # wordsリストから削除
        words = self.dictionary_data.get("words", [])
        self.dictionary_data["words"] = [
            e for e in words 
            if e.get("entry", {}).get("id") != entry_id
        ]
        
        # 他のエントリの関連語からも削除
        for word_entry in self.dictionary_data.get("words", []):
            relations = word_entry.get("relations", [])
            word_entry["relations"] = [
                rel for rel in relations
                if rel.get("entry", {}).get("id") != entry_id
            ]
        
        # 変更フラグを立てる
        self._mark_as_modified()
        
        # 自動保存
        self._auto_save_if_enabled()
        
        # 検索インデックスを再構築
        self.search_index, self.id_map = DictionaryLoader.build_search_index(
            self.dictionary_data
        )
        
        # ワーカーのインデックスを更新
        self.worker.index = self.search_index
        self.worker.id_map = self.id_map
        
        QMessageBox.information(
            self,
            "削除完了",
            f"「{form}」を削除しました。"
        )
        
        # 検索結果を更新
        current_text = self.search_input.text()
        if current_text:
            self.update_results(current_text)
        else:
            # 検索テキストがない場合は結果をクリア
            self.result_list.clear()
            self.detail_view.clear()
            self.result_entries = []

    def _add_reciprocal_relations(self, source_entry_id: str, reciprocal_relations: List[Dict]):
        """相手方に逆方向の関連語を追加"""
        words = self.dictionary_data.get("words", [])
        
        for recip in reciprocal_relations:
            target_entry_id = recip["target_entry_id"]
            relation_to_add = recip["relation"]
            
            # 新規登録の場合は source_entry_id を設定
            if relation_to_add["entry"]["id"] is None:
                relation_to_add["entry"]["id"] = source_entry_id
            
            # 対象エントリを検索
            for i, entry in enumerate(words):
                if entry.get("entry", {}).get("id") == target_entry_id:
                    # 既存の関連語リストを取得
                    relations = entry.get("relations", [])
                    
                    # 重複チェック（同じ関係タイプと同じIDの組み合わせ）
                    already_exists = False
                    for existing_rel in relations:
                        if (existing_rel.get("title") == relation_to_add["title"] and
                            existing_rel.get("entry", {}).get("id") == relation_to_add["entry"]["id"]):
                            already_exists = True
                            break
                    
                    # 重複していなければ追加
                    if not already_exists:
                        relations.append(relation_to_add)
                        self.dictionary_data["words"][i]["relations"] = relations
                    
                    break

    def _mark_as_modified(self):
        """変更フラグを立て、タイトルに「*」を追加"""
        if not self.has_unsaved_changes:
            self.has_unsaved_changes = True
            
            # タイトルに「*」を追加
            current_title = self.windowTitle()
            if not current_title.endswith("*"):
                self.setWindowTitle(f"{current_title}*")

# ============================================================================
# 変換画面
# ============================================================================

class DialectConverterDialog(QDialog):
    """変換ダイアログ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("変換")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        
        # 入力部分
        input_layout = QHBoxLayout()
        input_label = QLabel("元単語（アクセントは大文字）:")
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("例: nyUryoku")
        self.input_field.returnPressed.connect(self.convert)
        
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.input_field)
        
        # 変換ボタン
        convert_button = QPushButton("変換")
        convert_button.clicked.connect(self.convert)
        
        # 結果表示部分
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        self.result_display.setPlaceholderText("変換結果がここに表示されます")
        
        # 閉じるボタン
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.accept)
        
        # レイアウトに追加
        layout.addLayout(input_layout)
        layout.addWidget(convert_button)
        layout.addWidget(QLabel("変換結果:"))
        layout.addWidget(self.result_display)
        layout.addWidget(close_button)
        
        self.setLayout(layout)

    def convert(self):
        """変換を実行"""
        word = self.input_field.text().strip()
        if not word:
            self.result_display.setPlainText("単語を入力してください")
            return
        
        try:
            result = convert_idyer(word)
            
            # 結果を整形して表示
            output = f"""i.s 旗: {result['sekore']}
i.t 資: {result['titauini']}
i.k 探: {result['kaiko']}
i.a 教: {result['arzafire']}"""
            
            self.result_display.setPlainText(output)
            
        except Exception as e:
            self.result_display.setPlainText(f"エラーが発生しました: {str(e)}")

# ============================================================================
# IPA画面
# ============================================================================

class IPAConverterDialog(QDialog):
    """IPA変換ダイアログ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IPA to Spell Converter")
        self.setMinimumSize(600, 400)
        self.init_ui()
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout()
        
        # 入力セクション
        input_label = QLabel("IPA入力:")
        input_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(input_label)
        
        self.input_text = QLineEdit()
        self.input_text.setPlaceholderText("IPA記号を入力してください（例: ˈhɛloʊ）")
        self.input_text.setMaximumHeight(100)
        layout.addWidget(self.input_text)
        
        # 変換ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.convert_button = QPushButton("変換")
        self.convert_button.clicked.connect(self.convert_ipa)
        self.convert_button.setMinimumWidth(100)
        button_layout.addWidget(self.convert_button)
        
        self.clear_button = QPushButton("クリア")
        self.clear_button.clicked.connect(self.clear_all)
        self.clear_button.setMinimumWidth(100)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 出力セクション
        output_label = QLabel("変換結果:")
        output_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(output_label)
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText("変換結果がここに表示されます")
        layout.addWidget(self.output_text)
        
        # 閉じるボタン
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        
        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.accept)
        self.close_button.setMinimumWidth(100)
        close_layout.addWidget(self.close_button)
        
        layout.addLayout(close_layout)
        
        self.setLayout(layout)
    
    def convert_ipa(self):
        """IPA変換を実行"""
        input_text = self.input_text.toPlainText().strip()
        
        if not input_text:
            self.output_text.setPlainText("入力がありません")
            return
        
        # 各行を変換
        lines = input_text.split('\n')
        results = []
        
        for line in lines:
            if line.strip():
                converted = ipaToSpell(line.strip())
                # results.append(f"元のIPA: {line.strip()}")
                results.append(f"{converted}")
        
        self.output_text.setPlainText('\n'.join(results))
    
    def clear_all(self):
        """すべてのテキストをクリア"""
        self.input_text.clear()
        self.output_text.clear()

# ============================================================================
# 辞書依存設定画面
# ============================================================================

class DictionarySettingsDialog(QDialog):
    """辞書依存設定ダイアログ"""
    
    def __init__(self, dictionary_data: Dict, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.setWindowTitle("辞書依存設定")
        self.resize(500, 300)
        
        layout = QVBoxLayout()
        
        # 説明ラベル
        info_label = QLabel("訳語の区切り文字を設定します（複数指定可）")
        layout.addWidget(info_label)
        
        # 区切り文字入力
        punctuation_layout = QHBoxLayout()
        punctuation_label = QLabel("区切り文字:")
        self.punctuation_edit = QLineEdit()
        
        # 現在の設定を読み込み
        current_punctuations = dictionary_data.get("zpdicOnline", {}).get("punctuations", [","])
        self.punctuation_edit.setText("".join(current_punctuations))
        self.punctuation_edit.setPlaceholderText("例: ,/・")
        
        punctuation_layout.addWidget(punctuation_label)
        punctuation_layout.addWidget(self.punctuation_edit)
        layout.addLayout(punctuation_layout)
        
        # 使用例
        example_label = QLabel("使用例: 「apple, orange / banana・grape」\n→ 各区切り文字で分割されます")
        example_label.setStyleSheet("color: gray; font-size: 10pt;")
        layout.addWidget(example_label)
        
        layout.addStretch()
        
        # ボタン
        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        cancel_button = QPushButton("キャンセル")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def get_punctuations(self) -> List[str]:
        """設定された区切り文字をリストで取得"""
        text = self.punctuation_edit.text().strip()
        if not text:
            return [","]  # デフォルト値
        return list(text)  # 各文字をリストの要素に
    
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