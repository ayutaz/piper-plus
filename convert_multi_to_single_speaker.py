#!/usr/bin/env python3
"""
マルチスピーカーモデルから単一話者用の追加学習モデルを作成するスクリプト
事前学習モデルから話者埋め込み層を削除し、オプティマイザ状態を初期化します
"""

import sys
from pathlib import Path

import torch


def create_partial_checkpoint_for_finetuning(original_ckpt_path, new_ckpt_path):
    """
    ファインチューニングのために、不整合なレイヤー（話者関連の層）と
    オプティマイザの状態を削除した新しいチェックポイントを作成します。
    """
    print(f"Loading original checkpoint from: {original_ckpt_path}")

    if not Path(original_ckpt_path).exists():
        print(
            f"ERROR: Checkpoint file not found at {original_ckpt_path}", file=sys.stderr
        )
        return False

    try:
        # CPUにロードしてGPUメモリを節約
        checkpoint = torch.load(original_ckpt_path, map_location="cpu")
    except Exception as e:
        print(f"ERROR: Failed to load checkpoint: {e}", file=sys.stderr)
        return False

    # チェックポイントの内容を確認
    print("\n--- Original Checkpoint Info ---")
    print(f"Keys in checkpoint: {list(checkpoint.keys())}")

    # ハイパーパラメータの確認と更新
    if "hyper_parameters" in checkpoint:
        hp = checkpoint["hyper_parameters"]
        print(f"Original num_speakers: {hp.get('num_speakers', 'N/A')}")
        print(f"Original batch_size: {hp.get('batch_size', 'N/A')}")
        print(f"Original learning_rate: {hp.get('learning_rate', 'N/A')}")

        # 単一話者用に更新
        hp["num_speakers"] = 0  # または1
        hp["speaker_id"] = None
        print(f"Updated num_speakers to: {hp['num_speakers']}")

    original_state_dict = checkpoint["state_dict"]

    # 削除するキーのリスト
    # これらは主に、話者数が変わったことで不要になったレイヤーです
    keys_to_remove = [
        # 話者埋め込み層と関連する条件付けレイヤー
        "model_g.emb_g.weight",
        "model_g.dec.cond.weight",
        "model_g.dec.cond.bias",
        "model_g.enc_q.enc.cond_layer.bias",
        "model_g.enc_q.enc.cond_layer.weight_g",
        "model_g.enc_q.enc.cond_layer.weight_v",
        "model_g.dp.cond.weight",
        "model_g.dp.cond.bias",
    ]

    # フローの条件付けレイヤーも動的にリストに追加
    for i in [0, 2, 4, 6]:
        for suffix in ["bias", "weight_g", "weight_v"]:
            keys_to_remove.append(f"model_g.flow.flows.{i}.enc.cond_layer.{suffix}")

    # discriminatorの話者関連レイヤーも削除（存在する場合）
    discriminator_keys_to_check = [
        "model_d.emb",
        "model_d.cond",
    ]

    # 実際に存在するキーのみを削除対象に追加
    keys_to_remove_set = set()
    for key in keys_to_remove:
        if key in original_state_dict:
            keys_to_remove_set.add(key)

    # discriminator関連のキーも確認
    for key in original_state_dict.keys():
        for pattern in discriminator_keys_to_check:
            if pattern in key:
                keys_to_remove_set.add(key)

    # 新しいstate_dictから、削除対象のキーを除外して作成
    new_state_dict = {
        key: value
        for key, value in original_state_dict.items()
        if key not in keys_to_remove_set
    }

    # チェックポイントのstate_dictを新しいものに更新
    checkpoint["state_dict"] = new_state_dict

    # オプティマイザの状態を削除（新しい学習のため）
    if "optimizer_states" in checkpoint:
        del checkpoint["optimizer_states"]
        print("Removed optimizer states from the checkpoint.")

    # LRスケジューラの状態も削除
    if "lr_schedulers" in checkpoint:
        del checkpoint["lr_schedulers"]
        print("Removed lr_schedulers from the checkpoint.")

    # EMA状態も確認して削除（必要に応じて）
    ema_keys_removed = []
    for key in ["ema_generator_state", "ema_discriminator_state"]:
        if key in checkpoint:
            # EMA状態内の話者関連キーを削除
            if isinstance(checkpoint[key], dict) and "module" in checkpoint[key]:
                ema_state = checkpoint[key]["module"]
                ema_keys_to_remove = []
                for ema_key in ema_state.keys():
                    for pattern in keys_to_remove_set:
                        if (
                            pattern.replace("model_g.", "") in ema_key
                            or pattern.replace("model_d.", "") in ema_key
                        ):
                            ema_keys_to_remove.append(ema_key)

                for ema_key in ema_keys_to_remove:
                    if ema_key in ema_state:
                        del ema_state[ema_key]
                        ema_keys_removed.append(ema_key)

    if ema_keys_removed:
        print(f"Removed {len(ema_keys_removed)} keys from EMA states")

    # エポック数とステップ数をリセット（ファインチューニング用）
    checkpoint["epoch"] = 0
    checkpoint["global_step"] = 0
    if "loops" in checkpoint:
        # PyTorch Lightningのloopsを完全にリセット
        if "fit_loop" in checkpoint["loops"]:
            fit_loop = checkpoint["loops"]["fit_loop"]
            fit_loop["epoch_loop.current_epoch"] = 0
            # epoch_progressをリセット（重要！）
            if "epoch_progress" in fit_loop:
                fit_loop["epoch_progress"] = {
                    "total": {"ready": 0, "completed": 0, "started": 0, "processed": 0},
                    "current": {
                        "ready": 0,
                        "completed": 0,
                        "started": 0,
                        "processed": 0,
                    },
                }
            # batch_progressをリセット
            if "epoch_loop.batch_progress" in fit_loop:
                fit_loop["epoch_loop.batch_progress"] = {
                    "total": {"ready": 0, "completed": 0, "started": 0, "processed": 0},
                    "current": {
                        "ready": 0,
                        "completed": 0,
                        "started": 0,
                        "processed": 0,
                    },
                    "is_last_batch": False,
                }
            # manual_optimization進捗をリセット
            if "epoch_loop.manual_optimization.optim_step_progress" in fit_loop:
                fit_loop["epoch_loop.manual_optimization.optim_step_progress"] = {
                    "total": {"ready": 0, "completed": 0},
                    "current": {"ready": 0, "completed": 0},
                }
        print("Reset epoch and step counters to 0")

    # 新しいチェックポイントディレクトリの作成
    output_path = Path(new_ckpt_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 新しい部分的なチェックポイントを保存
    torch.save(checkpoint, new_ckpt_path)

    print("\n--- Checkpoint Modification Summary ---")
    print(f"Original state_dict had {len(original_state_dict)} keys.")
    print(f"Removed {len(keys_to_remove_set)} keys:")
    for key in sorted(keys_to_remove_set):
        print(f"  - {key}")
    print(f"New state_dict has {len(new_state_dict)} keys.")
    print("---------------------------------------")
    print(f"\nPartial checkpoint for fine-tuning saved to: {new_ckpt_path}")
    print(
        "\nNow, use this new partial checkpoint path for the --resume_from_checkpoint argument."
    )

    return True


if __name__ == "__main__":
    # --- 設定箇所 ---
    # 20話者prosodyモデル（200エポック）のチェックポイントパス
    original_checkpoint = "/data/piper/output-moe-speech-20speakers-prosody/lightning_logs/version_7/checkpoints/epoch=199-step=207480.ckpt"

    # 保存する新しい「部分的チェックポイント」のパスとファイル名
    partial_checkpoint = "/data/piper/base_model_prosody/model.ckpt"
    # --- 設定ここまで ---

    success = create_partial_checkpoint_for_finetuning(
        original_checkpoint, partial_checkpoint
    )

    if success:
        print("\n" + "=" * 60)
        print("✓ 変換成功！")
        print("=" * 60)
        print("\n次のステップ:")
        print("1. tsukuyomi-chanデータセットの前処理:")
        print("   python -m piper_train.preprocess \\")
        print("     --language ja \\")
        print("     --input-dir /data/tsukuyomi-chan-ljspeech/wavs \\")
        print("     --output-dir /data/piper/dataset-tsukuyomi-single \\")
        print("     --dataset-format ljspeech \\")
        print("     --single-speaker \\")
        print("     --sample-rate 22050")
        print("\n2. 追加学習の実行:")
        print("   python -m piper_train \\")
        print("     --dataset-dir /data/piper/dataset-tsukuyomi-single \\")
        print(f"     --resume_from_checkpoint {partial_checkpoint} \\")
        print("     --accelerator gpu \\")
        print("     --devices 1 \\")
        print("     --batch-size 32 \\")
        print("     --max_epochs 500 \\")
        print("     --checkpoint-epochs 50")
    else:
        print("\n✗ 変換失敗", file=sys.stderr)
        sys.exit(1)
