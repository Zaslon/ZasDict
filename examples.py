"""
ZasDict - 例文ビューア・エディタ
"""

import os
import json
import http.client
import ssl
import urllib.parse

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit, QPlainTextEdit, QLabel, QPushButton, QSpinBox,
    QScrollArea, QDialog, QMessageBox, QApplication, QComboBox,
    QLayout, QSizePolicy, QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt, Signal, QThread, QRect, QSize, QPoint, QEvent
from PySide6.QtGui import QFontMetrics
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


class AutoResizingTextEdit(QPlainTextEdit):
    """内容に合わせて高さが自動伸縮するテキスト入力欄"""

    def __init__(self, min_lines=1, max_lines=None, parent=None):
        super().__init__(parent)
        self._min_lines = min_lines
        self._max_lines = max_lines
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._adjust_height)

    def _adjust_height(self):
        m = self.contentsMargins()
        fw = self.frameWidth()
        lh = int(self.fontMetrics().height() * 1.4)
        overhead = m.top() + m.bottom() + fw * 2
        min_h = self._min_lines * lh + overhead

        # QPlainTextEdit の document().size().height() はブロック数を返すため
        # block.layout().lineCount() で折り返しを含む実際の視覚的行数を数える
        line_count = 0
        block = self.document().begin()
        while block.isValid():
            layout = block.layout()
            lc = layout.lineCount() if layout and layout.lineCount() > 0 else 1
            line_count += lc
            block = block.next()

        doc_h = line_count * lh + overhead
        h = max(doc_h, min_h)
        if self._max_lines is not None:
            max_h = self._max_lines * lh + overhead
            h = min(h, max_h)
            self.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded if doc_h > max_h
                else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        self.setFixedHeight(h)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._adjust_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._adjust_height()


class FlowLayout(QLayout):
    """横に並べて折り返すレイアウト"""

    def __init__(self, parent=None, h_spacing=6, v_spacing=4):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0

        for item in self._items:
            iw = item.sizeHint().width()
            ih = item.sizeHint().height()
            if x + iw > right and line_height > 0:
                x = rect.x() + m.left()
                y += line_height + self._v_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += iw + self._h_spacing
            line_height = max(line_height, ih)

        return y + line_height - rect.y() + m.bottom()


class LinkedWordWidget(QWidget):
    """関連単語の表示・削除ウィジェット"""

    remove_requested = Signal(object)
    word_link_clicked = Signal(int)

    def __init__(self, entry_id: int, form: str, parent=None):
        super().__init__(parent)
        self.entry_id = entry_id

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QPushButton(form)
        self.label.setFlat(True)
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setStyleSheet("text-decoration: underline; text-align: left; padding: 0px;")
        self.label.clicked.connect(lambda: self.word_link_clicked.emit(self.entry_id))
        remove_btn = QPushButton("－")
        remove_btn.setMaximumWidth(30)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))

        layout.addWidget(self.label)
        layout.addWidget(remove_btn)
        self.setLayout(layout)

    def get_id(self) -> int:
        return self.entry_id


class ExampleEditDialog(QDialog):
    """例文編集ダイアログ（ポップアップ）"""

    saved = Signal(dict)
    deleted = Signal()
    show_word_requested = Signal(int)

    def __init__(self, dictionary_data: Dict, search_index: Dict, id_map: Dict,
                 sentence_font=None, example: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.sentence_font = sentence_font
        self.example = example
        self._is_new = (example is None)
        self.linked_word_widgets: List[LinkedWordWidget] = []
        self._fetch_thread: Optional[OnlineFetchThread] = None

        self.setWindowTitle("例文を追加" if self._is_new else "例文を編集")
        self.resize(620, 520)
        self._build_ui()
        if not self._is_new:
            self._populate_form(example)

    def _build_ui(self):
        outer_layout = QVBoxLayout()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        form_layout = QVBoxLayout()
        scroll_content.setLayout(form_layout)
        scroll.setWidget(scroll_content)

        self.id_label = QLabel("ID: -" if self._is_new else f"ID: {self.example.get('id', '-')}")
        form_layout.addWidget(self.id_label)

        form_layout.addWidget(QLabel("文:"))
        self.sentence_input = AutoResizingTextEdit(1)
        self.sentence_input.setPlaceholderText("例文を入力...")
        self.sentence_input.setTabChangesFocus(True)
        if self.sentence_font:
            self.sentence_input.setFont(self.sentence_font)
        form_layout.addWidget(self.sentence_input)

        form_layout.addWidget(QLabel("訳:"))
        self.translation_input = AutoResizingTextEdit(1)
        self.translation_input.setPlaceholderText("翻訳を入力...")
        self.translation_input.setTabChangesFocus(True)
        form_layout.addWidget(self.translation_input)

        form_layout.addWidget(QLabel("補足:"))
        self.supplement_input = AutoResizingTextEdit(1)
        self.supplement_input.setPlaceholderText("補足情報（任意）")
        self.supplement_input.setTabChangesFocus(True)
        form_layout.addWidget(self.supplement_input)

        form_layout.addWidget(QLabel("タグ（,区切り）:"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("例: 挨拶,日常")
        form_layout.addWidget(self.tags_input)

        form_layout.addWidget(QLabel("関連単語:"))
        self.words_widget = QWidget()
        self.words_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.words_container = FlowLayout(self.words_widget, h_spacing=6, v_spacing=4)
        form_layout.addWidget(self.words_widget)
        add_word_btn = QPushButton("＋ 単語を追加")
        add_word_btn.clicked.connect(self._add_linked_word)
        form_layout.addWidget(add_word_btn)

        # 出典セクション
        offer_row = QHBoxLayout()
        offer_row.addWidget(QLabel("出典:"))
        self.offer_catalog_combo = QComboBox()
        self.offer_catalog_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.offer_catalog_combo.setMinimumContentsLength(20)
        for _, display in const.EXAMPLE_CATALOG_OPTIONS:
            self.offer_catalog_combo.addItem(display)
        self.offer_catalog_combo.currentIndexChanged.connect(self._on_offer_catalog_changed)
        offer_row.addWidget(self.offer_catalog_combo)
        offer_row.addWidget(QLabel("No."))
        self.offer_number_spin = QSpinBox()
        self.offer_number_spin.setRange(0, 999999)
        offer_row.addWidget(self.offer_number_spin)
        self.offer_fetch_btn = QPushButton("照会")
        is_online = (self._current_catalog_api() != const.EXAMPLE_CATALOG_SELF)
        self.offer_fetch_btn.setEnabled(is_online)
        self.offer_fetch_btn.clicked.connect(self._fetch_offer_example)
        offer_row.addWidget(self.offer_fetch_btn)
        form_layout.addLayout(offer_row)

        # 照会ステータス行
        status_row = QHBoxLayout()
        self.offer_status_label = QLabel("")
        self.offer_status_label.setWordWrap(True)
        status_row.addWidget(self.offer_status_label, 1)
        api_key_btn = QPushButton("APIキー設定")
        # api_key_btn.setFixedWidth(90)
        api_key_btn.clicked.connect(self._change_api_key)
        status_row.addWidget(api_key_btn)
        form_layout.addLayout(status_row)

        form_layout.addStretch()

        outer_layout.addWidget(scroll)

        # ボタン行
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        self.delete_btn = QPushButton("削除")
        self.delete_btn.setEnabled(not self._is_new)
        self.delete_btn.setVisible(not self._is_new)
        self.delete_btn.clicked.connect(self._on_delete)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(cancel_btn)
        outer_layout.addLayout(btn_layout)

        self.setLayout(outer_layout)

    def _populate_form(self, example: Dict):
        self.id_label.setText(f"ID: {example.get('id', '-')}")
        self.sentence_input.setPlainText(example.get("sentence", ""))
        self.translation_input.setPlainText(example.get("translation", ""))
        self.supplement_input.setPlainText(example.get("supplement", ""))
        self.tags_input.setText(", ".join(example.get("tags", [])))

        offer = example.get("offer", {})
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
        for word_ref in example.get("words", []):
            word_id = word_ref.get("id")
            if word_id is not None:
                entry = self.id_map.get(word_id)
                form = entry.get("entry", {}).get("form", f"ID:{word_id}") if entry else f"ID:{word_id}"
                self._add_linked_word_widget(word_id, form)

    def get_form_data(self) -> Optional[Dict]:
        sentence = self.sentence_input.toPlainText().strip()
        if not sentence:
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

    def _on_save(self):
        data = self.get_form_data()
        if data is None:
            QMessageBox.warning(self, "入力エラー", "「文」は必須です。")
            return
        self.saved.emit(data)
        self.close()

    def _on_delete(self):
        sentence = (self.example or {}).get("sentence", "")
        preview = sentence[:30] + ("…" if len(sentence) > 30 else "")
        reply = QMessageBox.question(
            self, "削除確認",
            f"「{preview}」を削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit()
            self.close()

    # ----------------------------------------------------------------
    # カタログ名ヘルパー
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
        self.offer_fetch_btn.setEnabled(is_online)
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
        self.offer_fetch_btn.setEnabled(is_online)

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
    # 関連単語
    # ----------------------------------------------------------------

    def _clear_linked_words(self):
        for w in self.linked_word_widgets:
            w.deleteLater()
        self.linked_word_widgets.clear()

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
        widget.word_link_clicked.connect(self.show_word_requested)
        self.words_container.addWidget(widget)
        self.linked_word_widgets.append(widget)

    def _remove_linked_word(self, widget: LinkedWordWidget):
        self.linked_word_widgets.remove(widget)
        widget.deleteLater()


class TwoLineExampleDelegate(QStyledItemDelegate):
    """文と訳語を2行1組で描画するデリゲート"""

    def __init__(self, sentence_font=None, parent=None):
        super().__init__(parent)
        self._sentence_font = sentence_font

    def sizeHint(self, option, _index):
        fm1 = QFontMetrics(self._sentence_font if self._sentence_font else option.font)
        fm2 = QFontMetrics(option.font)
        return QSize(option.rect.width(), fm1.height() + fm2.height() + 10)

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        painter.save()

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if is_selected:
            painter.fillRect(option.rect, option.palette.highlight())
            main_color = option.palette.highlightedText().color()
            sub_color = main_color
        else:
            main_color = option.palette.text().color()
            sub_color = option.palette.placeholderText().color()

        sentence = index.data(Qt.ItemDataRole.DisplayRole) or ""
        translation = index.data(Qt.ItemDataRole.UserRole) or ""

        pad = 4
        x = option.rect.x() + pad
        w = option.rect.width() - pad * 2

        font1 = self._sentence_font if self._sentence_font else option.font
        painter.setFont(font1)
        fm1 = QFontMetrics(font1)
        y1 = option.rect.y() + pad
        painter.setPen(main_color)
        painter.drawText(x, y1, w, fm1.height(), Qt.AlignmentFlag.AlignLeft, sentence)

        painter.setFont(option.font)
        fm2 = QFontMetrics(option.font)
        y2 = y1 + fm1.height() + 2
        painter.setPen(sub_color)
        painter.drawText(x, y2, w, fm2.height(), Qt.AlignmentFlag.AlignLeft, translation)

        painter.restore()


class ExamplesViewerWidget(QWidget):
    """例文ビューア（閲覧専用リスト）"""

    changed = Signal()
    show_word_in_dict = Signal(int)

    def __init__(self, dictionary_data: Dict, search_index: Dict, id_map: Dict,
                 sentence_font=None, parent=None):
        super().__init__(parent)
        self.dictionary_data = dictionary_data
        self.search_index = search_index
        self.id_map = id_map
        self.sentence_font = sentence_font
        self.filtered_examples: List[Dict] = []
        self._open_dialogs: set = set()

        self.setWindowTitle("例文")
        self.resize(500, 520)
        self._build_ui()
        self._reload_list()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("例文・訳を検索...")
        self.search_input.textChanged.connect(lambda _: self._reload_list())
        main_layout.addWidget(self.search_input)

        self.example_list = QListWidget()
        self.example_list.itemDoubleClicked.connect(lambda _: self._on_example_activate())
        self.example_list.installEventFilter(self)
        self.example_list.setItemDelegate(TwoLineExampleDelegate(self.sentence_font, self.example_list))
        main_layout.addWidget(self.example_list)

        add_btn = QPushButton("＋ 例文を追加")
        add_btn.clicked.connect(self._add_new_example)
        main_layout.addWidget(add_btn)

        self.setLayout(main_layout)

    def eventFilter(self, obj, event):
        if obj == self.example_list and event.type() == QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and
                    event.modifiers() == Qt.KeyboardModifier.ControlModifier):
                self._on_example_activate()
                return True
        return super().eventFilter(obj, event)

    # ----------------------------------------------------------------
    # リスト操作
    # ----------------------------------------------------------------

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

        self.example_list.clear()
        for ex in self.filtered_examples:
            sentence = ex.get("sentence", "")
            translation = ex.get("translation", "")
            sentence_disp = sentence[:50] + ("…" if len(sentence) > 50 else "")
            translation_disp = translation[:50] + ("…" if len(translation) > 50 else "")
            item = QListWidgetItem(sentence_disp)
            item.setData(Qt.ItemDataRole.UserRole, translation_disp)
            self.example_list.addItem(item)

    # ----------------------------------------------------------------
    # 編集ダイアログ
    # ----------------------------------------------------------------

    def _on_example_activate(self):
        row = self.example_list.currentRow()
        if row < 0 or row >= len(self.filtered_examples):
            return
        self._open_edit_dialog(self.filtered_examples[row], row)

    def _open_edit_dialog(self, example: Dict, row: int):
        dialog = ExampleEditDialog(
            self.dictionary_data, self.search_index, self.id_map,
            sentence_font=self.sentence_font,
            example=example,
            parent=self
        )

        def on_saved(data):
            data["id"] = example["id"]
            examples = self._get_examples()
            for i, e in enumerate(examples):
                if e.get("id") == example["id"]:
                    examples[i] = data
                    if row < len(self.filtered_examples):
                        self.filtered_examples[row] = data
                    break
            sentence = data.get("sentence", "")
            translation = data.get("translation", "")
            sentence_disp = sentence[:50] + ("…" if len(sentence) > 50 else "")
            translation_disp = translation[:50] + ("…" if len(translation) > 50 else "")
            item = self.example_list.item(row)
            if item:
                item.setText(sentence_disp)
                item.setData(Qt.ItemDataRole.UserRole, translation_disp)
            self.changed.emit()

        def on_deleted():
            target_id = example.get("id")
            self.dictionary_data["examples"] = [
                e for e in self._get_examples() if e.get("id") != target_id
            ]
            self._reload_list()
            self.changed.emit()

        dialog.saved.connect(on_saved)
        dialog.deleted.connect(on_deleted)
        dialog.show_word_requested.connect(self.show_word_in_dict)
        dialog.finished.connect(lambda _: self._open_dialogs.discard(dialog))
        self._open_dialogs.add(dialog)
        dialog.show()

    def _add_new_example(self):
        new_id = self._generate_unique_id()
        dialog = ExampleEditDialog(
            self.dictionary_data, self.search_index, self.id_map,
            sentence_font=self.sentence_font,
            example=None,
            parent=self
        )

        def on_saved(data):
            data["id"] = new_id
            if "examples" not in self.dictionary_data:
                self.dictionary_data["examples"] = []
            self.dictionary_data["examples"].append(data)
            self._reload_list()
            self.example_list.setCurrentRow(self.example_list.count() - 1)
            self.changed.emit()

        dialog.saved.connect(on_saved)
        dialog.finished.connect(lambda _: self._open_dialogs.discard(dialog))
        self._open_dialogs.add(dialog)
        dialog.show()

    def _generate_unique_id(self) -> int:
        examples = self._get_examples()
        if not examples:
            return 1
        return max(e.get("id", 0) for e in examples) + 1
