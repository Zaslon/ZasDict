"""
ZasDict - 編集画面モジュール
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QPushButton, QLabel, QTextEdit, QWidget, QScrollArea,
    QListWidget, QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from typing import Dict, List, Optional
import uuid


class TranslationWidget(QWidget):
    """品詞と訳語のセット"""
    
    remove_requested = Signal(object)  # 削除要求シグナル
    
    # 品詞の選択肢（バリデーション用）
    VALID_POS = [
        "名詞", "動詞", "形容詞", "副詞", "前置詞", 
        "接続詞", "代名詞", "冠詞", "感嘆詞", "助動詞"
    ]
    
    def __init__(self, removable=True, parent=None):
        super().__init__(parent)
        self.removable = removable
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 品詞
        self.pos_combo = QComboBox()
        self.pos_combo.setEditable(True)
        self.pos_combo.addItems(self.VALID_POS)
        self.pos_combo.setMaximumWidth(120)
        
        # 訳語
        self.translation_input = QLineEdit()
        self.translation_input.setPlaceholderText("訳語を入力...")
        
        layout.addWidget(QLabel("品詞:"))
        layout.addWidget(self.pos_combo)
        layout.addWidget(QLabel("訳語:"))
        layout.addWidget(self.translation_input)
        
        # 削除ボタン（最初の1つ以外に表示）
        if self.removable:
            remove_btn = QPushButton("－")
            remove_btn.setMaximumWidth(30)
            remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
            layout.addWidget(remove_btn)
        
        self.setLayout(layout)
    
    def get_data(self) -> Dict:
        """データを取得"""
        return {
            "title": self.pos_combo.currentText(),
            "forms": [f.strip() for f in self.translation_input.text().split(",") if f.strip()]
        }
    
    def set_data(self, pos: str, forms: List[str]):
        """データを設定"""
        self.pos_combo.setCurrentText(pos)
        self.translation_input.setText(", ".join(forms))


class RelationWidget(QWidget):
    """関連語のセット"""
    
    remove_requested = Signal(object)
    
    # 関係の選択肢（バリデーション用）
    VALID_RELATIONS = [
        "同義語", "反義語", "類義語", "派生語", "複合語", "関連語"
    ]
    
    def __init__(self, dictionary_data, search_index, id_map, removable=True, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.removable = removable
        self.selected_entry_id = None
        self._build_ui()
    
    def _build_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 関係
        self.relation_combo = QComboBox()
        self.relation_combo.setEditable(True)
        self.relation_combo.addItems(self.VALID_RELATIONS)
        self.relation_combo.setMaximumWidth(120)
        
        # 単語選択ボタン
        self.word_button = QPushButton("単語を選択...")
        self.word_button.clicked.connect(self._select_word)
        
        # 選択された単語表示
        self.selected_label = QLabel("(未選択)")
        
        layout.addWidget(QLabel("関係:"))
        layout.addWidget(self.relation_combo)
        layout.addWidget(self.word_button)
        layout.addWidget(self.selected_label)
        layout.addStretch()
        
        # 削除ボタン
        if self.removable:
            remove_btn = QPushButton("－")
            remove_btn.setMaximumWidth(30)
            remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
            layout.addWidget(remove_btn)
        
        self.setLayout(layout)
    
    def _select_word(self):
        """単語選択ダイアログを開く"""
        dialog = WordSelectDialog(
            self.dictionary_data, 
            self.search_index, 
            self.id_map, 
            self
        )
        if dialog.exec() == QDialog.Accepted:
            entry_id, form = dialog.get_selected()
            self.selected_entry_id = entry_id
            self.selected_label.setText(form)
    
    def get_data(self) -> Optional[Dict]:
        """データを取得"""
        if not self.selected_entry_id:
            return None
        return {
            "title": self.relation_combo.currentText(),
            "entry": {"id": self.selected_entry_id}
        }
    
    def set_data(self, relation: str, entry_id: str, form: str):
        """データを設定"""
        self.relation_combo.setCurrentText(relation)
        self.selected_entry_id = entry_id
        self.selected_label.setText(form)


class WordSelectDialog(QDialog):
    """単語選択ダイアログ"""
    
    def __init__(self, dictionary_data, search_index, id_map, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.selected_entry_id = None
        self.selected_form = None
        
        self.setWindowTitle("単語を選択")
        self.resize(600, 400)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout()
        
        # 検索欄
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("検索語を入力...")
        self.search_input.textChanged.connect(self._update_results)
        
        # 結果リスト
        self.result_list = QListWidget()
        self.result_list.itemDoubleClicked.connect(self._on_double_click)
        
        # ボタン
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addWidget(QLabel("検索:"))
        layout.addWidget(self.search_input)
        layout.addWidget(self.result_list)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 初期表示（全件）
        self._update_results("")
    
    def _update_results(self, text: str):
        """検索結果を更新"""
        self.result_list.clear()
        self.result_entries = []
        
        # wordsリストを取得
        words = self.dictionary_data.get("words", [])
        if not words:
            return
        
        if not text:
            # 全件表示
            for entry in words:
                form = entry.get("entry", {}).get("form", "")
                if form:
                    self.result_list.addItem(form)
                    self.result_entries.append(entry)
        else:
            # 前方一致検索
            text_lower = text.lower()
            for entry in words:
                form = entry.get("entry", {}).get("form", "")
                if form and form.lower().startswith(text_lower):
                    self.result_list.addItem(form)
                    self.result_entries.append(entry)
    
    def _on_double_click(self):
        """ダブルクリック時"""
        self._select_current()
        self.accept()
    
    def _on_ok(self):
        """OK押下時"""
        self._select_current()
        self.accept()
    
    def _select_current(self):
        """現在選択中の項目を取得"""
        current_row = self.result_list.currentRow()
        if 0 <= current_row < len(self.result_entries):
            entry = self.result_entries[current_row]
            self.selected_entry_id = entry["entry"]["id"]
            self.selected_form = entry["entry"]["form"]
    
    def get_selected(self):
        """選択された単語を取得"""
        return self.selected_entry_id, self.selected_form


class EntryEditorDialog(QDialog):
    """エントリ編集ダイアログ"""
    
    def __init__(self, dictionary_data, search_index, id_map, initial_form="", existing_entry=None, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.initial_form = initial_form
        self.existing_entry = existing_entry  # 既存エントリ（編集時）
        self.is_edit_mode = existing_entry is not None
        
        self.translation_widgets = []
        self.relation_widgets = []
        
        title = "単語編集" if self.is_edit_mode else "新規単語登録"
        self.setWindowTitle(title)
        self.resize(700, 600)
        self._build_ui()
        
        # 既存データを読み込む
        if self.is_edit_mode:
            self._load_existing_data()
    
    def _build_ui(self):
        main_layout = QVBoxLayout()
        
        # スクロール可能な領域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        
        # 見出し語
        scroll_layout.addWidget(QLabel("見出し語:"))
        self.form_input = QLineEdit()
        self.form_input.setText(self.initial_form)
        scroll_layout.addWidget(self.form_input)
        
        # 品詞・訳語
        scroll_layout.addWidget(QLabel("品詞・訳語:"))
        self.translation_container = QVBoxLayout()
        self._add_translation(removable=False)
        
        add_trans_btn = QPushButton("＋ 品詞・訳語を追加")
        add_trans_btn.clicked.connect(lambda: self._add_translation(removable=True))
        
        scroll_layout.addLayout(self.translation_container)
        scroll_layout.addWidget(add_trans_btn)
        
        # 語法
        scroll_layout.addWidget(QLabel("語法:"))
        self.usage_input = QTextEdit()
        self.usage_input.setMaximumHeight(80)
        scroll_layout.addWidget(self.usage_input)
        
        # 語源
        scroll_layout.addWidget(QLabel("語源:"))
        self.etymology_input = QTextEdit()
        self.etymology_input.setMaximumHeight(80)
        scroll_layout.addWidget(self.etymology_input)
        
        # 関連語
        scroll_layout.addWidget(QLabel("関連語:"))
        self.relation_container = QVBoxLayout()
        
        add_rel_btn = QPushButton("＋ 関連語を追加")
        add_rel_btn.clicked.connect(lambda: self._add_relation(removable=True))
        
        scroll_layout.addLayout(self.relation_container)
        scroll_layout.addWidget(add_rel_btn)
        
        scroll_layout.addStretch()
        
        # ボタン
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addWidget(scroll)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def _add_translation(self, removable=True):
        """品詞・訳語セットを追加"""
        widget = TranslationWidget(removable=removable, parent=self)
        widget.remove_requested.connect(self._remove_translation)
        self.translation_container.addWidget(widget)
        self.translation_widgets.append(widget)
    
    def _remove_translation(self, widget):
        """品詞・訳語セットを削除"""
        self.translation_widgets.remove(widget)
        widget.deleteLater()
    
    def _add_relation(self, removable=True):
        """関連語セットを追加"""
        widget = RelationWidget(
            self.dictionary_data,
            self.search_index,
            self.id_map,
            removable=removable,
            parent=self
        )
        widget.remove_requested.connect(self._remove_relation)
        self.relation_container.addWidget(widget)
        self.relation_widgets.append(widget)
    
    def _remove_relation(self, widget):
        """関連語セットを削除"""
        self.relation_widgets.remove(widget)
        widget.deleteLater()
    
    def get_entry_data(self) -> Dict:
        """エントリデータを取得"""
        # 編集モードの場合は既存のIDを使用、新規の場合は生成
        if self.is_edit_mode:
            entry_id = self.existing_entry["entry"]["id"]
        else:
            entry_id = self._generate_unique_id()
        
        # 翻訳データ
        translations = [w.get_data() for w in self.translation_widgets]
        translations = [t for t in translations if t["forms"]]  # 空でないもののみ
        
        # 関連語データ
        relations = [w.get_data() for w in self.relation_widgets]
        relations = [r for r in relations if r is not None]  # 選択されているもののみ
        
        # コンテンツ
        contents = []
        usage_text = self.usage_input.toPlainText().strip()
        if usage_text:
            contents.append({"title": "語法", "text": usage_text})
        
        etymology_text = self.etymology_input.toPlainText().strip()
        if etymology_text:
            contents.append({"title": "語源", "text": etymology_text})
        
        entry_data = {
            "entry": {
                "id": entry_id,
                "form": self.form_input.text().strip()
            },
            "translations": translations,
            "tags": [],
            "contents": contents,
            "variations": [],
            "relations": relations
        }
        
        return entry_data
    
    def _generate_unique_id(self) -> str:
        """一意なIDを生成"""
        existing_ids = set()
        for entry in self.dictionary_data.get("words", []):
            entry_id = entry.get("entry", {}).get("id")
            if entry_id:
                existing_ids.add(entry_id)
        
        while True:
            new_id = str(uuid.uuid4())
            if new_id not in existing_ids:
                return new_id
    
    def _load_existing_data(self):
        """既存データを読み込む"""
        if not self.existing_entry:
            return
        
        # 見出し語
        self.form_input.setText(self.existing_entry["entry"]["form"])
        
        # 品詞・訳語
        translations = self.existing_entry.get("translations", [])
        if translations:
            # 最初の1つは既に作成済みなので設定
            if len(self.translation_widgets) > 0:
                first = translations[0]
                self.translation_widgets[0].set_data(
                    first.get("title", ""),
                    first.get("forms", [])
                )
            
            # 2つ目以降を追加
            for trans in translations[1:]:
                self._add_translation(removable=True)
                self.translation_widgets[-1].set_data(
                    trans.get("title", ""),
                    trans.get("forms", [])
                )
        
        # 語法・語源
        for content in self.existing_entry.get("contents", []):
            title = content.get("title", "")
            text = content.get("text", "")
            
            if title == "語法":
                self.usage_input.setPlainText(text)
            elif title == "語源":
                self.etymology_input.setPlainText(text)
        
        # 関連語
        relations = self.existing_entry.get("relations", [])
        for rel in relations:
            self._add_relation(removable=True)
            
            rel_entry_id = rel.get("entry", {}).get("id", "")
            rel_form = ""
            
            # IDから見出し語を取得（id_mapを使用）
            if rel_entry_id in self.id_map:
                rel_form = self.id_map[rel_entry_id]["entry"]["form"]
            
            self.relation_widgets[-1].set_data(
                rel.get("title", ""),
                rel_entry_id,
                rel_form
            )