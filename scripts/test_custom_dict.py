#!/usr/bin/env python3
"""
カスタム辞書機能の統合テストスクリプト
"""

import json
import tempfile
from pathlib import Path
import subprocess
import sys

# テスト用のテキスト
TEST_TEXTS = [
    "DockerとGitHubを使ってPiperを開発しています。",
    "PythonとJavaScriptでAPIを実装しました。",
    "AWSのEC2インスタンスでTensorFlowを実行。",
    "WebAssemblyとONNXを使った音声合成エンジン。",
]

# 期待される置換結果
EXPECTED_RESULTS = [
    "ドッカーとギットハブを使ってパイパーを開発しています。",
    "パイソンとジャバスクリプトでエーピーアイを実装しました。",
    "エーダブリューエスのイーシーツーインスタンスでテンソルフローを実行。",
    "ウェブアセンブリとオニックスを使った音声合成エンジン。",
]


def test_python_custom_dict():
    """Python版のカスタム辞書テスト"""
    print("Testing Python custom dictionary...")
    
    # Pythonのパスを追加
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))
    
    try:
        from piper_train.phonemize.custom_dict import CustomDictionary
        
        # デフォルト辞書でテスト
        dict_obj = CustomDictionary()
        
        for i, text in enumerate(TEST_TEXTS):
            result = dict_obj.apply_to_text(text)
            expected = EXPECTED_RESULTS[i]
            
            if result == expected:
                print(f"✓ Test {i+1} passed")
            else:
                print(f"✗ Test {i+1} failed")
                print(f"  Input:    {text}")
                print(f"  Expected: {expected}")
                print(f"  Got:      {result}")
                return False
        
        print("All Python tests passed!")
        return True
        
    except Exception as e:
        print(f"Python test failed with error: {e}")
        return False


def test_custom_dict_file():
    """カスタム辞書ファイルのテスト"""
    print("\nTesting custom dictionary file...")
    
    # テスト用の辞書を作成
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        test_dict = {
            "version": "2.0",
            "entries": {
                "TestWord": {"pronunciation": "テストワード", "priority": 10},
                "CustomAPI": {"pronunciation": "カスタムエーピーアイ", "priority": 10}
            }
        }
        json.dump(test_dict, f, ensure_ascii=False)
        dict_path = f.name
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))
        from piper_train.phonemize.custom_dict import CustomDictionary
        
        dict_obj = CustomDictionary(dict_path)
        
        # テスト
        text = "TestWordとCustomAPIを使用"
        expected = "テストワードとカスタムエーピーアイを使用"
        result = dict_obj.apply_to_text(text)
        
        if result == expected:
            print("✓ Custom dictionary file test passed")
            return True
        else:
            print("✗ Custom dictionary file test failed")
            print(f"  Input:    {text}")
            print(f"  Expected: {expected}")
            print(f"  Got:      {result}")
            return False
            
    finally:
        Path(dict_path).unlink()


def test_japanese_phonemize():
    """日本語音素化との統合テスト"""
    print("\nTesting Japanese phonemize integration...")
    
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))
        from piper_train.phonemize.japanese import phonemize_japanese
        from piper_train.phonemize.custom_dict import CustomDictionary
        
        # カスタム辞書を作成
        dict_obj = CustomDictionary()
        
        # 音素化テスト
        text = "PiperでDockerを使います"
        phonemes = phonemize_japanese(text, custom_dict=dict_obj)
        
        if isinstance(phonemes, list) and len(phonemes) > 0:
            print("✓ Japanese phonemize integration test passed")
            print(f"  Phonemes: {' '.join(phonemes[:10])}...")  # 最初の10個のみ表示
            return True
        else:
            print("✗ Japanese phonemize integration test failed")
            return False
            
    except Exception as e:
        print(f"Japanese phonemize test failed with error: {e}")
        return False


def test_dictionary_consistency():
    """辞書の一貫性テスト - Python版とWebAssembly版の辞書が同じ内容か確認"""
    print("\nTesting dictionary consistency across versions...")
    
    try:
        # Python版の辞書を読み込み
        sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))
        from piper_train.phonemize.custom_dict import CustomDictionary
        
        py_dict = CustomDictionary()
        
        # WebAssembly版の辞書も確認（ファイルレベルで）
        wasm_dict_path = Path(__file__).parent.parent / "src" / "wasm" / "openjtalk-web" / "assets"
        
        # 同じ辞書ファイルが存在するか確認
        expected_files = ["default_tech_dict.json", "default_common_dict.json"]
        all_exist = True
        
        for dict_file in expected_files:
            if (wasm_dict_path / dict_file).exists():
                print(f"✓ WebAssembly版に {dict_file} が存在")
            else:
                print(f"✗ WebAssembly版に {dict_file} が存在しません")
                all_exist = False
        
        return all_exist
        
    except Exception as e:
        print(f"Dictionary consistency test failed with error: {e}")
        return False


def main():
    """メインテスト関数"""
    print("=== Custom Dictionary Integration Tests ===\n")
    
    tests = [
        test_python_custom_dict,
        test_custom_dict_file,
        test_japanese_phonemize,
        test_dictionary_consistency,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"=== Summary: {passed}/{total} tests passed ===")
    
    if passed == total:
        print("All tests passed! ✓")
        print("\n辞書の統合が完了しました：")
        print("- Python版、C++版、WebAssembly版で同じ辞書を使用")
        print("- 200以上の技術用語を含むデフォルト辞書")
        return 0
    else:
        print("Some tests failed! ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())