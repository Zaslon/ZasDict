"""
ZasDict - 検索の別プロセス実行

検索を別プロセスで実行することで、Python の GIL の影響を受けずに
メインプロセス（UI）の応答性を保つ。

- 子プロセス: 自前の index / id_map を保持し、検索ジョブを処理して
  「ソート済みの word_id リスト」だけを返す（エントリ本体は転送しない）。
- メインプロセス: SearchClient が子プロセスへジョブを投げ、結果受信用の
  軽量スレッド（res_q.get() でブロック）経由で Qt シグナルとして受け取る。
"""

import re
import queue
import multiprocessing

from PySide6.QtCore import QObject, QThread, Signal

from func import TextProcessor


# ============================================================================
# 検索ロジック（子プロセス側）
# ============================================================================

def _normalize_for_search(ignored_re, text):
    """ignoredPattern にマッチする部分を削除"""
    return ignored_re.sub("", text)


def _match(forms, keyword, mode, ignored_re):
    """マッチング判定"""
    if mode == "部分":
        text = " ".join(forms)
        return all(k in text for k in keyword.split())
    elif mode == "前方":
        return any(_normalize_for_search(ignored_re, f).startswith(keyword) for f in forms)
    elif mode == "後方":
        return any(_normalize_for_search(ignored_re, f).endswith(keyword) for f in forms)
    elif mode == "完全":
        return keyword in forms
    return False


def _search_headword_translation(id_map, keyword, mode, ignored_re):
    """見出し語・訳語での検索"""
    results = set()
    for entry in id_map.values():
        word_id = entry["entry"]["id"]
        forms = [entry["entry"]["form"].lower()]
        for translation in entry.get("translations", []):
            forms.extend([f.lower() for f in translation.get("forms", []) if f])
        if _match(forms, keyword, mode, ignored_re):
            results.add(word_id)
    return results


def _search_fulltext(index, keyword, mode, ignored_re):
    """全文検索"""
    results = set()
    for key, ids in index.items():
        if _match([key], keyword, mode, ignored_re):
            results.update(ids)
    return results


def _run_search(index, id_map, ignored_re, mode, scope, text):
    """検索を実行し、ソート済みの word_id リストを返す"""
    keyword = text.lower()
    if scope == "見出し語・訳語":
        result_ids = _search_headword_translation(id_map, keyword, mode, ignored_re)
    else:
        result_ids = _search_fulltext(index, keyword, mode, ignored_re)

    entries = [id_map[i] for i in result_ids if i in id_map]
    entries = TextProcessor.sort_entries(entries)
    return [e["entry"]["id"] for e in entries]


def _compile_ignored_re(dictionary_data):
    """ignoredPattern を事前コンパイル（失敗時は何もマッチしないパターン）"""
    try:
        pattern = dictionary_data["zpdicOnline"]["ignoredPattern"]
        return re.compile(pattern)
    except (KeyError, TypeError, re.error):
        return re.compile(r"(?!)")  # 何にもマッチしない


def search_worker_loop(req_q, res_q, index, id_map, dictionary_data):
    """子プロセスのメインループ

    req_q から受け取るメッセージ:
      - None                                : 終了
      - ("update", index, id_map)           : インデックス更新
      - ("search", job_id, mode, scope, text): 検索
    """
    ignored_re = _compile_ignored_re(dictionary_data)

    while True:
        # ブロック待ち（別プロセスなので GIL とは無関係）
        first = req_q.get()

        # 溜まっているメッセージをまとめて取り出し、検索は最新のものだけ処理（コアレッシング）
        batch = [first]
        while True:
            try:
                batch.append(req_q.get_nowait())
            except queue.Empty:
                break

        pending_search = None
        stop = False
        for msg in batch:
            if msg is None:
                stop = True
            elif msg[0] == "update":
                index, id_map = msg[1], msg[2]
            elif msg[0] == "search":
                pending_search = msg  # 後勝ち（中間のキーストロークはスキップ）

        if pending_search is not None:
            _, job_id, mode, scope, text = pending_search
            try:
                ids = _run_search(index, id_map, ignored_re, mode, scope, text)
            except Exception:
                ids = []
            res_q.put((job_id, ids))

        if stop:
            break


# ============================================================================
# メインプロセス側のブリッジ
# ============================================================================

class _ResultReader(QThread):
    """res_q をブロック待ちし、結果を Qt シグナルとして中継する軽量スレッド"""

    received = Signal(int, object)

    def __init__(self, res_q, parent=None):
        super().__init__(parent)
        self._res_q = res_q

    def run(self):
        while True:
            item = self._res_q.get()
            if item is None:  # 停止サイン
                break
            job_id, ids = item
            self.received.emit(job_id, ids)


class SearchClient(QObject):
    """検索子プロセスを管理し、結果を finished シグナルで通知する"""

    finished = Signal(int, object)  # (job_id, word_id のリスト)

    def __init__(self, index, id_map, dictionary_data, parent=None):
        super().__init__(parent)
        self._req_q = multiprocessing.Queue()
        self._res_q = multiprocessing.Queue()
        self._proc = multiprocessing.Process(
            target=search_worker_loop,
            args=(self._req_q, self._res_q, index, id_map, dictionary_data),
            daemon=True,
        )
        self._reader = _ResultReader(self._res_q)
        self._reader.received.connect(self.finished)

    def start(self):
        self._proc.start()
        self._reader.start()

    def run_search(self, job_id, mode, scope, text):
        """検索ジョブを投入（即時・非ブロッキング）"""
        self._req_q.put(("search", job_id, mode, scope, text))

    def update_index(self, index, id_map):
        """子プロセスのインデックスを更新（編集・再読み込み時）"""
        self._req_q.put(("update", index, id_map))

    def shutdown(self):
        """子プロセスと受信スレッドを停止"""
        try:
            self._req_q.put(None)
        except Exception:
            pass

        if self._proc.is_alive():
            self._proc.join(timeout=2)
            if self._proc.is_alive():
                self._proc.terminate()

        # 受信スレッドを起こして終了させる
        try:
            self._res_q.put(None)
        except Exception:
            pass
        self._reader.wait(2000)
