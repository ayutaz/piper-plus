# Debug Scripts

このディレクトリには、開発・デバッグ用のスクリプトが含まれています。

## ファイル一覧

- `debug_phonemes.py` - OpenJTalkの音素抽出をテストするPythonスクリプト
- `test_openjtalk_phonemes.c` - OpenJTalkラッパー関数をテストするCプログラム
- `test_openjtalk.sh` - OpenJTalkバイナリの動作確認スクリプト
- `rename_models.sh` - CI用のモデルファイル名変更スクリプト

## 使用方法

### debug_phonemes.py
```bash
python scripts/debug/debug_phonemes.py "テストしたいテキスト"
```

### test_openjtalk.sh
```bash
bash scripts/debug/test_openjtalk.sh
```

## 注意事項

これらのスクリプトは開発用であり、製品版のビルドには含まれません。