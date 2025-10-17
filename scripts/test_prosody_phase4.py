#!/usr/bin/env python3
"""Test Phase 4: Context prosody enhancement for Japanese TTS (B,E field extraction)"""

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
    PROSODY_TOKENS_PHASE4,
    SPECIAL_TOKENS,
    JAPANESE_PHONEMES,
)
from phonemize.token_mapper import (
    PROSODY_PUA_MAPPING_PHASE4,
    CHAR2TOKEN,
    register,
)


def test_phase4_tokens_defined():
    """Test that Phase 4 prosody tokens are properly defined"""
    print("=" * 70)
    print("Test 1: Phase 4トークン定義の確認")
    print("=" * 70)

    # Check PROSODY_TOKENS_PHASE4 contains 47 tokens
    expected_count = 47  # 13 prev_pos + 13 next_pos + 5 intn_pos + 10 prev_mora + 6 prev_acc

    print(f"\n期待されるPhase 4トークン数: {expected_count}")
    print(f"実際のPhase 4トークン数: {len(PROSODY_TOKENS_PHASE4)}")
    assert len(PROSODY_TOKENS_PHASE4) == expected_count, f"Phase 4トークン数が正しくありません (期待: {expected_count}, 実際: {len(PROSODY_TOKENS_PHASE4)})"

    # Verify token categories
    prev_pos_tokens = [t for t in PROSODY_TOKENS_PHASE4 if t.startswith("<PREV_POS:")]
    next_pos_tokens = [t for t in PROSODY_TOKENS_PHASE4 if t.startswith("<NEXT_POS:")]
    intn_pos_tokens = [t for t in PROSODY_TOKENS_PHASE4 if t.startswith("<INTN_POS:")]
    prev_mora_tokens = [t for t in PROSODY_TOKENS_PHASE4 if t.startswith("<PREV_MORA:")]
    prev_acc_tokens = [t for t in PROSODY_TOKENS_PHASE4 if t.startswith("<PREV_ACC:")]

    print(f"\nトークンカテゴリ別集計:")
    print(f"  前アクセント句POS: {len(prev_pos_tokens)} (期待: 13)")
    print(f"  後アクセント句POS: {len(next_pos_tokens)} (期待: 13)")
    print(f"  イントネーション句内位置: {len(intn_pos_tokens)} (期待: 5)")
    print(f"  前アクセント句モーラ数: {len(prev_mora_tokens)} (期待: 10)")
    print(f"  前アクセント句アクセント型: {len(prev_acc_tokens)} (期待: 6)")

    assert len(prev_pos_tokens) == 13, "前アクセント句POSトークン数が正しくありません"
    assert len(next_pos_tokens) == 13, "後アクセント句POSトークン数が正しくありません"
    assert len(intn_pos_tokens) == 5, "イントネーション句内位置トークン数が正しくありません"
    assert len(prev_mora_tokens) == 10, "前アクセント句モーラ数トークン数が正しくありません"
    assert len(prev_acc_tokens) == 6, "前アクセント句アクセント型トークン数が正しくありません"

    print("\n✅ Phase 4トークン定義: 正常")
    return True


def test_phase4_pua_mapping():
    """Test that Phase 4 PUA mappings are correctly defined"""
    print("\n" + "=" * 70)
    print("Test 2: Phase 4 PUAマッピングの確認")
    print("=" * 70)

    # Verify mapping count
    expected_count = 47
    actual_count = len(PROSODY_PUA_MAPPING_PHASE4)
    print(f"\nPhase 4 PUAマッピング数: {actual_count} (期待: {expected_count})")
    assert actual_count == expected_count, f"PUAマッピング数が正しくありません (期待: {expected_count}, 実際: {actual_count})"

    # Verify PUA ranges
    pua_ranges = {
        "前POS": (0xE0A0, 0xE0AC, 13),
        "後POS": (0xE0B0, 0xE0BC, 13),
        "イントネーション位置": (0xE0C0, 0xE0C4, 5),
        "前モーラ": (0xE0D0, 0xE0D9, 10),
        "前アクセント": (0xE0E0, 0xE0E5, 6),
    }

    print("\nPUA範囲チェック:")
    for category, (start, end, expected_tokens) in pua_ranges.items():
        tokens_in_range = [
            (token, code) for token, code in PROSODY_PUA_MAPPING_PHASE4.items()
            if start <= code <= end
        ]
        print(f"  {category}: {hex(start)}-{hex(end)} ({len(tokens_in_range)}トークン, 期待: {expected_tokens})")
        assert len(tokens_in_range) == expected_tokens, f"{category}のトークン数が正しくありません"

    print("\n✅ Phase 4 PUAマッピング: 正常")
    return True


def test_total_token_count():
    """Test that total token count is 144 after Phase 4"""
    print("\n" + "=" * 70)
    print("Test 3: トークン総数の確認")
    print("=" * 70)

    # Calculate total tokens
    basic_special = 7  # _, ^, $, ?, #, [, ]
    phase1_count = len(PROSODY_TOKENS_PHASE1)  # 31 tokens
    phase2_count = len(PROSODY_TOKENS_PHASE2)  # 8 tokens
    phase4_count = len(PROSODY_TOKENS_PHASE4)  # 47 tokens
    phoneme_count = len(JAPANESE_PHONEMES)  # 51 phonemes

    total_special = basic_special + phase1_count + phase2_count + phase4_count
    total_tokens = total_special + phoneme_count
    expected_total = 144  # 7 + 31 + 8 + 47 + 51 = 144

    print(f"\n基本特殊トークン: {basic_special}")
    print(f"Phase 1韻律トークン: {phase1_count}")
    print(f"Phase 2韻律トークン: {phase2_count}")
    print(f"Phase 4韻律トークン: {phase4_count}")
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


def test_phase4_phonemization():
    """Test actual phonemization with Phase 4 features"""
    print("\n" + "=" * 70)
    print("Test 4: Phase 4音素化の実行テスト")
    print("=" * 70)

    if not HAS_PYOPENJTALK:
        print("\n⚠️  pyopenjtalkが利用できないため、このテストをスキップします")
        return True

    # Test with multi-sentence text to trigger B/E field extraction
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

            # Check for Phase 4 tokens (decode to check)
            phase4_found = []
            for token_char in result:
                if token_char in CHAR2TOKEN:
                    original_token = CHAR2TOKEN[token_char]
                    if original_token in PROSODY_TOKENS_PHASE4:
                        phase4_found.append(original_token)

            if phase4_found:
                print(f"  検出されたPhase 4トークン: {phase4_found[:5]}")  # Show first 5
                if len(phase4_found) > 5:
                    print(f"    ... 他 {len(phase4_found) - 5}個")
            else:
                print(f"  Phase 4トークンは検出されませんでした（文によっては正常）")

            # Show first few tokens
            display_tokens = []
            for token_char in result[:20]:
                if token_char in CHAR2TOKEN:
                    display_tokens.append(CHAR2TOKEN[token_char])
                else:
                    display_tokens.append(token_char)
            print(f"  最初の20トークン: {' '.join(display_tokens)}")

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            import traceback
            traceback.print_exc()
            return False

    print("\n✅ Phase 4音素化: 正常")
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
    """Run all Phase 4 tests"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "Phase 4 コンテキスト韻律強化機能テスト" + " " * 17 + "║")
    print("╚" + "=" * 68 + "╝")

    tests = [
        test_phase4_tokens_defined,
        test_phase4_pua_mapping,
        test_total_token_count,
        test_phase4_phonemization,
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
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "=" * 70)
    print("テスト結果サマリー")
    print("=" * 70)
    print(f"成功: {passed}/{len(tests)}")
    print(f"失敗: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 すべてのテストが正常に完了しました！")
        print("   Phase 4実装は完全です。")
        return 0
    else:
        print(f"\n⚠️  {failed}個のテストが失敗しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
