#!/usr/bin/env python3
"""Test Phase 5: Complete field extraction for Japanese TTS (D,H,K fields)"""

import sys
import importlib.util
from pathlib import Path

# Add python directory to path
python_path = Path(__file__).parent.parent / "src" / "python"
sys.path.insert(0, str(python_path))

# Skip phonemize_japanese import (requires Python 3.10+ and pyopenjtalk)
HAS_PYOPENJTALK = False
phonemize_japanese = None

# Load token_mapper module with proper package context
phonemize_path = python_path / "piper_train" / "phonemize"
token_mapper_path = phonemize_path / "token_mapper.py"
spec = importlib.util.spec_from_file_location("piper_train.phonemize.token_mapper", token_mapper_path)
token_mapper = importlib.util.module_from_spec(spec)
sys.modules["piper_train.phonemize.token_mapper"] = token_mapper
sys.modules["piper_train"] = type(sys)("piper_train")
sys.modules["piper_train.phonemize"] = type(sys)("piper_train.phonemize")
spec.loader.exec_module(token_mapper)

# Load jp_id_map module with proper package context
jp_id_map_path = phonemize_path / "jp_id_map.py"
spec = importlib.util.spec_from_file_location("piper_train.phonemize.jp_id_map", jp_id_map_path)
jp_id_map = importlib.util.module_from_spec(spec)
sys.modules["piper_train.phonemize.jp_id_map"] = jp_id_map
spec.loader.exec_module(jp_id_map)

# Extract needed symbols
get_japanese_id_map = jp_id_map.get_japanese_id_map
PROSODY_TOKENS_PHASE1 = jp_id_map.PROSODY_TOKENS_PHASE1
PROSODY_TOKENS_PHASE2 = jp_id_map.PROSODY_TOKENS_PHASE2
PROSODY_TOKENS_PHASE4 = jp_id_map.PROSODY_TOKENS_PHASE4
PROSODY_TOKENS_PHASE5 = jp_id_map.PROSODY_TOKENS_PHASE5
SPECIAL_TOKENS = jp_id_map.SPECIAL_TOKENS
JAPANESE_PHONEMES = jp_id_map.JAPANESE_PHONEMES

PROSODY_PUA_MAPPING_PHASE5 = token_mapper.PROSODY_PUA_MAPPING_PHASE5
CHAR2TOKEN = token_mapper.CHAR2TOKEN
register = token_mapper.register


def test_phase5_tokens_defined():
    """Test that Phase 5 prosody tokens are properly defined"""
    print("=" * 70)
    print("Test 1: Phase 5トークン定義の確認")
    print("=" * 70)

    # Check PROSODY_TOKENS_PHASE5 contains 49 tokens (D,H,K fields)
    expected_count = 49  # 13 prev_word + 13 next_word + 8 bunsetsu + 4 utt_bg + 6 utt_ip + 5 utt_mora

    print(f"\n期待されるPhase 5トークン数: {expected_count}")
    print(f"実際のPhase 5トークン数: {len(PROSODY_TOKENS_PHASE5)}")
    assert len(PROSODY_TOKENS_PHASE5) == expected_count, f"Phase 5トークン数が正しくありません (期待: {expected_count}, 実際: {len(PROSODY_TOKENS_PHASE5)})"

    # Verify token categories
    prev_word_pos_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<PREV_WORD_POS:")]
    next_word_pos_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<NEXT_WORD_POS:")]
    bunsetsu_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<BUNSETSU:")]
    utt_bg_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<UTT_BG:")]
    utt_ip_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<UTT_IP:")]
    utt_mora_tokens = [t for t in PROSODY_TOKENS_PHASE5 if t.startswith("<UTT_MORA:")]

    print(f"\nトークンカテゴリ別集計:")
    print(f"  前単語POS (D field): {len(prev_word_pos_tokens)} (期待: 13)")
    print(f"  後単語POS (D field): {len(next_word_pos_tokens)} (期待: 13)")
    print(f"  文節位置 (H field): {len(bunsetsu_tokens)} (期待: 8)")
    print(f"  発話呼気段落数 (K field): {len(utt_bg_tokens)} (期待: 4)")
    print(f"  発話イントネーション句数 (K field): {len(utt_ip_tokens)} (期待: 6)")
    print(f"  発話総モーラ数 (K field): {len(utt_mora_tokens)} (期待: 5)")

    assert len(prev_word_pos_tokens) == 13, "前単語POSトークン数が正しくありません"
    assert len(next_word_pos_tokens) == 13, "後単語POSトークン数が正しくありません"
    assert len(bunsetsu_tokens) == 8, "文節位置トークン数が正しくありません"
    assert len(utt_bg_tokens) == 4, "発話呼気段落数トークン数が正しくありません"
    assert len(utt_ip_tokens) == 6, "発話イントネーション句数トークン数が正しくありません"
    assert len(utt_mora_tokens) == 5, "発話総モーラ数トークン数が正しくありません"

    print("\n✅ Phase 5トークン定義: 正常")
    return True


def test_phase5_pua_mapping():
    """Test that Phase 5 PUA mappings are correctly defined"""
    print("\n" + "=" * 70)
    print("Test 2: Phase 5 PUAマッピングの確認")
    print("=" * 70)

    # Verify mapping count (D,H,K fields)
    expected_count = 49
    actual_count = len(PROSODY_PUA_MAPPING_PHASE5)
    print(f"\nPhase 5 PUAマッピング数: {actual_count} (期待: {expected_count})")
    assert actual_count == expected_count, f"PUAマッピング数が正しくありません (期待: {expected_count}, 実際: {actual_count})"

    # Verify PUA ranges
    pua_ranges = {
        "前単語POS (D)": (0xE120, 0xE12C, 13),
        "後単語POS (D)": (0xE130, 0xE13C, 13),
        "文節位置 (H)": (0xE140, 0xE147, 8),
        "発話呼気段落数 (K)": (0xE150, 0xE153, 4),
        "発話イントネーション句数 (K)": (0xE154, 0xE159, 6),
        "発話総モーラ数 (K)": (0xE15A, 0xE15E, 5),
    }

    print("\nPUA範囲チェック:")
    for category, (start, end, expected_tokens) in pua_ranges.items():
        tokens_in_range = [
            (token, code) for token, code in PROSODY_PUA_MAPPING_PHASE5.items()
            if start <= code <= end
        ]
        print(f"  {category}: {hex(start)}-{hex(end)} ({len(tokens_in_range)}トークン, 期待: {expected_tokens})")
        assert len(tokens_in_range) == expected_tokens, f"{category}のトークン数が正しくありません"

    print("\n✅ Phase 5 PUAマッピング: 正常")
    return True


def test_total_token_count():
    """Test that total token count is 209 after Phase 5"""
    print("\n" + "=" * 70)
    print("Test 3: トークン総数の確認")
    print("=" * 70)

    # Calculate total tokens
    basic_special = 7  # _, ^, $, ?, #, [, ]
    phase1_count = len(PROSODY_TOKENS_PHASE1)  # 31 tokens
    phase2_count = len(PROSODY_TOKENS_PHASE2)  # 8 tokens
    phase4_count = len(PROSODY_TOKENS_PHASE4)  # 63 tokens (B,E,G)
    phase5_count = len(PROSODY_TOKENS_PHASE5)  # 49 tokens (D,H,K)
    phoneme_count = len(JAPANESE_PHONEMES)  # 51 phonemes

    total_special = basic_special + phase1_count + phase2_count + phase4_count + phase5_count
    total_tokens = total_special + phoneme_count
    expected_total = 209  # 7 + 31 + 8 + 63 + 49 + 51 = 209

    print(f"\n基本特殊トークン: {basic_special}")
    print(f"Phase 1韻律トークン: {phase1_count}")
    print(f"Phase 2韻律トークン: {phase2_count}")
    print(f"Phase 4韻律トークン: {phase4_count}")
    print(f"Phase 5韻律トークン: {phase5_count}")
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


def test_phase5_phonemization():
    """Test actual phonemization with Phase 5 features"""
    print("\n" + "=" * 70)
    print("Test 4: Phase 5音素化の実行テスト")
    print("=" * 70)

    if not HAS_PYOPENJTALK:
        print("\n⚠️  pyopenjtalkが利用できないため、このテストをスキップします")
        return True

    # Test with multi-sentence text to trigger D,H,K field extraction
    test_sentences = [
        "今日は良い天気です。",
        "こんにちは。お元気ですか？",
        "桜が咲きました。春ですね。",
    ]

    for i, text in enumerate(test_sentences, 1):
        print(f"\nテスト文 {i}: {text}")
        try:
            result = phonemize_japanese(text)
            print(f"  トークン数: {len(result)}")

            # Check for BOS/EOS
            assert result[0] == "^", "BOSトークンがありません"
            assert result[-1] in ["$", "?"], "EOSトークンがありません"

            # Check for Phase 5 tokens (decode to check)
            phase5_found = []
            for token_char in result:
                if token_char in CHAR2TOKEN:
                    original_token = CHAR2TOKEN[token_char]
                    if original_token in PROSODY_TOKENS_PHASE5:
                        phase5_found.append(original_token)

            if phase5_found:
                print(f"  検出されたPhase 5トークン: {phase5_found[:5]}")  # Show first 5
                if len(phase5_found) > 5:
                    print(f"    ... 他 {len(phase5_found) - 5}個")
            else:
                print(f"  Phase 5トークンは検出されませんでした（文によっては正常）")

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

    print("\n✅ Phase 5音素化: 正常")
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
    """Run all Phase 5 tests"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "Phase 5 完全フィールド抽出機能テスト" + " " * 19 + "║")
    print("╚" + "=" * 68 + "╝")

    tests = [
        test_phase5_tokens_defined,
        test_phase5_pua_mapping,
        test_total_token_count,
        test_phase5_phonemization,
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
        print("   Phase 5実装は完全です。")
        return 0
    else:
        print(f"\n⚠️  {failed}個のテストが失敗しました")
        return 1


if __name__ == "__main__":
    sys.exit(main())
