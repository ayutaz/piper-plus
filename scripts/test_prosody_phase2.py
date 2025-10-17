#!/usr/bin/env python3
"""Test Phase 2: Sentence-level prosody enhancement for Japanese TTS"""

import sys
from pathlib import Path

# Add src/python_run/piper to path for direct phonemize imports
phonemize_path = Path(__file__).parent.parent / "src" / "python_run" / "piper" / "phonemize"
sys.path.insert(0, str(phonemize_path.parent))

# Direct imports from phonemize modules
from phonemize.japanese import phonemize_japanese, HAS_PYOPENJTALK
from phonemize.jp_id_map import (
    get_japanese_id_map,
    PROSODY_TOKENS_PHASE1,
    PROSODY_TOKENS_PHASE2,
    SPECIAL_TOKENS,
    JAPANESE_PHONEMES,
)
from phonemize.token_mapper import (
    PROSODY_PUA_MAPPING_PHASE2,
    CHAR2TOKEN,
    register,
)


def test_phase2_tokens_defined():
    """Test that Phase 2 prosody tokens are properly defined"""
    print("=" * 70)
    print("Test 1: Phase 2トークン定義の確認")
    print("=" * 70)

    # Check PROSODY_TOKENS_PHASE2 contains 8 tokens
    expected_tokens = [
        "<IP:1>",
        "<IP:2>",
        "<IP:3>",
        "<IP:4>",
        "<IP:5+>",
        "<BG:1/1>",
        "<BG:1/2>",
        "<BG:2/2>",
    ]

    print(f"\n期待されるPhase 2トークン数: {len(expected_tokens)}")
    print(f"実際のPhase 2トークン数: {len(PROSODY_TOKENS_PHASE2)}")
    assert len(PROSODY_TOKENS_PHASE2) == 8, "Phase 2トークン数が正しくありません"

    for token in expected_tokens:
        assert (
            token in PROSODY_TOKENS_PHASE2
        ), f"トークン {token} がPROSODY_TOKENS_PHASE2に含まれていません"
        print(f"  ✓ {token}")

    print("\n✅ Phase 2トークン定義: 正常")
    return True


def test_phase2_pua_mapping():
    """Test that Phase 2 PUA mappings are correctly defined"""
    print("\n" + "=" * 70)
    print("Test 2: Phase 2 PUAマッピングの確認")
    print("=" * 70)

    expected_mappings = {
        "<IP:1>": 0xE070,
        "<IP:2>": 0xE071,
        "<IP:3>": 0xE072,
        "<IP:4>": 0xE073,
        "<IP:5+>": 0xE074,
        "<BG:1/1>": 0xE080,
        "<BG:1/2>": 0xE081,
        "<BG:2/2>": 0xE082,
    }

    print(f"\nPhase 2 PUAマッピング:")
    for token, expected_code in expected_mappings.items():
        assert (
            token in PROSODY_PUA_MAPPING_PHASE2
        ), f"トークン {token} がマッピングに含まれていません"
        actual_code = PROSODY_PUA_MAPPING_PHASE2[token]
        assert (
            actual_code == expected_code
        ), f"{token}: 期待値 {hex(expected_code)}, 実際 {hex(actual_code)}"
        print(f"  {token:12} → {hex(actual_code)}")

    print("\n✅ Phase 2 PUAマッピング: 正常")
    return True


def test_total_token_count():
    """Test that total token count is 97 after Phase 2"""
    print("\n" + "=" * 70)
    print("Test 3: トークン総数の確認")
    print("=" * 70)

    # Calculate total tokens
    basic_special = 7  # _, ^, $, ?, #, [, ]
    phase1_count = len(PROSODY_TOKENS_PHASE1)  # 31 tokens
    phase2_count = len(PROSODY_TOKENS_PHASE2)  # 8 tokens
    phoneme_count = len(JAPANESE_PHONEMES)  # 51 phonemes

    total_special = basic_special + phase1_count + phase2_count
    total_tokens = total_special + phoneme_count
    expected_total = 97  # 7 + 31 + 8 + 51 = 97

    print(f"\n基本特殊トークン: {basic_special}")
    print(f"Phase 1韻律トークン: {phase1_count}")
    print(f"Phase 2韻律トークン: {phase2_count}")
    print(f"音素トークン: {phoneme_count}")
    print(f"─" * 40)
    print(f"特殊トークン合計: {total_special}")
    print(f"総トークン数: {total_tokens}")

    # Check against ID map
    id_map = get_japanese_id_map()
    actual_count = len(id_map)
    print(f"ID mapの実際のサイズ: {actual_count}")

    assert (
        actual_count == expected_total
    ), f"期待値: {expected_total}トークン, 実際: {actual_count}トークン"

    print(f"\n✅ トークン総数: 正常 ({expected_total}トークン)")
    return True


def test_phase2_phonemization():
    """Test actual phonemization with Phase 2 features"""
    print("\n" + "=" * 70)
    print("Test 4: Phase 2音素化の実行テスト")
    print("=" * 70)

    if not HAS_PYOPENJTALK:
        print("\n⚠️  pyopenjtalkが利用できないため、このテストをスキップします")
        return True

    # Test with multi-sentence text to potentially trigger J/I field extraction
    test_sentences = [
        "今日は良い天気です。",
        "こんにちは。お元気ですか？",
        "桜が咲きました。春ですね。",
    ]

    for i, text in enumerate(test_sentences, 1):
        print(f"\nテスト文 {i}: {text}")
        try:
            result = phonemize_japanese(text, prosody=True)
            print(f"  トークン数: {len(result)}")

            # Check for BOS/EOS
            assert result[0] == "^", "BOSトークンがありません"
            assert result[-1] in ["$", "?"], "EOSトークンがありません"

            # Check for Phase 2 tokens (decode to check)
            phase2_found = []
            for token_char in result:
                if token_char in CHAR2TOKEN:
                    original_token = CHAR2TOKEN[token_char]
                    if original_token in PROSODY_TOKENS_PHASE2:
                        phase2_found.append(original_token)

            if phase2_found:
                print(f"  検出されたPhase 2トークン: {phase2_found}")
            else:
                print(f"  Phase 2トークンは検出されませんでした（文によっては正常）")

            # Show first few tokens
            display_tokens = []
            for token_char in result[:15]:
                if token_char in CHAR2TOKEN:
                    display_tokens.append(CHAR2TOKEN[token_char])
                else:
                    display_tokens.append(token_char)
            print(f"  最初の15トークン: {' '.join(display_tokens)}")

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            return False

    print("\n✅ Phase 2音素化: 正常")
    return True


def test_id_map_uniqueness():
    """Test that all IDs in the map are unique"""
    print("\n" + "=" * 70)
    print("Test 5: IDマップの一意性確認")
    print("=" * 70)

    id_map = get_japanese_id_map()
    all_ids = [v[0] for v in id_map.values()]

    print(f"\nID総数: {len(all_ids)}")
    unique_ids = set(all_ids)
    print(f"ユニークなID数: {len(unique_ids)}")

    assert len(all_ids) == len(
        unique_ids
    ), f"重複したIDが見つかりました（{len(all_ids) - len(unique_ids)}個の重複）"

    # Check that IDs are sequential from 0
    assert all_ids == list(
        range(len(all_ids))
    ), "IDが0から連続していません"

    print("\n✅ IDマップの一意性: 正常")
    return True


def main():
    """Run all Phase 2 tests"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "Phase 2 韻律強化機能テスト" + " " * 25 + "║")
    print("╚" + "=" * 68 + "╝")

    tests = [
        test_phase2_tokens_defined,
        test_phase2_pua_mapping,
        test_total_token_count,
        test_phase2_phonemization,
        test_id_map_uniqueness,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"\n❌ テスト失敗: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ 予期しないエラー: {e}")
            failed += 1

    # Summary
    print("\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    print(f"成功: {passed}/{len(tests)}")
    print(f"失敗: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 すべてのテストが正常に完了しました！")
        return 0
    else:
        print(f"\n⚠️  {failed}個のテストが失敗しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
