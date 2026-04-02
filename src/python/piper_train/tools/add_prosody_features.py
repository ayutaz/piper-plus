#!/usr/bin/env python3
"""
既存データセットにprosody_featuresを追加する最適化スクリプト
音声処理をスキップし、JapanesePhonemizer().phonemize_with_prosody()のみ実行
"""

import argparse
import json
import shutil
from multiprocessing import Pool, cpu_count
from pathlib import Path

from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.encode.pua import map_token
from piper_plus_g2p.japanese import JapanesePhonemizer
from tqdm import tqdm


def process_utterance(item: dict) -> dict | None:
    """単一発話にprosody_featuresを追加し、phoneme_idsも更新"""
    try:
        text = item.get("text", "")
        if not text:
            return None

        # prosody情報付きで再phonemize（新しいトークン体系を使用）
        phonemes, prosody_info_list = JapanesePhonemizer().phonemize_with_prosody(text)

        # phoneme_ids を更新（新しいトークン体系: ?!, ?., ?~, N_m, N_n, N_ng, N_uvular）
        # piper_plus_g2p returns clean tokens; PUA-map them for id_map lookup
        id_map = get_phoneme_id_map("ja")
        phoneme_ids = []
        for p in phonemes:
            mapped = map_token(p)
            for ch in mapped:
                if ch in id_map:
                    phoneme_ids.extend(id_map[ch])

        # prosody_features を生成
        prosody_features = [
            {"a1": p.a1, "a2": p.a2, "a3": p.a3} if p is not None else None
            for p in prosody_info_list
        ]

        # 既存データを更新
        item["phoneme_ids"] = phoneme_ids  # 新しいトークン体系でphoneme_idsを更新
        item["prosody_features"] = prosody_features
        item["prosody_ids"] = []  # 将来用

        return item
    except Exception as e:
        print(f"Error processing: {text[:30]}... - {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dataset", required=True, help="既存dataset.jsonlのパス"
    )
    parser.add_argument("--output-dir", required=True, help="出力ディレクトリ")
    parser.add_argument(
        "--workers", type=int, default=cpu_count(), help="並列ワーカー数"
    )
    args = parser.parse_args()

    input_path = Path(args.input_dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 入力ディレクトリからconfig.jsonをコピー
    input_dir = input_path.parent
    config_src = input_dir / "config.json"
    if config_src.exists():
        shutil.copy(config_src, output_dir / "config.json")
        print("Copied config.json")

    # cacheディレクトリをシンボリックリンク
    cache_src = input_dir / "cache"
    cache_dst = output_dir / "cache"
    if cache_src.exists() and not cache_dst.exists():
        cache_dst.symlink_to(cache_src.resolve())
        print(f"Linked cache directory: {cache_src} -> {cache_dst}")

    # データセット読み込み
    print(f"Loading dataset from {input_path}")
    with open(input_path, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(items)} utterances")

    # 並列処理
    print(f"Processing with {args.workers} workers...")
    with Pool(args.workers) as pool:
        results = list(
            tqdm(
                pool.imap(process_utterance, items, chunksize=100),
                total=len(items),
                desc="Adding prosody",
            )
        )

    # 結果を書き込み
    output_path = output_dir / "dataset.jsonl"
    success_count = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for result in results:
            if result is not None:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                success_count += 1

    print(f"Wrote {success_count}/{len(items)} utterances to {output_path}")

    # config.jsonにprosody設定と新しいphoneme_id_mapを追加
    config_path = output_dir / "config.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # 新しいトークン体系でphoneme_id_mapを更新
        id_map = get_phoneme_id_map("ja")
        config["num_symbols"] = len(id_map)  # 65 (10 special + 55 phonemes)
        config["phoneme_id_map"] = id_map

        # prosody設定
        config["prosody_num_symbols"] = 11
        config["prosody_id_map"] = {str(i): [i] for i in range(11)}

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print(f"Updated config.json: num_symbols={len(id_map)}, prosody settings added")


if __name__ == "__main__":
    main()
