#!/usr/bin/env python3
"""Phase 5 クロスチェック: 学習時と推論時のファイルが同一であることを確認"""

import sys
import hashlib
from pathlib import Path


def get_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of file contents"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def test_file_identity():
    """学習時と推論時のファイルが完全に同一であることを確認"""
    print("=" * 70)
    print("Phase 5 クロスチェック: ファイル同一性検証")
    print("=" * 70)
    print()

    project_root = Path(__file__).parent.parent

    # Files to check
    files_to_check = [
        ("japanese.py", "phonemize/japanese.py"),
        ("jp_id_map.py", "phonemize/jp_id_map.py"),
        ("token_mapper.py", "phonemize/token_mapper.py"),
    ]

    passed = 0
    failed = 0

    for filename, rel_path in files_to_check:
        print(f"チェック: {filename}")

        train_file = project_root / "src" / "python" / "piper_train" / rel_path
        infer_file = project_root / "src" / "python_run" / "piper" / rel_path

        # Check if files exist
        if not train_file.exists():
            print(f"  ❌ 学習時ファイルが見つかりません: {train_file}")
            failed += 1
            continue

        if not infer_file.exists():
            print(f"  ❌ 推論時ファイルが見つかりません: {infer_file}")
            failed += 1
            continue

        # Calculate hashes
        train_hash = get_file_hash(train_file)
        infer_hash = get_file_hash(infer_file)

        # Compare
        if train_hash == infer_hash:
            print(f"  ✅ 完全一致 (SHA256: {train_hash[:16]}...)")
            passed += 1
        else:
            print(f"  ❌ ハッシュが異なります")
            print(f"     学習時: {train_hash}")
            print(f"     推論時: {infer_hash}")
            failed += 1

        print()

    # Summary
    print("=" * 70)
    print("クロスチェック結果")
    print("=" * 70)
    print(f"成功: {passed}/{len(files_to_check)}")
    print(f"失敗: {failed}/{len(files_to_check)}")

    if failed == 0:
        print("\n🎉 すべてのファイルが学習時・推論時で完全に一致しました！")
        print("   Phase 5の実装同期は完全です。")
        return True
    else:
        print(f"\n⚠️  {failed}個のファイルで不一致がありました")
        return False


def main():
    """Run cross-check test"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "Phase 5 学習時・推論時ファイル同一性チェック" + " " * 13 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    try:
        if test_file_identity():
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
