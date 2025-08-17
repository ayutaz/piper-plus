"""
カスタム辞書モジュール
技術用語や固有名詞の読みを管理し、テキスト前処理を行う
"""

import json
import re
from pathlib import Path


class CustomDictionary:
    """カスタム辞書クラス"""

    def __init__(self, dict_paths: str | list[str] | None = None):
        """
        Args:
            dict_paths: 辞書ファイルのパス（単一または複数）
        """
        self.entries: dict[str, dict[str, str | int]] = {}
        self.case_sensitive_entries: dict[str, dict[str, str | int]] = {}
        self.pattern_cache: dict[str, re.Pattern] = {}

        # デフォルト辞書のパスを設定
        self.default_dict_dir = (
            Path(__file__).parent.parent.parent.parent.parent / "data" / "dictionaries"
        )

        # デフォルト辞書を読み込む
        self._load_default_dictionaries()

        # ユーザー指定の辞書を読み込む
        if dict_paths:
            if isinstance(dict_paths, str):
                dict_paths = [dict_paths]
            for path in dict_paths:
                self.load_dictionary(path)

    def _load_default_dictionaries(self):
        """デフォルト辞書を読み込む"""
        default_dicts = [
            "default_tech_dict.json",
            "default_common_dict.json",
            "additional_tech_dict.json",  # 最新トレンドの技術用語
        ]

        for dict_name in default_dicts:
            dict_path = self.default_dict_dir / dict_name
            if dict_path.exists():
                try:
                    self.load_dictionary(str(dict_path))
                except Exception as e:
                    print(
                        f"Warning: Failed to load default dictionary {dict_path}: {e}"
                    )

    def load_dictionary(self, dict_path: str) -> None:
        """辞書ファイルを読み込む

        Args:
            dict_path: 辞書ファイルのパス
        """
        path = Path(dict_path)
        if not path.exists():
            raise FileNotFoundError(f"Dictionary file not found: {dict_path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # バージョンチェック
        version = data.get("version", "1.0")

        if version == "1.0":
            # 旧形式（単純な key: value）
            entries = data.get("entries", {})
            for word, pronunciation in entries.items():
                if isinstance(pronunciation, str):
                    entry = {"pronunciation": pronunciation, "priority": 5}
                else:
                    entry = pronunciation
                self._add_entry(word, entry)

        elif version == "2.0":
            # 新形式（詳細情報付き）
            entries = data.get("entries", {})
            for word, entry in entries.items():
                # コメント行をスキップ
                if word.startswith("//"):
                    continue

                if isinstance(entry, str):
                    # 互換性のため文字列も受け入れる
                    entry = {"pronunciation": entry, "priority": 5}
                elif isinstance(entry, dict):
                    # priorityがない場合はデフォルト値を設定
                    if "priority" not in entry:
                        entry["priority"] = 5

                self._add_entry(word, entry)

    def _add_entry(self, word: str, entry: dict[str, str | int]) -> None:
        """エントリを辞書に追加

        Args:
            word: 単語
            entry: エントリ情報（pronunciation, priority等）
        """
        # 大文字小文字を区別するケースをチェック
        if word != word.lower() and word != word.upper():
            # 混在している場合は大文字小文字を区別
            self.case_sensitive_entries[word] = entry
        else:
            # 全て大文字または小文字の場合は正規化
            normalized_word = word.lower()

            # 既存エントリとの優先度比較
            if normalized_word in self.entries:
                existing_priority = self.entries[normalized_word].get("priority", 0)
                new_priority = entry.get("priority", 0)
                if new_priority <= existing_priority:
                    return  # 既存の方が優先度が高い

            self.entries[normalized_word] = entry

    def apply_to_text(self, text: str) -> str:
        """テキストに辞書を適用して単語を置換

        Args:
            text: 入力テキスト

        Returns:
            置換後のテキスト
        """
        # まず大文字小文字を区別するエントリを処理
        for word, entry in sorted(
            self.case_sensitive_entries.items(), key=lambda x: len(x[0]), reverse=True
        ):
            pronunciation = entry["pronunciation"]
            # 単語境界を考慮した置換
            pattern = self._get_word_pattern(word, case_sensitive=True)
            text = pattern.sub(pronunciation, text)

        # 次に大文字小文字を区別しないエントリを処理
        for word, entry in sorted(
            self.entries.items(), key=lambda x: len(x[0]), reverse=True
        ):
            pronunciation = entry["pronunciation"]
            # 単語境界を考慮した置換
            pattern = self._get_word_pattern(word, case_sensitive=False)
            text = pattern.sub(pronunciation, text)

        return text

    def _get_word_pattern(self, word: str, case_sensitive: bool = False) -> re.Pattern:
        """単語の正規表現パターンを取得（キャッシュ付き）

        Args:
            word: 単語
            case_sensitive: 大文字小文字を区別するか

        Returns:
            コンパイル済み正規表現パターン
        """
        cache_key = f"{word}_{case_sensitive}"
        if cache_key not in self.pattern_cache:
            escaped_word = re.escape(word)

            # 日本語の場合は単語境界を使わない（\bは日本語で機能しない）
            # 最初の1文字だけチェックすることで高速化
            has_japanese = bool(word) and ord(word[0]) > 127

            # より確実にするため、全文字チェックが必要な場合のみ実行
            if not has_japanese and len(word) > 1:
                has_japanese = any(ord(c) > 127 for c in word[1:])

            if has_japanese:
                # 日本語を含む場合はそのまま置換
                pattern_str = escaped_word
            else:
                # 英語の場合は単語境界を使用
                pattern_str = r"\b" + escaped_word + r"\b"

            flags = 0 if case_sensitive else re.IGNORECASE
            self.pattern_cache[cache_key] = re.compile(pattern_str, flags)

        return self.pattern_cache[cache_key]

    def get_pronunciation(self, word: str) -> str | None:
        """単語の読みを取得

        Args:
            word: 単語

        Returns:
            読み（カタカナ）、見つからない場合はNone
        """
        # まず大文字小文字を区別してチェック
        if word in self.case_sensitive_entries:
            return self.case_sensitive_entries[word]["pronunciation"]

        # 次に正規化してチェック
        normalized_word = word.lower()
        if normalized_word in self.entries:
            return self.entries[normalized_word]["pronunciation"]

        return None

    def add_word(self, word: str, pronunciation: str, priority: int = 5) -> None:
        """単語を動的に追加

        Args:
            word: 単語
            pronunciation: 読み（カタカナ）
            priority: 優先度（0-10、大きいほど優先）
        """
        entry = {"pronunciation": pronunciation, "priority": priority}
        self._add_entry(word, entry)

        # パターンキャッシュをクリア（再構築のため）
        self.pattern_cache.clear()

    def remove_word(self, word: str) -> bool:
        """単語を削除

        Args:
            word: 単語

        Returns:
            削除に成功した場合True
        """
        removed = False

        if word in self.case_sensitive_entries:
            del self.case_sensitive_entries[word]
            removed = True

        normalized_word = word.lower()
        if normalized_word in self.entries:
            del self.entries[normalized_word]
            removed = True

        if removed:
            # パターンキャッシュをクリア
            self.pattern_cache.clear()

        return removed

    def save_dictionary(self, output_path: str) -> None:
        """辞書を保存

        Args:
            output_path: 出力ファイルパス
        """
        # すべてのエントリを統合
        all_entries = {}

        # 大文字小文字を区別しないエントリ
        for word, entry in self.entries.items():
            all_entries[word] = entry

        # 大文字小文字を区別するエントリ
        for word, entry in self.case_sensitive_entries.items():
            all_entries[word] = entry

        # 保存用データ構造
        data = {
            "version": "2.0",
            "description": "Custom dictionary exported from Piper",
            "metadata": {
                "created": "auto-generated",
                "author": "Piper",
                "license": "MIT",
            },
            "entries": all_entries,
        }

        # ファイルに保存
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_stats(self) -> dict[str, int]:
        """辞書の統計情報を取得

        Returns:
            統計情報の辞書
        """
        return {
            "total_entries": len(self.entries) + len(self.case_sensitive_entries),
            "case_insensitive_entries": len(self.entries),
            "case_sensitive_entries": len(self.case_sensitive_entries),
        }


# 便利な関数
def create_default_dictionary() -> CustomDictionary:
    """デフォルト設定の辞書を作成"""
    return CustomDictionary()


def apply_custom_dictionary(
    text: str, dict_paths: str | list[str] | None = None
) -> str:
    """テキストにカスタム辞書を適用（ワンライナー用）

    Args:
        text: 入力テキスト
        dict_paths: 辞書ファイルのパス

    Returns:
        置換後のテキスト
    """
    dictionary = CustomDictionary(dict_paths)
    return dictionary.apply_to_text(text)
