"""
ZasDict - 辞書検索アプリケーション
内部処理
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

# ============================================================================
# ソート・前処理ユーティリティ
# ============================================================================

class TextProcessor:
    """テキストの前処理とソート用のユーティリティクラス"""
    
    ORDER_MAP = {ch: i for i, ch in enumerate(const.CUSTOM_ORDER)}
    
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