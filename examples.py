"""
ZasDict - 例文ビューア・エディタ
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QLineEdit, QPlainTextEdit, QLabel, QPushButton, QSpinBox,
    QScrollArea, QDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal
from typing import Dict, List, Optional


class LinkedWordWidget(QWidget):
    """関連単語の表示・削除ウィジェット"""

    remove_requested = Signal(object)

    def __init__(self, entry_id: int, form: str, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # self.label = QLabel(f"#{entry_id} {form}")
        self.label = QLabel(f"{form}")
        remove_btn = QPushButton("－")
        remove_btn.setMaximumWidth(30)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        layout.addWidget(self.label)
        layout.addWidget(remove_btn)
        layout.addStretch()
        self.setLayout(layout)

    def get_id(self) -> int:
        return self.entry_id


class ExamplesViewerWidget(QWidget):
    """例文ビューア・エディタ"""

    changed = Signal()

    def __init__(self, dictionary_data: Dict, search_index: Dict, id_map: Dict,
                 sentence_font=None, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.sentence_font = sentence_font
        self.filtered_examples: List[Dict] = []
        self.linked_word_widgets: List[LinkedWordWidget] = []
        self._editing_new = False
        self._new_id: Optional[int] = None

        self.setWindowTitle("例文")
        self.resize(820, 520)
        self._build_ui()
        self._reload_list()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        splitter = QSplitter(Qt.Horizontal)

        # 左ペイン: 検索 + リスト
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("例文・訳を検索...")
        self.search_input.textChanged.connect(lambda _: self._reload_list())
        left_layout.addWidget(self.search_input)

        self.example_list = QListWidget()
        self.example_list.currentRowChanged.connect(self._on_example_selected)
        if self.sentence_font:
            self.example_list.setFont(self.sentence_font)
        left_layout.addWidget(self.example_list)

        left_widget.setLayout(left_layout)

        # 右ペイン: 編集フォーム
        right_outer = QWidget()
        right_outer_layout = QVBoxLayout()
        right_outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        form_layout = QVBoxLayout()
        scroll_content.setLayout(form_layout)
        scroll.setWidget(scroll_content)

        self.id_label = QLabel("ID: -")
        form_layout.addWidget(self.id_label)

        form_layout.addWidget(QLabel("文:"))
        self.sentence_input = QPlainTextEdit()
        self.sentence_input.setPlaceholderText("例文を入力...")
        self.sentence_input.setMaximumHeight(80)
        self.sentence_input.setTabChangesFocus(True)
        if self.sentence_font:
            self.sentence_input.setFont(self.sentence_font)
        form_layout.addWidget(self.sentence_input)

        form_layout.addWidget(QLabel("訳:"))
        self.translation_input = QPlainTextEdit()
        self.translation_input.setPlaceholderText("翻訳を入力...")
        self.translation_input.setMaximumHeight(80)
        self.translation_input.setTabChangesFocus(True)
        form_layout.addWidget(self.translation_input)

        form_layout.addWidget(QLabel("補足:"))
        self.supplement_input = QPlainTextEdit()
        self.supplement_input.setPlaceholderText("補足情報（任意）")
        self.supplement_input.setMaximumHeight(60)
        self.supplement_input.setTabChangesFocus(True)
        form_layout.addWidget(self.supplement_input)

        form_layout.addWidget(QLabel("タグ（,区切り）:"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("例: 挨拶,日常")
        form_layout.addWidget(self.tags_input)

        form_layout.addWidget(QLabel("関連単語:"))
        self.words_container = QVBoxLayout()
        form_layout.addLayout(self.words_container)
        add_word_btn = QPushButton("＋ 単語を追加")
        add_word_btn.clicked.connect(self._add_linked_word)
        form_layout.addWidget(add_word_btn)

        offer_layout = QHBoxLayout()
        offer_layout.addWidget(QLabel("出典:"))
        self.offer_catalog_input = QLineEdit()
        self.offer_catalog_input.setPlaceholderText("カタログ名")
        offer_layout.addWidget(self.offer_catalog_input)
        offer_layout.addWidget(QLabel("No."))
        self.offer_number_spin = QSpinBox()
        self.offer_number_spin.setRange(0, 999999)
        offer_layout.addWidget(self.offer_number_spin)
        form_layout.addLayout(offer_layout)

        form_layout.addStretch()

        right_outer_layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_current)
        self.delete_btn = QPushButton("削除")
        self.delete_btn.clicked.connect(self._delete_current)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        right_outer_layout.addLayout(btn_layout)

        right_outer.setLayout(right_outer_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_outer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

        add_btn = QPushButton("＋ 例文を追加")
        add_btn.clicked.connect(self._add_new_example)
        main_layout.addWidget(add_btn)

        self.setLayout(main_layout)
        self._set_form_enabled(False)

    def _set_form_enabled(self, enabled: bool):
        self.sentence_input.setEnabled(enabled)
        self.translation_input.setEnabled(enabled)
        self.supplement_input.setEnabled(enabled)
        self.tags_input.setEnabled(enabled)
        self.offer_catalog_input.setEnabled(enabled)
        self.offer_number_spin.setEnabled(enabled)
        self.save_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled and not self._editing_new)

    def _get_examples(self) -> List[Dict]:
        return self.dictionary_data.get("examples", [])

    def _reload_list(self):
        query = self.search_input.text().lower()
        self.filtered_examples = []

        for ex in self._get_examples():
            sentence = ex.get("sentence", "")
            translation = ex.get("translation", "")
            supplement = ex.get("supplement", "")
            if not query or query in sentence.lower() or query in translation.lower() or query in supplement.lower():
                self.filtered_examples.append(ex)

        self.example_list.blockSignals(True)
        self.example_list.clear()
        for ex in self.filtered_examples:
            sentence = ex.get("sentence", "")
            display = sentence[:50] + ("…" if len(sentence) > 50 else "")
            self.example_list.addItem(display)
        self.example_list.blockSignals(False)

        self._editing_new = False
        self._new_id = None
        self._set_form_enabled(False)
        self._clear_form()

    def _clear_form(self):
        self.id_label.setText("ID: -")
        self.sentence_input.clear()
        self.translation_input.clear()
        self.supplement_input.clear()
        self.tags_input.clear()
        self.offer_catalog_input.clear()
        self.offer_number_spin.setValue(0)
        self._clear_linked_words()

    def _clear_linked_words(self):
        for w in self.linked_word_widgets:
            w.deleteLater()
        self.linked_word_widgets.clear()

    def _on_example_selected(self, row: int):
        if row < 0 or row >= len(self.filtered_examples):
            self._set_form_enabled(False)
            self._clear_form()
            return

        self._editing_new = False
        self._new_id = None
        ex = self.filtered_examples[row]

        self.id_label.setText(f"ID: {ex.get('id', '-')}")
        self.sentence_input.setPlainText(ex.get("sentence", ""))
        self.translation_input.setPlainText(ex.get("translation", ""))
        self.supplement_input.setPlainText(ex.get("supplement", ""))
        self.tags_input.setText(", ".join(ex.get("tags", [])))

        offer = ex.get("offer", {})
        self.offer_catalog_input.setText(offer.get("catalog", ""))
        self.offer_number_spin.setValue(offer.get("number", 0))

        self._clear_linked_words()
        for word_ref in ex.get("words", []):
            word_id = word_ref.get("id")
            if word_id is not None:
                entry = self.id_map.get(word_id)
                form = entry.get("entry", {}).get("form", f"ID:{word_id}") if entry else f"ID:{word_id}"
                self._add_linked_word_widget(word_id, form)

        self._set_form_enabled(True)

    def _add_linked_word(self):
        from editor import WordSelectDialog
        dialog = WordSelectDialog(self.dictionary_data, self.search_index, self.id_map, self)
        if dialog.exec() == QDialog.Accepted:
            entry_id, form = dialog.get_selected()
            if entry_id is None:
                return
            for w in self.linked_word_widgets:
                if w.get_id() == entry_id:
                    return
            self._add_linked_word_widget(entry_id, form)

    def _add_linked_word_widget(self, entry_id: int, form: str):
        widget = LinkedWordWidget(entry_id, form, self)
        widget.remove_requested.connect(self._remove_linked_word)
        self.words_container.addWidget(widget)
        self.linked_word_widgets.append(widget)

    def _remove_linked_word(self, widget: LinkedWordWidget):
        self.linked_word_widgets.remove(widget)
        widget.deleteLater()

    def _get_form_data(self) -> Optional[Dict]:
        sentence = self.sentence_input.toPlainText().strip()
        if not sentence:
            QMessageBox.warning(self, "入力エラー", "「文」は必須です。")
            return None
        translation = self.translation_input.toPlainText().strip()
        supplement = self.supplement_input.toPlainText().strip()
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        words = [{"id": w.get_id()} for w in self.linked_word_widgets]
        offer = {
            "catalog": self.offer_catalog_input.text().strip(),
            "number": self.offer_number_spin.value()
        }
        return {
            "sentence": sentence,
            "translation": translation,
            "supplement": supplement,
            "tags": tags,
            "words": words,
            "offer": offer,
        }

    def _save_current(self):
        data = self._get_form_data()
        if data is None:
            return

        if self._editing_new:
            data["id"] = self._new_id
            if "examples" not in self.dictionary_data:
                self.dictionary_data["examples"] = []
            self.dictionary_data["examples"].append(data)
            self._editing_new = False
            self._new_id = None
            self._reload_list()
            # リストの末尾（追加した項目）を選択
            self.example_list.blockSignals(True)
            self.example_list.setCurrentRow(self.example_list.count() - 1)
            self.example_list.blockSignals(False)
            self._on_example_selected(self.example_list.count() - 1)
        else:
            row = self.example_list.currentRow()
            if row < 0 or row >= len(self.filtered_examples):
                return
            ex = self.filtered_examples[row]
            data["id"] = ex["id"]
            examples = self._get_examples()
            for i, e in enumerate(examples):
                if e.get("id") == ex["id"]:
                    examples[i] = data
                    self.filtered_examples[row] = data
                    break
            sentence = data.get("sentence", "")
            display = sentence[:50] + ("…" if len(sentence) > 50 else "")
            self.example_list.currentItem().setText(display)

        self.changed.emit()

    def _delete_current(self):
        row = self.example_list.currentRow()
        if row < 0 or row >= len(self.filtered_examples):
            return

        ex = self.filtered_examples[row]
        sentence = ex.get("sentence", "")
        preview = sentence[:30] + ("…" if len(sentence) > 30 else "")

        reply = QMessageBox.question(
            self,
            "削除確認",
            f"「{preview}」を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        target_id = ex.get("id")
        self.dictionary_data["examples"] = [
            e for e in self._get_examples() if e.get("id") != target_id
        ]
        self._reload_list()
        self.changed.emit()

    def _generate_unique_id(self) -> int:
        examples = self._get_examples()
        if not examples:
            return 1
        return max(e.get("id", 0) for e in examples) + 1

    def _add_new_example(self):
        self._editing_new = True
        self._new_id = self._generate_unique_id()

        self.example_list.blockSignals(True)
        self.example_list.clearSelection()
        self.example_list.setCurrentRow(-1)
        self.example_list.blockSignals(False)

        self._clear_form()
        self.id_label.setText(f"ID: {self._new_id} (新規)")
        self._set_form_enabled(True)
        self.delete_btn.setEnabled(False)
        self.sentence_input.setFocus()
