"""Opt-in research-recipe requirements; no evaluation metrics enter training."""

from pathlib import Path

import torch


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


def validate_training_batch(batch, *, gather=False):
    embeddings = batch.speaker_embeddings
    payload = {
        "speakers": batch.speaker_ids.detach().view(-1).cpu().tolist()
        if batch.speaker_ids is not None
        else None,
        "utterances": getattr(batch, "utterance_ids", None),
        "embeddings_valid": embeddings is not None
        and embeddings.ndim == 2
        and bool(torch.isfinite(embeddings).all())
        and bool((embeddings.norm(dim=1) > 0).all()),
        "embedding_count": len(embeddings) if embeddings is not None else 0,
    }
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
