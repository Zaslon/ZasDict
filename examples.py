"""
ZasDict - 例文ビューア・エディタ
"""

import os
import json
import http.client
import ssl
import urllib.parse

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QLineEdit, QPlainTextEdit, QLabel, QPushButton, QSpinBox,
    QScrollArea, QDialog, QMessageBox, QApplication, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread
from typing import Dict, List, Optional

import const

# APIキーの保存先（プロジェクト外のユーザーホームディレクトリ）
_API_KEY_PATH = os.path.join(os.path.expanduser("~"), ".zasdict", "api_key")


def _load_api_key() -> Optional[str]:
    try:
        with open(_API_KEY_PATH, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips BOM
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def _save_api_key(key: str):
    os.makedirs(os.path.dirname(_API_KEY_PATH), exist_ok=True)
    with open(_API_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key)


class ApiKeyDialog(QDialog):
    """ZpDIC APIキー入力ダイアログ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("APIキーの設定")
        self.resize(440, 160)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("ZpDIC Online のAPIキーを入力してください:"))

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("APIキー")
        layout.addWidget(self.key_input)

        note = QLabel(
            f"保存先: {_API_KEY_PATH}\n"
            "（プロジェクトフォルダ外のため、Git管理外です）"
        )
        note.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(note)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("キャンセル")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_key(self) -> str:
        return self.key_input.text().strip()


class OnlineFetchThread(QThread):
    """ZpDIC例文API照会スレッド"""

    result = Signal(dict)

    def __init__(self, catalog: str, number: int, api_key: str, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.number = number
        self.api_key = api_key

    def run(self):
        # HTTP ヘッダーは latin-1 制限があるため ASCII のみ許可
        if not self.api_key.isascii():
            self.result.emit({"ok": False, "error": "api_key_non_ascii"})
            return

        # カタログ名をパーセントエンコード（非ASCII対策）
        catalog_encoded = urllib.parse.quote(self.catalog, safe="")
        path = f"/api/v0/exampleOffer/{catalog_encoded}/{self.number}"

        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection("zpdic.ziphil.com", context=ctx, timeout=10)
        try:
            conn.request("GET", path, headers={"X-Api-Key": self.api_key})
            resp = conn.getresponse()
            body = resp.read()
            if resp.status == 200:
                data = json.loads(body.decode("utf-8"))
                self.result.emit({"ok": True, "data": data.get("exampleOffer", {})})
            elif resp.status == 400:
                self.result.emit({"ok": False, "error": "bad_request"})
            elif resp.status == 401:
                self.result.emit({"ok": False, "error": "auth_failed"})
            elif resp.status == 404:
                self.result.emit({"ok": False, "error": "not_found"})
            elif resp.status == 429:
                self.result.emit({"ok": False, "error": "rate_limit"})
            else:
                self.result.emit({"ok": False, "error": f"HTTP {resp.status}"})
        except Exception as e:
            self.result.emit({"ok": False, "error": str(e)})
        finally:
            try:
                conn.close()
            except Exception:
                pass


class LinkedWordWidget(QWidget):
    """関連単語の表示・削除ウィジェット"""

    remove_requested = Signal(object)

    def __init__(self, entry_id: int, form: str, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

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
        self._form_enabled = False
        self._fetch_thread: Optional[OnlineFetchThread] = None

        self.setWindowTitle("例文")
        self.resize(820, 520)
        self._build_ui()
        self._reload_list()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        splitter = QSplitter(Qt.Horizontal)

        # ---- 左ペイン: 検索 + リスト ----
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

        # ---- 右ペイン: 編集フォーム ----
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

        # ---- 出典セクション ----
        offer_row = QHBoxLayout()
        offer_row.addWidget(QLabel("出典:"))
        self.offer_catalog_combo = QComboBox()
        for _, display in const.EXAMPLE_CATALOG_OPTIONS:
            self.offer_catalog_combo.addItem(display)
        self.offer_catalog_combo.currentIndexChanged.connect(self._on_offer_catalog_changed)
        offer_row.addWidget(self.offer_catalog_combo)
        offer_row.addWidget(QLabel("No."))
        self.offer_number_spin = QSpinBox()
        self.offer_number_spin.setRange(0, 999999)
        offer_row.addWidget(self.offer_number_spin)
        self.offer_fetch_btn = QPushButton("照会")
        self.offer_fetch_btn.setEnabled(False)
        self.offer_fetch_btn.clicked.connect(self._fetch_offer_example)
        offer_row.addWidget(self.offer_fetch_btn)
        form_layout.addLayout(offer_row)

        # 照会ステータス行
        status_row = QHBoxLayout()
        self.offer_status_label = QLabel("")
        self.offer_status_label.setWordWrap(True)
        status_row.addWidget(self.offer_status_label, 1)
        api_key_btn = QPushButton("APIキー設定")
        api_key_btn.setFixedWidth(90)
        api_key_btn.clicked.connect(self._change_api_key)
        status_row.addWidget(api_key_btn)
        form_layout.addLayout(status_row)

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

    # ----------------------------------------------------------------
    # カタログ名ヘルパー（currentData/findData に頼らずインデックスで解決）
    # ----------------------------------------------------------------

    def _current_catalog_api(self) -> str:
        idx = self.offer_catalog_combo.currentIndex()
        if 0 <= idx < len(const.EXAMPLE_CATALOG_OPTIONS):
            return const.EXAMPLE_CATALOG_OPTIONS[idx][0]
        return const.EXAMPLE_CATALOG_SELF

    def _find_catalog_index(self, api_name: str) -> int:
        for i, (name, _) in enumerate(const.EXAMPLE_CATALOG_OPTIONS):
            if name == api_name:
                return i
        return -1

    # ----------------------------------------------------------------
    # 出典照会
    # ----------------------------------------------------------------

    def _on_offer_catalog_changed(self):
        is_online = (self._current_catalog_api() != const.EXAMPLE_CATALOG_SELF)
        self.offer_fetch_btn.setEnabled(self._form_enabled and is_online)
        self.offer_status_label.setText("")

    def _fetch_offer_example(self):
        api_key = self._get_or_ask_api_key()
        if not api_key:
            return

        number = self.offer_number_spin.value()
        if number == 0:
            self.offer_status_label.setText("番号を入力してください。")
            return

        catalog = self._current_catalog_api()
        self.offer_fetch_btn.setEnabled(False)
        self.offer_status_label.setText("照会中...")

        self._fetch_thread = OnlineFetchThread(catalog, number, api_key, self)
        self._fetch_thread.result.connect(self._on_offer_fetch_result)
        self._fetch_thread.start()

    def _on_offer_fetch_result(self, result: dict):
        is_online = (self._current_catalog_api() != const.EXAMPLE_CATALOG_SELF)
        self.offer_fetch_btn.setEnabled(self._form_enabled and is_online)

        if result["ok"]:
            data = result["data"]
            self.translation_input.setPlainText(data.get("translation", ""))
            self.supplement_input.setPlainText(data.get("supplement", ""))
            author = data.get("author", "")
            self.offer_status_label.setText(
                f"照会成功（作者: {author}）" if author else "照会成功"
            )
        elif result["error"] == "bad_request":
            self.offer_status_label.setText(
                "HTTP 400: リクエストの内容が誤っています。"
            )
        elif result["error"] == "not_found":
            self.offer_status_label.setText(
                f"HTTP 404: No. {self.offer_number_spin.value()} の例文は存在しません。"
            )
            self.offer_number_spin.setValue(0)
        elif result["error"] == "auth_failed":
            self.offer_status_label.setText(
                "HTTP 401: APIキーが正しくありません。「APIキー設定」から再設定してください。"
            )
            try:
                os.remove(_API_KEY_PATH)
            except FileNotFoundError:
                pass
        elif result["error"] == "rate_limit":
            self.offer_status_label.setText(
                "HTTP 429: 呼び出し回数の上限に達しています。"
            )
        elif result["error"] == "api_key_non_ascii":
            self.offer_status_label.setText(
                "APIキーに使用できない文字が含まれています。「APIキー設定」から再設定してください。"
            )
            try:
                os.remove(_API_KEY_PATH)
            except FileNotFoundError:
                pass
        else:
            self.offer_status_label.setText(f"エラー: {result['error']}")

    def _get_or_ask_api_key(self) -> Optional[str]:
        key = _load_api_key()
        if key:
            return key
        dialog = ApiKeyDialog(self)
        if dialog.exec() == QDialog.Accepted:
            key = dialog.get_key()
            if key:
                _save_api_key(key)
                return key
        return None

    def _change_api_key(self):
        dialog = ApiKeyDialog(self)
        if dialog.exec() == QDialog.Accepted:
            key = dialog.get_key()
            if key:
                _save_api_key(key)

    # ----------------------------------------------------------------
    # フォーム操作
    # ----------------------------------------------------------------

    def _set_form_enabled(self, enabled: bool):
        self._form_enabled = enabled
        self.sentence_input.setEnabled(enabled)
        self.translation_input.setEnabled(enabled)
        self.supplement_input.setEnabled(enabled)
        self.tags_input.setEnabled(enabled)
        self.offer_catalog_combo.setEnabled(enabled)
        self.offer_number_spin.setEnabled(enabled)
        is_online = (self._current_catalog_api() != const.EXAMPLE_CATALOG_SELF)
        self.offer_fetch_btn.setEnabled(enabled and is_online)
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
        idx = self._find_catalog_index(const.EXAMPLE_CATALOG_SELF)
        self.offer_catalog_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.offer_number_spin.setValue(0)
        self.offer_status_label.setText("")
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
        catalog = offer.get("catalog", "")
        idx = self._find_catalog_index(catalog)
        if idx >= 0:
            self.offer_catalog_combo.setCurrentIndex(idx)
        else:
            idx = self._find_catalog_index(const.EXAMPLE_CATALOG_SELF)
            self.offer_catalog_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.offer_number_spin.setValue(offer.get("number", 0))
        self.offer_status_label.setText("")

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
            "catalog": self._current_catalog_api(),
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
