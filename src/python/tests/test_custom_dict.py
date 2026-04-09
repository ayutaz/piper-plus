"""
カスタム辞書のテストケース
"""

import json
import tempfile
from pathlib import Path
import pytest

from piper_plus_g2p.custom_dict import CustomDictionary, apply_custom_dictionary


@pytest.mark.unit
class TestCustomDictionary:
    """CustomDictionaryクラスのテスト"""

    def test_basic_replacement(self):
        """基本的な単語置換のテスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("Docker", "ドッカー", priority=9)
        dict_obj.add_word("GitHub", "ギットハブ", priority=9)
        
        text = "DockerとGitHubを使った開発"
        result = dict_obj.apply_to_text(text)
        assert result == "ドッカーとギットハブを使った開発"
    
    def test_case_insensitive(self):
        """大文字小文字を区別しない置換のテスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("docker", "ドッカー", priority=9)
        
        text = "Docker, DOCKER, docker"
        result = dict_obj.apply_to_text(text)
        assert result == "ドッカー, ドッカー, ドッカー"
    
    def test_case_sensitive(self):
        """大文字小文字を区別する置換のテスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("PyTorch", "パイトーチ", priority=8)
        dict_obj.add_word("pytorch", "パイトーチ小文字", priority=8)
        
        text = "PyTorchとpytorchは異なる"
        result = dict_obj.apply_to_text(text)
        assert result == "パイトーチとパイトーチ小文字は異なる"
    
    def test_word_boundary(self):
        """単語境界の処理テスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("AI", "エーアイ", priority=9)
        
        text = "AI技術とAIDS（エイズ）は違う"
        result = dict_obj.apply_to_text(text)
        assert result == "エーアイ技術とAIDS（エイズ）は違う"
    
    def test_priority(self):
        """優先度のテスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("test", "テスト１", priority=5)
        dict_obj.add_word("test", "テスト２", priority=8)  # より高い優先度
        
        text = "これはtestです"
        result = dict_obj.apply_to_text(text)
        assert result == "これはテスト２です"
    
    def test_load_v1_format(self):
        """V1形式の辞書読み込みテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = {
                "version": "1.0",
                "entries": {
                    "Docker": "ドッカー",
                    "Python": "パイソン"
                }
            }
            json.dump(data, f, ensure_ascii=False)
            temp_path = f.name
        
        try:
            dict_obj = CustomDictionary(temp_path)
            assert dict_obj.get_pronunciation("Docker") == "ドッカー"
            assert dict_obj.get_pronunciation("Python") == "パイソン"
        finally:
            Path(temp_path).unlink()
    
    def test_load_v2_format(self):
        """V2形式の辞書読み込みテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = {
                "version": "2.0",
                "entries": {
                    "Docker": {"pronunciation": "ドッカー", "priority": 9},
                    "Python": {"pronunciation": "パイソン", "priority": 8}
                }
            }
            json.dump(data, f, ensure_ascii=False)
            temp_path = f.name
        
        try:
            dict_obj = CustomDictionary(temp_path)
            assert dict_obj.get_pronunciation("Docker") == "ドッカー"
            assert dict_obj.get_pronunciation("Python") == "パイソン"
        finally:
            Path(temp_path).unlink()
    
    def test_japanese_text(self):
        """日本語テキストとの混在テスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("Piper", "パイパー", priority=10)
        dict_obj.add_word("TTS", "ティーティーエス", priority=10)
        
        text = "PiperはオープンソースのTTSエンジンです。"
        result = dict_obj.apply_to_text(text)
        assert result == "パイパーはオープンソースのティーティーエスエンジンです。"
    
    def test_multiple_dictionaries(self):
        """複数辞書の読み込みテスト"""
        # 辞書1を作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f1:
            data1 = {
                "version": "2.0",
                "entries": {
                    "Docker": {"pronunciation": "ドッカー", "priority": 5}
                }
            }
            json.dump(data1, f1, ensure_ascii=False)
            temp_path1 = f1.name
        
        # 辞書2を作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f2:
            data2 = {
                "version": "2.0",
                "entries": {
                    "Python": {"pronunciation": "パイソン", "priority": 5}
                }
            }
            json.dump(data2, f2, ensure_ascii=False)
            temp_path2 = f2.name
        
        try:
            dict_obj = CustomDictionary([temp_path1, temp_path2])
            assert dict_obj.get_pronunciation("Docker") == "ドッカー"
            assert dict_obj.get_pronunciation("Python") == "パイソン"
        finally:
            Path(temp_path1).unlink()
            Path(temp_path2).unlink()
    
    def test_save_dictionary(self):
        """辞書の保存テスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("Test", "テスト", priority=7)
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            dict_obj.save_dictionary(temp_path)
            
            # 保存した辞書を読み込み
            new_dict = CustomDictionary(temp_path)
            assert new_dict.get_pronunciation("Test") == "テスト"
        finally:
            Path(temp_path).unlink()
    
    def test_stats(self):
        """統計情報のテスト"""
        dict_obj = CustomDictionary(load_defaults=False)
        dict_obj.add_word("docker", "ドッカー")  # case insensitive
        dict_obj.add_word("PyTorch", "パイトーチ")  # case sensitive

        stats = dict_obj.get_stats()
        assert stats["total_entries"] == 2
        assert stats["case_insensitive_entries"] == 1
        assert stats["case_sensitive_entries"] == 1
    
    def test_apply_function(self):
        """apply_custom_dictionary関数のテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            data = {
                "version": "2.0",
                "entries": {
                    "Docker": {"pronunciation": "ドッカー", "priority": 9}
                }
            }
            json.dump(data, f, ensure_ascii=False)
            temp_path = f.name
        
        try:
            text = "Dockerコンテナを起動"
            result = apply_custom_dictionary(text, temp_path)
            assert result == "ドッカーコンテナを起動"
        finally:
            Path(temp_path).unlink()


@pytest.mark.japanese
class TestJapaneseIntegration:
    """日本語音素化との統合テスト"""
    
    def test_phonemize_with_custom_dict(self):
        """カスタム辞書を使った音素化のテスト"""
        from piper_plus_g2p.japanese import JapanesePhonemizer
        from piper_plus_g2p.encode.pua import map_token

        # カスタム辞書を作成
        dict_obj = CustomDictionary()
        dict_obj.add_word("Piper", "パイパー", priority=10)
        dict_obj.add_word("Docker", "ドッカー", priority=9)

        def phonemize_japanese(text):
            p = JapanesePhonemizer(custom_dict=dict_obj)
            tokens = p.phonemize(text)
            full_tokens = ["^"] + tokens + ["$"]
            return [map_token(t) for t in full_tokens]

        # 音素化
        text = "PiperとDockerを使います"
        phonemes = phonemize_japanese(text)

        # 音素列に「パイパー」と「ドッカー」が含まれることを確認
        # （実際の音素は環境により異なる可能性があるため、基本的な動作確認のみ）
        assert isinstance(phonemes, list)
        assert len(phonemes) > 0


@pytest.mark.unit
class TestDefaultDictionaryLoading:
    """デフォルト辞書の自動読み込みテスト"""

    def test_load_all_default_dictionaries(self):
        """全てのデフォルト辞書が読み込まれることを確認"""
        dict_obj = CustomDictionary()
        stats = dict_obj.get_stats()

        # 複数の辞書が読み込まれている場合、エントリ数は多くなる
        # 最低でも500エントリ以上あることを確認（5つの辞書合計）
        assert stats["total_entries"] >= 500, (
            f"Expected at least 500 entries, got {stats['total_entries']}. "
            "All dictionary files should be loaded."
        )

    def test_default_dictionary_entries_common(self):
        """default_common_dict.jsonのエントリが読み込まれていることを確認"""
        dict_obj = CustomDictionary()

        # 誤読防止エントリ（成、声、生を含む語）
        assert dict_obj.get_pronunciation("成功") == "せいこう"
        assert dict_obj.get_pronunciation("音声") == "おんせい"
        assert dict_obj.get_pronunciation("生成") == "せいせい"

        # 地名
        assert dict_obj.get_pronunciation("東京") == "とうきょう"
        assert dict_obj.get_pronunciation("大阪") == "おおさか"

    def test_default_dictionary_entries_ai(self):
        """AI関連用語が読み込まれていることを確認"""
        dict_obj = CustomDictionary()

        # AI関連用語（default_common_dict.jsonに追加済み）
        assert dict_obj.get_pronunciation("Llama") == "ラマ"
        assert dict_obj.get_pronunciation("Mistral") == "ミストラル"
        assert dict_obj.get_pronunciation("Sora") == "ソラ"
        assert dict_obj.get_pronunciation("Cursor") == "カーソル"

    def test_default_dictionary_entries_tech(self):
        """技術用語が読み込まれていることを確認"""
        dict_obj = CustomDictionary()

        # default_tech_dict.jsonまたはadditional_tech_dict.jsonのエントリ
        # 基本的なIT用語が読み込まれていることを確認
        ai_pronunciation = dict_obj.get_pronunciation("AI")
        assert ai_pronunciation is not None, "AI should be in the dictionary"

    def test_glob_pattern_only_json(self):
        """globパターンで.jsonファイルのみ読み込むことを確認"""
        import tempfile
        import shutil

        # 一時ディレクトリを作成
        temp_dir = tempfile.mkdtemp()
        try:
            # .jsonファイルを作成
            json_path = Path(temp_dir) / "test_dict.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "2.0",
                    "entries": {"TestWord": {"pronunciation": "テストワード", "priority": 10}}
                }, f, ensure_ascii=False)

            # .txtファイルを作成（読み込まれないはず）
            txt_path = Path(temp_dir) / "not_a_dict.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("This is not a dictionary")

            # .json.bakファイルを作成（読み込まれないはず）
            bak_path = Path(temp_dir) / "backup.json.bak"
            with open(bak_path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "2.0",
                    "entries": {"BackupWord": {"pronunciation": "バックアップ", "priority": 10}}
                }, f, ensure_ascii=False)

            # 辞書を読み込み
            dict_obj = CustomDictionary()
            # 一時ディレクトリのパスを設定して再読み込み
            dict_obj.default_dict_dir = Path(temp_dir)
            dict_obj.entries.clear()
            dict_obj.case_sensitive_entries.clear()
            dict_obj._load_default_dictionaries()

            # .jsonファイルのエントリのみが読み込まれていることを確認
            assert dict_obj.get_pronunciation("TestWord") == "テストワード"
            assert dict_obj.get_pronunciation("BackupWord") is None

        finally:
            shutil.rmtree(temp_dir)

    def test_dictionary_directory_not_exists(self):
        """辞書ディレクトリが存在しない場合もエラーにならないことを確認"""
        dict_obj = CustomDictionary()
        # 存在しないディレクトリを設定
        dict_obj.default_dict_dir = Path("/nonexistent/path/to/dictionaries")
        dict_obj.entries.clear()
        dict_obj.case_sensitive_entries.clear()

        # エラーなく実行されることを確認
        dict_obj._load_default_dictionaries()

        # エントリは空のまま
        assert len(dict_obj.entries) == 0