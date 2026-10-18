"""Opt-in research-recipe requirements; no evaluation metrics enter training."""

import shlex
from collections.abc import Sequence
from pathlib import Path

import torch

from .reference_spec_contract import REFERENCE_SPEC_FRONTENDS


def validate_recipe(
    *,
    use_zero_shot,
    c_spk,
    spk_loss_type,
    spk_loss_positives,
    speaker_encoder_torch_path,
):
    if not use_zero_shot or c_spk <= 0:
        raise ValueError("strict zero-shot requires active zero-shot SCL")
    if spk_loss_type != "infonce" or spk_loss_positives != "cross_utt":
        raise ValueError("strict zero-shot requires infonce with cross_utt positives")
    if not speaker_encoder_torch_path or not Path(speaker_encoder_torch_path).is_file():
        raise ValueError(
            "strict zero-shot requires existing differentiable encoder weights"
        )


GENERATOR_REFERENCE_MODES = ("self", "cross_utt")


def reference_training_conflict(
    *, reference_conditioning, generator_reference, latent_filling_tau, c_swap_spk
):
    """参照条件付けと学習設定の組み合わせの誤りを文で返す (問題なければ None)。

    参照融合計画 §8 Task 7R:

    * ``reference_conditioning`` が ``"none"`` 以外なら、G の参照は別発話
      (``generator_reference="cross_utt"``) でなければならない。自己参照で
      参照 encoder を学習すると、target の音声そのものを読む近道になる。
    * Latent Filling / swap-SCL は G の条件を target 由来の架空・別話者
      embedding に差し替える。参照 spec / Ccap にはそれに対応する参照発話が
      ないため、参照条件付きとは併用しない。

    C0 群 (``cross_utt`` + ``reference_conditioning="none"``) はどちらも許す。
    """
    if reference_conditioning == "none":
        return None
    if generator_reference != "cross_utt":
        return (
            f"--reference-conditioning {reference_conditioning} requires "
            "--generator-reference cross_utt: the reference module must read a "
            "different utterance of the same speaker, never the target itself "
            "(build the pairs with piper_train.tools.build_reference_pairs)."
        )
    if (latent_filling_tau or 0) > 0 or (c_swap_spk or 0) > 0:
        return (
            f"--reference-conditioning {reference_conditioning} cannot be "
            "combined with Latent Filling (--latent-filling-tau > 0) or swap-SCL "
            "(--c-swap-spk > 0): both replace the generator condition with a "
            "target-derived embedding that has no reference utterance."
        )
    return None


def validate_reference_training_args(
    *, reference_conditioning, generator_reference, latent_filling_tau, c_swap_spk
):
    """CLI 起動時の組み合わせ検査。誤りは ``SystemExit`` (学習を始めない)。"""
    message = reference_training_conflict(
        reference_conditioning=reference_conditioning,
        generator_reference=generator_reference,
        latent_filling_tau=latent_filling_tau,
        c_swap_spk=c_swap_spk,
    )
    if message is not None:
        raise SystemExit(message)


def reference_spec_frontend_conflict(
    *, reference_conditioning, reference_spec_frontend
):
    """``reference_spec_frontend`` の誤りを文で返す (問題なければ None)。

    参照融合計画 §8 Task 11R (Ruling R14): 推論・評価で作る参照 spec は、学習
    dataset の ``.spec.pt`` を作った cache builder と同じ手順でなければならない。
    どの builder で作ったかは dataset から読み取れないので、ref_spec の学習では
    閉じた集合 (``reference_spec_contract``) の名前を明示させて hparam に残す。
    ref_spec 以外での指定は効果がないので拒否する (黙って無視しない)。
    """
    choices = ", ".join(sorted(REFERENCE_SPEC_FRONTENDS))
    if reference_conditioning == "ref_spec":
        if reference_spec_frontend is None:
            return (
                "--reference-conditioning ref_spec requires --reference-spec-frontend "
                f"(one of: {choices}): name the cache builder that produced the "
                "dataset's .spec.pt files, so that inference/evaluation builds the "
                "reference spec the same way. Determine it in the S2 data audit "
                "(reference-fusion plan §8) before training."
            )
        if reference_spec_frontend not in REFERENCE_SPEC_FRONTENDS:
            return (
                f"Unknown reference spec frontend {reference_spec_frontend!r}; "
                f"expected one of: {choices}"
            )
        return None
    if reference_spec_frontend is not None:
        return (
            "--reference-spec-frontend only applies to --reference-conditioning "
            f"ref_spec (got {reference_conditioning})"
        )
    return None


def validate_reference_spec_frontend_args(
    *, reference_conditioning, reference_spec_frontend
):
    """CLI 起動時の ``--reference-spec-frontend`` 検査。誤りは ``SystemExit``。"""
    message = reference_spec_frontend_conflict(
        reference_conditioning=reference_conditioning,
        reference_spec_frontend=reference_spec_frontend,
    )
    if message is not None:
        raise SystemExit(message)


# 参照条件付きモデルの契約を宣言する hparam と、その CLI flag (Ruling R16)。
# export・評価はこの宣言に従うので、resume で黙って変えると epoch によって
# 宣言の違う checkpoint ができ、評価の比較が成り立たなくなる。
REFERENCE_CONTRACT_HPARAMS = {
    "reference_spec_frontend": "--reference-spec-frontend",
    "generator_reference": "--generator-reference",
    "reference_max_frames": "--reference-max-frames",
}


def reference_hparam_mismatches(saved_hparams, current_hparams):
    """checkpoint と今回の参照 hparam の食い違いを ``(key, saved, current)`` で返す。

    ``generator_reference`` は none を含むすべての mode で、今回の値があれば
    比べる (Ruling R16a: C0 = none + cross_utt は主な比較群)。
    ``reference_spec_frontend`` / ``reference_max_frames`` は両方が同じ参照
    条件付き (none 以外) のときだけ比べる (none は参照 spec を使わない)。
    ``reference_conditioning`` 自体の食い違いは state_dict の key 差で止まる
    (strict resume / weights-only) か、single-speaker FT では参照 weights を
    捨てる (R9) ので、ここでは扱わない。checkpoint に key がない、または値が
    None (宣言なし) の key は比べない (旧 ckpt の挙動を変えない)。
    """
    saved_hparams = saved_hparams or {}
    current_hparams = current_hparams or {}
    mode = saved_hparams.get("reference_conditioning", "none")
    same_reference_mode = mode != "none" and mode == current_hparams.get(
        "reference_conditioning", "none"
    )

    def compared(key):
        if saved_hparams.get(key) is None:
            return False
        if key == "generator_reference":
            return current_hparams.get(key) is not None
        return same_reference_mode

    return [
        (key, saved_hparams[key], current_hparams.get(key))
        for key in REFERENCE_CONTRACT_HPARAMS
        if compared(key) and saved_hparams[key] != current_hparams.get(key)
    ]


def _mismatch_line(key, saved, current):
    return (
        f"checkpoint hparam {key}={saved!r} differs from this run's {current!r} "
        f"(pass {REFERENCE_CONTRACT_HPARAMS[key]} {shlex.quote(str(saved))} to keep it)"
    )


def validate_strict_resume_reference_hparams(saved_hparams, current_hparams):
    """strict resume の参照 hparam 照合。食い違いは ``SystemExit`` (重みを読む前)。"""
    mismatches = reference_hparam_mismatches(saved_hparams, current_hparams)
    if not mismatches:
        return
    lines = "\n".join(f"  - {_mismatch_line(*m)}" for m in mismatches)
    # frontend は weights-only でも変えられない (validate_warm_start_... が拒否)
    if all(key != "reference_spec_frontend" for key, _, _ in mismatches):
        how = (
            "To change it, start a new run from these weights with "
            "--resume-weights-only instead of --resume_from_checkpoint."
        )
    else:
        how = (
            "reference_spec_frontend names the cache builder of the reference "
            "specs the encoder was trained on; to use another one, start a new "
            "run (new output directory) without resuming from this checkpoint."
        )
    raise SystemExit(
        "Strict resume would silently re-declare the reference-conditioning "
        "contract of this checkpoint (export and evaluation follow the latest "
        f"declaration):\n{lines}\n{how}"
    )


def validate_warm_start_reference_hparams(
    saved_hparams, current_hparams, *, source_flag, logger
):
    """weights-only / multispeaker FT の参照 hparam 照合 (重みを読む前に呼ぶ)。

    ``reference_spec_frontend`` の食い違いは ``SystemExit`` (encoder が学習した
    参照 spec の分布が変わる)。``generator_reference`` / ``reference_max_frames``
    は新しい run の設定として許し、key と両方の値を WARNING に出す。
    """
    mismatches = reference_hparam_mismatches(saved_hparams, current_hparams)
    for key, saved, current in mismatches:
        if key == "reference_spec_frontend":
            raise SystemExit(
                f"{source_flag}: {_mismatch_line(key, saved, current)}. The "
                "reference encoder was trained on reference specs built by "
                f"{saved!r}; a different frontend changes their distribution. "
                "To use another frontend, train the reference encoder from "
                "scratch instead of warm-starting from this checkpoint."
            )
    for key, saved, current in mismatches:
        logger.warning(
            "%s: checkpoint hparam %s=%r differs from this run's %r; continuing "
            "with %r (the new checkpoints declare it).",
            source_flag,
            key,
            saved,
            current,
            current,
        )


def _pair_of_sequences(name, value, n):
    if (
        not isinstance(value, Sequence)
        or isinstance(value, str)
        or len(value) != 2
        or any(
            isinstance(side, str) or not isinstance(side, Sequence) for side in value
        )
    ):
        raise ValueError(f"{name} must be a (targets, references) pair of sequences")
    targets, references = value
    if len(targets) != n or len(references) != n:
        raise ValueError(
            f"{name} length must match the batch: got {len(targets)} targets / "
            f"{len(references)} references for {n} utterances"
        )
    return targets, references


def validate_reference_pairs(
    utterance_ids, reference_utterance_ids, speaker_ids, splits, audio_sha256
) -> None:
    """G の参照が target と分離されているかを batch 単位で確かめる。

    ``utterance_ids`` / ``reference_utterance_ids`` は行ごとの発話 identity
    (dataset の ``str(audio_norm_path.resolve())``)。``speaker_ids`` /
    ``splits`` / ``audio_sha256`` はそれぞれ ``(targets, references)`` の
    2 本の列。``audio_sha256`` は ``build_reference_pairs`` が書く
    ``audio_norm`` の float32 sample の sha256 (別 path の同一音声を検出する)。
    split は ``None`` 同士を「split なし = 1 つの split」とみなす。

    ここでの split は **jsonl の ``split`` フィールドだけ** を指す。学習が実行時に
    行う train / val の ``random_split`` とは無関係で、その subset を跨ぐ参照は
    ここでは検出しない (``VitsModel`` が読み込み時に数えて WARNING を出す)。

    参照 = target、別話者、別 split、同一音声 hash、値の欠落のどれかで
    ``ValueError``。
    """
    if utterance_ids is None or reference_utterance_ids is None:
        raise ValueError("reference pairs require target and reference identities")
    n = len(utterance_ids)
    if n == 0:
        raise ValueError("reference pairs require a nonempty batch")
    if len(reference_utterance_ids) != n:
        raise ValueError(
            f"reference_utterance_ids length {len(reference_utterance_ids)} does "
            f"not match {n} utterances"
        )
    target_spk, ref_spk = _pair_of_sequences("speaker_ids", speaker_ids, n)
    target_split, ref_split = _pair_of_sequences("splits", splits, n)
    target_hash, ref_hash = _pair_of_sequences("audio_sha256", audio_sha256, n)
    for row in range(n):
        target, reference = utterance_ids[row], reference_utterance_ids[row]
        if not isinstance(target, str) or not target:
            raise ValueError(f"row {row}: missing target utterance identity")
        if not isinstance(reference, str) or not reference:
            raise ValueError(f"row {row} ({target}): missing reference identity")
        if reference == target:
            raise ValueError(
                f"row {row} ({target}): the reference is the target itself"
            )
        if target_spk[row] is None or ref_spk[row] is None:
            raise ValueError(f"row {row} ({target}): missing speaker id")
        if int(target_spk[row]) != int(ref_spk[row]):
            raise ValueError(
                f"row {row} ({target}): reference {reference} is another speaker "
                f"({ref_spk[row]} != {target_spk[row]})"
            )
        if target_split[row] != ref_split[row]:
            raise ValueError(
                f"row {row} ({target}): reference {reference} is in another split "
                f"({ref_split[row]!r} != {target_split[row]!r})"
            )
        for side, value in (("target", target_hash[row]), ("reference", ref_hash[row])):
            if not isinstance(value, str) or not value:
                raise ValueError(f"row {row} ({target}): missing {side} audio_sha256")
        if target_hash[row] == ref_hash[row]:
            raise ValueError(
                f"row {row} ({target}): reference {reference} has the same audio "
                "(identical audio_sha256 at a different path)"
            )


def _embeddings_valid(embeddings):
    return (
        embeddings is not None
        and embeddings.ndim == 2
        and bool(torch.isfinite(embeddings).all())
        and bool((embeddings.norm(dim=1) > 0).all())
    )


def _reference_error(batch, n):
    """batch の参照ペア検査の誤り (なければ None)。例外は投げない。"""
    references = getattr(batch, "reference_embeddings", None)
    if getattr(batch, "reference_utterance_ids", None) is None or references is None:
        return "strict cross_utt requires reference fields in every batch"
    if not _embeddings_valid(references) or len(references) != n:
        return (
            "strict cross_utt requires finite nonzero reference embeddings for "
            "every utterance"
        )
    speakers = batch.speaker_ids
    try:
        validate_reference_pairs(
            batch.utterance_ids,
            batch.reference_utterance_ids,
            (
                speakers.detach().view(-1).cpu().tolist()
                if speakers is not None
                else [],
                getattr(batch, "reference_speaker_ids", None) or [],
            ),
            (
                getattr(batch, "splits", None) or [],
                getattr(batch, "reference_splits", None) or [],
            ),
            (
                getattr(batch, "audio_sha256s", None) or [],
                getattr(batch, "reference_audio_sha256s", None) or [],
            ),
        )
    except ValueError as exc:
        return str(exc)
    return None


def validate_training_batch(batch, *, gather=False, require_reference_pairs=False):
    embeddings = batch.speaker_embeddings
    payload = {
        "speakers": batch.speaker_ids.detach().view(-1).cpu().tolist()
        if batch.speaker_ids is not None
        else None,
        "utterances": getattr(batch, "utterance_ids", None),
        "embeddings_valid": _embeddings_valid(embeddings),
        "embedding_count": len(embeddings) if embeddings is not None else 0,
    }
    if require_reference_pairs:
        # 例外にせず payload に載せる: 全 rank が all_gather に参加してから
        # 一斉に落ちる (peer を all_gather に置き去りにしない)
        payload["reference_error"] = _reference_error(
            batch, len(payload["speakers"] or [])
        )
    payloads = [payload]
    # Every rank participates, including ranks with invalid/missing metadata.
    # This makes all ranks fail together rather than stranding a peer in all_gather.
    if torch.distributed.is_available() and torch.distributed.is_initialized():
        payloads = [None] * torch.distributed.get_world_size()
        torch.distributed.all_gather_object(payloads, payload)
    for item in payloads:
        ids, utterances = item["speakers"], item["utterances"]
        if ids is None or utterances is None or len(ids) != len(utterances):
            raise ValueError(
                "strict zero-shot requires speaker and utterance identities"
            )
        if not ids or any(
            not isinstance(value, str) or not value for value in utterances
        ):
            raise ValueError("strict zero-shot requires nonempty utterance identities")
        if not item["embeddings_valid"] or item["embedding_count"] != len(ids):
            raise ValueError(
                "strict zero-shot requires finite nonzero embeddings for every utterance"
            )
        if require_reference_pairs and item.get("reference_error") is not None:
            raise ValueError(item["reference_error"])
    candidates = [[item] for item in payloads] if not gather else [payloads]
    for candidate in candidates:
        candidate_ids = [speaker for item in candidate for speaker in item["speakers"]]
        utterances = [
            utterance for item in candidate for utterance in item["utterances"]
        ]
        if len(utterances) != len(set(utterances)):
            raise ValueError(
                "strict zero-shot rejects repeated utterances within the contrastive batch"
            )
        counts = [
            sum(other == speaker for other in candidate_ids) - 1
            for speaker in candidate_ids
        ]
        if not counts or min(counts) < 1:
            raise ValueError(
                "strict zero-shot requires a cross_utt positive for every anchor"
            )
    selected = payloads if gather else [payload]
    ids = [speaker for item in selected for speaker in item["speakers"]]
    return {
        "anchors": len(ids),
        "min_positives": min(ids.count(speaker) - 1 for speaker in ids),
        "fallbacks": 0,
    }
