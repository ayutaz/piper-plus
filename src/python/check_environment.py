#!/usr/bin/env python3
"""Check if the environment has correct unvoiced vowel support."""

import sys


try:
    from piper_plus_g2p.japanese import JapanesePhonemizer
    from piper_plus_g2p.encode.pua import map_token
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map, _JAPANESE_PHONEMES as JAPANESE_PHONEMES

    def get_japanese_id_map():
        return get_phoneme_id_map("ja")

    def phonemize_japanese(text):
        p = JapanesePhonemizer()
        tokens = p.phonemize(text)
        return [map_token(t) for t in ["^"] + tokens + ["$"]]

    print("=== 環境チェック ===")
    print(f"Python: {sys.executable}")
    print(f"PYTHONPATH: {':'.join(sys.path[:3])}")

    # Check jp_id_map
    id_map = get_japanese_id_map()
    print(f"\n音素数: {len(id_map)}")
    print(f"無声化母音サポート: {'A' in JAPANESE_PHONEMES}")

    # Check actual mapping
    unvoiced = [p for p in JAPANESE_PHONEMES if p in "AIUEO"]
    print(f"無声化母音: {unvoiced}")

    # Test phonemization
    test_text = "です"
    phonemes = phonemize_japanese(test_text)
    print(f"\nテスト: '{test_text}' → {phonemes}")
    print(f"無声化母音を保持: {any(p in 'AIUEO' for p in phonemes)}")

    # Show what preprocess would create
    print("\n=== preprocess.pyが作成するconfig.json ===")
    print(f"num_symbols: {len(id_map)}")
    print("phoneme_id_map (無声化母音部分):")
    for vowel in "aiueoAIUEO":
        if vowel in id_map:
            print(f"  '{vowel}': {id_map[vowel]}")

except Exception as e:
    print(f"エラー: {e}")
    print("piper_trainモジュールが見つかりません")
