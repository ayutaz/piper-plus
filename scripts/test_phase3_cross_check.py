#!/usr/bin/env python3
"""Phase 3クロスチェック: 学習時と推論時の実装が同一の出力を生成することを確認"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

# Import training module (add piper_train parent to path)
train_phonemize_path = project_root / "src" / "python" / "piper_train" / "phonemize"
sys.path.insert(0, str(train_phonemize_path.parent.parent))

try:
    from piper_train.phonemize.japanese import phonemize_japanese as train_phonemize
    TRAIN_AVAILABLE = True
    TRAIN_ERROR = None
except Exception as e:
    TRAIN_AVAILABLE = False
    TRAIN_ERROR = str(e)
    train_phonemize = None

# Import inference module (add piper parent to path, but import as phonemize.*)
# This avoids triggering piper/__init__.py which requires onnxruntime
infer_phonemize_path = project_root / "src" / "python_run" / "piper" / "phonemize"
sys.path.insert(0, str(infer_phonemize_path.parent))

try:
    # Import from phonemize.* (not piper.phonemize.*) to avoid piper/__init__.py
    from phonemize.japanese import phonemize_japanese as infer_phonemize
    from phonemize.japanese import HAS_PYOPENJTALK as INFER_HAS_PYOPENJTALK
    INFER_AVAILABLE = True
    INFER_ERROR = None
except Exception as e:
    INFER_AVAILABLE = False
    INFER_ERROR = str(e)
    infer_phonemize = None
    INFER_HAS_PYOPENJTALK = False


def test_cross_check():
    """学習時と推論時の実装が同一の出力を生成することを確認"""
    print("=" * 70)
    print("Phase 3 クロスチェック: 学習時・推論時実装の同一性検証")
    print("=" * 70)

    # Check module availability
    if not TRAIN_AVAILABLE:
        print(f"\n⚠️  学習時モジュールのインポートに失敗しました: {TRAIN_ERROR}")
        return False
    if not INFER_AVAILABLE:
        print(f"\n⚠️  推論時モジュールのインポートに失敗しました: {INFER_ERROR}")
        return False
    if not INFER_HAS_PYOPENJTALK:
        print("\n⚠️  推論時モジュールでpyopenjtalkが利用できません")
        return False

    print("\n✓ 両モジュールが正常にインポートされました\n")

    # Test sentences covering various prosody features
    test_cases = [
        "今日は良い天気です。",
        "こんにちは。お元気ですか？",
        "桜が咲きました。春ですね。",
        "これはテストです。",
        "雨が降っています。",
        "明日は晴れるでしょう。",
    ]

    passed = 0
    failed = 0

    for i, text in enumerate(test_cases, 1):
        print(f"テストケース {i}: {text}")
        try:
            # Phonemize with both implementations
            # Note: Training version doesn't have prosody parameter (always True)
            # Inference version has prosody=True as default
            train_tokens = train_phonemize(text)
            infer_tokens = infer_phonemize(text, prosody=True)

            # Compare results
            if train_tokens == infer_tokens:
                print(f"  ✓ 一致 (トークン数: {len(train_tokens)})")
                passed += 1
            else:
                print(f"  ❌ 不一致")
                print(f"     学習時トークン数: {len(train_tokens)}")
                print(f"     推論時トークン数: {len(infer_tokens)}")

                # Show first difference
                min_len = min(len(train_tokens), len(infer_tokens))
                for idx in range(min_len):
                    if train_tokens[idx] != infer_tokens[idx]:
                        print(f"     最初の相違点 (index {idx}):")
                        print(f"       学習時: {repr(train_tokens[idx])}")
                        print(f"       推論時: {repr(infer_tokens[idx])}")
                        break
                else:
                    if len(train_tokens) != len(infer_tokens):
                        print(f"     トークン長が異なります")

                failed += 1

        except Exception as e:
            print(f"  ❌ エラー: {e}")
            failed += 1

        print()

    # Summary
    print("=" * 70)
    print("クロスチェック結果")
    print("=" * 70)
    print(f"成功: {passed}/{len(test_cases)}")
    print(f"失敗: {failed}/{len(test_cases)}")

    if failed == 0:
        print("\n🎉 すべてのテストケースで学習時・推論時実装が一致しました！")
        print("   Phase 3の実装同期は完全です。")
        return True
    else:
        print(f"\n⚠️  {failed}個のテストケースで不一致がありました")
        return False


def main():
    """Run cross-check test"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 12 + "Phase 3 学習時・推論時実装クロスチェック" + " " * 16 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    try:
        if test_cross_check():
            return 0
        else:
            return 1
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
