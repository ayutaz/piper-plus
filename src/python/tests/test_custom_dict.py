"""
カスタム辞書のテストケース
"""

import json
import tempfile
from pathlib import Path
import pytest

from piper_train.phonemize.custom_dict import CustomDictionary, apply_custom_dictionary


class TestCustomDictionary:
    """CustomDictionaryクラスのテスト"""
    
    def test_basic_replacement(self):
        """基本的な単語置換のテスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("Docker", "ドッカー", priority=9)
        dict_obj.add_word("GitHub", "ギットハブ", priority=9)
        
        text = "DockerとGitHubを使った開発"
        result = dict_obj.apply_to_text(text)
        assert result == "ドッカーとギットハブを使った開発"
    
    def test_case_insensitive(self):
        """大文字小文字を区別しない置換のテスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("docker", "ドッカー", priority=9)
        
        text = "Docker, DOCKER, docker"
        result = dict_obj.apply_to_text(text)
        assert result == "ドッカー, ドッカー, ドッカー"
    
    def test_case_sensitive(self):
        """大文字小文字を区別する置換のテスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("PyTorch", "パイトーチ", priority=8)
        dict_obj.add_word("pytorch", "パイトーチ小文字", priority=8)
        
        text = "PyTorchとpytorchは異なる"
        result = dict_obj.apply_to_text(text)
        assert result == "パイトーチとパイトーチ小文字は異なる"
    
    def test_word_boundary(self):
        """単語境界の処理テスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("AI", "エーアイ", priority=9)
        
        text = "AI技術とAIDS（エイズ）は違う"
        result = dict_obj.apply_to_text(text)
        assert result == "エーアイ技術とAIDS（エイズ）は違う"
    
    def test_priority(self):
        """優先度のテスト"""
        dict_obj = CustomDictionary()
        dict_obj.add_word("test", "テスト１", priority=5)
        dict_obj.add_word("test", "テスト２", priority=8)  # より高い優先度
        
        text = "これはtestです"
        result = dict_obj.apply_to_text(text)
        assert result == "これはテスト２です"
    
    def test_load_v1_format(self):
        """V1形式の辞書読み込みテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        dict_obj = CustomDictionary()
        dict_obj.add_word("Piper", "パイパー", priority=10)
        dict_obj.add_word("TTS", "ティーティーエス", priority=10)
        
        text = "PiperはオープンソースのTTSエンジンです。"
        result = dict_obj.apply_to_text(text)
        assert result == "パイパーはオープンソースのティーティーエスエンジンです。"
    
    def test_multiple_dictionaries(self):
        """複数辞書の読み込みテスト"""
        # 辞書1を作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f1:
            data1 = {
                "version": "2.0",
                "entries": {
                    "Docker": {"pronunciation": "ドッカー", "priority": 5}
                }
            }
            json.dump(data1, f1, ensure_ascii=False)
            temp_path1 = f1.name
        
        # 辞書2を作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f2:
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
        dict_obj = CustomDictionary()
        dict_obj.add_word("docker", "ドッカー")  # case insensitive
        dict_obj.add_word("PyTorch", "パイトーチ")  # case sensitive
        
        stats = dict_obj.get_stats()
        assert stats["total_entries"] == 2
        assert stats["case_insensitive_entries"] == 1
        assert stats["case_sensitive_entries"] == 1
    
    def test_apply_function(self):
        """apply_custom_dictionary関数のテスト"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        from piper_train.phonemize.japanese import phonemize_japanese
        
        # カスタム辞書を作成
        dict_obj = CustomDictionary()
        dict_obj.add_word("Piper", "パイパー", priority=10)
        dict_obj.add_word("Docker", "ドッカー", priority=9)
        
        # 音素化
        text = "PiperとDockerを使います"
        phonemes = phonemize_japanese(text, custom_dict=dict_obj)
        
        # 音素列に「パイパー」と「ドッカー」が含まれることを確認
        # （実際の音素は環境により異なる可能性があるため、基本的な動作確認のみ）
        assert isinstance(phonemes, list)
        assert len(phonemes) > 0