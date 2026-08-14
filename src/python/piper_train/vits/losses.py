import logging
import math

import torch
from librosa.filters import mel as librosa_mel_fn
from torch.nn import functional as F


_LOGGER = logging.getLogger(__name__)


def feature_loss(fmap_r, fmap_g):
    loss = 0
    for dr, dg in zip(fmap_r, fmap_g, strict=False):
        for rl, gl in zip(dr, dg, strict=False):
            rl = rl.float().detach()
            gl = gl.float()
            loss += torch.mean(torch.abs(rl - gl))

    return loss * 2


def discriminator_loss(disc_real_outputs, disc_generated_outputs):
    loss = 0
    r_losses = []
    g_losses = []
    for dr, dg in zip(disc_real_outputs, disc_generated_outputs, strict=False):
        dr = dr.float()
        dg = dg.float()
        r_loss = torch.mean((1 - dr) ** 2)
        g_loss = torch.mean(dg**2)
        loss += r_loss + g_loss
        r_losses.append(r_loss.item())
        g_losses.append(g_loss.item())

    return loss, r_losses, g_losses


def generator_loss(disc_outputs):
    loss = 0
    gen_losses = []
    for dg in disc_outputs:
        dg = dg.float()
        l_dg = torch.mean((1 - dg) ** 2)
        gen_losses.append(l_dg)
        loss += l_dg

    return loss, gen_losses


def kl_loss(z_p, logs_q, m_p, logs_p, z_mask, logdet=None):
    """
    z_p, logs_q: [b, h, t_t]
    m_p, logs_p: [b, h, t_t]
    logdet: [b] or None — flow forward の per-sample 対数行列式 (v10 M1 SNAC
        flow)。None (default) は従来と厳密一致。
        log p(z) = log N(flow(z); m_p, logs_p) + logdet なので KL では負号で
        効く: loss_kl = kl_loss(...) - Σ logdet / Σ z_mask。符号を逆にすると
        flow が発散方向に報酬を受け KL が静かに壊れる (v10 design §4 M1)。
    """
    z_p = z_p.float()
    logs_q = logs_q.float()
    m_p = m_p.float()
    logs_p = logs_p.float()
    z_mask = z_mask.float()

    kl = logs_p - logs_q - 0.5
    kl += 0.5 * ((z_p - m_p) ** 2) * torch.exp(-2.0 * logs_p)
    kl = torch.sum(kl * z_mask)
    if logdet is not None:
        kl = kl - torch.sum(logdet.float())
    l_kl = kl / torch.sum(z_mask)
    return l_kl


def speaker_consistency_loss(gen_embedding, ref_embedding):
    """Speaker Consistency Loss (SCL) — コサイン類似度ベースの話者一貫性損失

    Parameters
    ----------
    gen_embedding : torch.Tensor
        生成音声から抽出した話者埋め込み [B, D]
    ref_embedding : torch.Tensor
        参照音声の話者埋め込み [B, D]

    Returns
    -------
    torch.Tensor
        スカラー損失値 (範囲: 0-2, 0が完全一致)
    """
    # NaN/Infチェック: CAM++ ONNX出力が異常な場合は0を返す
    if torch.isnan(gen_embedding).any() or torch.isnan(ref_embedding).any():
        return torch.tensor(0.0, device=gen_embedding.device)
    return 1.0 - F.cosine_similarity(gen_embedding, ref_embedding, dim=-1).mean()


def speaker_infonce_loss(
    gen_embedding,
    ref_embedding,
    speaker_ids=None,
    temperature: float = 0.07,
    positive_mode: str = "same_utt",
):
    """In-batch InfoNCE 版 SCL — 話者「判別」を要求する対比損失。

    plain cosine (speaker_consistency_loss) は「自分の参照に近づく」ことしか
    要求せず、batch 内の他話者から離れる圧力がない。InfoNCE は生成音声の
    embedding が batch 内の全参照 embedding の中から自話者を識別することを
    要求するため、話者の作り分け (v7/v8 の既知課題「区別性不十分」) に
    直接の勾配を与える。

    ``positive_mode`` (Phase 1 B-1、v10 roadmap):

    - ``"same_utt"`` (従来): 正例 = 条件付けに使った同一発話の参照 embedding
      (対角)。``samples_per_speaker > 1`` の batch では同一話者の他発話参照が
      false negative になるため、``speaker_ids`` を渡すと同一話者の
      非対角成分を分母から除外する (SupCon 方式のマスク)。
      **既知の欠陥**: 「同一発話の embedding への一致」を直接最適化するため、
      話者としての類似 (cross-utterance) が伸びなくても loss が下がる
      (Phase 0 Arm B で実証された Goodhart 経路)。
    - ``"cross_utt"``: 正例 = **同一話者の別発話**の参照 embedding (SupCon 形式)。
      対角 (same-utt) は正例にも負例にもせず分母から除外する (neutral)。
      発話固有の特徴では正例に近づけないため、話者としての転写に直接の
      勾配を与える。``speaker_ids`` 必須。batch 内に同一話者の別発話を持たない
      行は損失から除外し、全行が該当しない場合 (samples_per_speaker=1 相当)
      は same_utt 挙動にフォールバックする。

    Parameters
    ----------
    gen_embedding : torch.Tensor
        生成音声から抽出した話者埋め込み [B, D] (微分可能であること)
    ref_embedding : torch.Tensor
        参照 (conditioning に使った) 話者埋め込み [B, D]
    speaker_ids : torch.LongTensor | None
        [B] 話者 ID。None ならマスクなし (全非対角を negative 扱い)。
        ``positive_mode="cross_utt"`` では必須 (None は ValueError)
    temperature : float
        softmax 温度。小さいほど hard negative を強調 (default 0.07)
    positive_mode : str
        "same_utt" (従来、対角正例) | "cross_utt" (同一話者別発話正例)

    Returns
    -------
    torch.Tensor
        スカラー損失値 (cross entropy、0 が完全識別)
    """
    if positive_mode not in ("same_utt", "cross_utt"):
        raise ValueError(f"unknown positive_mode: {positive_mode!r}")
    if positive_mode == "cross_utt" and speaker_ids is None:
        raise ValueError(
            "positive_mode='cross_utt' requires speaker_ids "
            "(same-speaker other-utterance positives cannot be built without them)"
        )
    if torch.isnan(gen_embedding).any() or torch.isnan(ref_embedding).any():
        return torch.tensor(0.0, device=gen_embedding.device)

    gen = F.normalize(gen_embedding, p=2, dim=-1)
    ref = F.normalize(ref_embedding, p=2, dim=-1)
    b = gen.shape[0]
    if b < 2:
        # 対比相手がいない — cosine にフォールバック
        return 1.0 - F.cosine_similarity(gen, ref, dim=-1).mean()

    logits = gen @ ref.t() / temperature  # [B, B]
    eye = torch.eye(b, dtype=torch.bool, device=logits.device)

    if positive_mode == "cross_utt":
        same = speaker_ids.view(1, -1) == speaker_ids.view(-1, 1)
        pos_mask = same & ~eye  # 同一話者・別発話 = 正例
        has_pos = pos_mask.any(dim=1)
        if has_pos.any():
            # SupCon: L_i = -mean_{p∈P(i)} [logits_ip - logsumexp_{a∈A(i)} logits_ia]
            # A(i) = 対角 (same-utt) を除く全列。対角は負例化ではなく
            # 分母から完全除外 (neutral) — same-utt 一致への勾配を残さない
            # (v10 roadmap B-1 の footgun 指定、回帰テストで固定)。
            logits_no_diag = logits.masked_fill(eye, float("-inf"))
            log_denom = torch.logsumexp(logits_no_diag, dim=1)  # [B]
            pos_sum = (logits * pos_mask).sum(dim=1)
            n_pos = pos_mask.sum(dim=1).clamp(min=1)
            loss_per_row = log_denom - pos_sum / n_pos
            return loss_per_row[has_pos].mean()
        # batch 内に cross-utt 正例が 1 行もない (samples_per_speaker=1 相当)
        # — 学習信号を失わないよう same_utt 挙動にフォールバック

    labels = torch.arange(b, device=logits.device)
    if speaker_ids is not None:
        same = speaker_ids.view(1, -1) == speaker_ids.view(-1, 1)
        # 同一話者の他発話参照は negative にしない (false negative 除外)
        logits = logits.masked_fill(same & ~eye, float("-inf"))
    return F.cross_entropy(logits, labels)


def build_same_language_permutation(
    batch_size, language_ids=None, speaker_ids=None, generator=None
):
    """同一言語グループ内 roll で swap ペア permutation を作る純関数 (v10 S1)。

    swap-SCL (design doc §3.1) / Latent Filling (§3.3) の「同一言語 2 話者
    ペア」構築に共用する。cross-lingual swap は VC として高難度なため、
    言語グループを跨ぐペアは作らない (§3.1 ガード (a))。

    Parameters
    ----------
    batch_size : int
        バッチ行数 B (``language_ids=None`` のとき B を推定する材料が
        他にないため第一引数に取る)
    language_ids : torch.LongTensor | None
        [B] 言語 ID。None なら全体を 1 グループ扱い (monolingual 学習)
    speaker_ids : torch.LongTensor | None
        [B] 話者 ID。指定すると同一言語グループ内でも **同一話者** の
        ペアは valid=False にする (異話者 derangement)。language-balanced
        sampling + samples_per_speaker>1 の batch では言語グループが
        1 話者の複数発話だけで埋まり得るため、これがないと swap-SCL の
        swap 相手が目標話者 = z_p の中身の話者となり通常 SCL に退化する
        (design doc §3.1 の Goodhart 耐性が崩れる)。LF 補間も同一話者
        補間 (≒恒等) に希釈される。None は従来挙動 (別の行なら valid) と
        bit 互換。
    generator : torch.Generator | None
        CPU generator。指定で決定論 (DDP で rank ごとに揃えたい場合は
        global_step 由来 seed を渡す)

    Returns
    -------
    (perm, valid_mask) : (torch.LongTensor [B], torch.BoolTensor [B])
        perm は全体として ``arange(B)`` の permutation。各グループ内は
        cyclic shift (shift ∈ [1, n-1]) で ``perm[i] != i`` かつ
        ``language_ids[perm[i]] == language_ids[i]``。言語内 1 行のみ
        (singleton) の行は ``perm[i] == i`` / ``valid_mask[i] = False``
        (損失から除外するための mask)。

        speaker_ids 指定時: グループ内を話者 sort した順序への rotation で
        shift を「最大話者ブロック幅 m ≤ shift ≤ n - m」に取り、異話者
        ペアを構造的に保証する (m > n/2 のときは shift = m が同一話者
        ペア数の理論最小 2m - n を達成し、当たった行のみ valid=False)。
        言語グループ内が 1 話者のみの場合は全行 ``perm[i] == i`` /
        valid=False。language_ids / speaker_ids が GPU tensor の場合は
        同 device で返す。
    """
    if language_ids is None:
        lang = torch.zeros(batch_size, dtype=torch.long)
        out_device = speaker_ids.device if speaker_ids is not None else None
    else:
        lang = language_ids.detach().reshape(-1).to("cpu", torch.long)
        out_device = language_ids.device
    spk = None
    if speaker_ids is not None:
        spk = speaker_ids.detach().reshape(-1).to("cpu", torch.long)
    perm = torch.arange(batch_size)
    valid = torch.zeros(batch_size, dtype=torch.bool)
    # torch.unique は sorted を返すため group の走査順は決定論
    for lang_value in torch.unique(lang):
        idx = (lang == lang_value).nonzero(as_tuple=True)[0]
        n = int(idx.numel())
        if n < 2:
            # singleton: perm[i] == i のまま valid=False (swap 相手がいない)
            continue
        if spk is None:
            shift = int(torch.randint(1, n, (1,), generator=generator).item())
            # roll(-shift): perm[idx[k]] = idx[(k + shift) % n] — グループ内
            # cyclic shift。shift >= 1 なので自己写像は生じない
            perm[idx] = idx.roll(-shift)
            valid[idx] = True
            continue
        spk_grp = spk[idx]
        counts = torch.unique(spk_grp, return_counts=True)[1]
        if int(counts.numel()) < 2:
            # 言語グループ内が 1 話者のみ: 異話者ペアが作れない。
            # perm identity のまま全行 valid=False (同一話者 swap を損失に
            # 入れると swap-SCL が通常 SCL に退化するため black-out が正)
            continue
        # 話者ブロック sort 済み順序への rotation。shift k を最大ブロック
        # サイズ m 以上 (かつ n - m 以下) に取ると rotation は必ず話者
        # ブロックを跨ぐ (2m <= n なら全行異話者)。ブロック内の順序は
        # generator で shuffle し、step ごとにペアの組合せを変える。
        m = int(counts.max())
        shuffle = torch.randperm(n, generator=generator)
        spk_sh = spk_grp[shuffle]
        order = torch.argsort(spk_sh, stable=True)
        sorted_idx = idx[shuffle][order]
        spk_sorted = spk_sh[order]
        if 2 * m <= n:
            k = int(torch.randint(m, n - m + 1, (1,), generator=generator).item())
        else:
            # m > n/2: 同一話者ペアを完全には避けられない。k = m が理論
            # 最小 (2m - n 行) — 当たった行は下の話者比較で valid=False
            k = m
        # 1 <= k <= n-1 なので自己写像は生じない (perm は依然 permutation)
        perm[sorted_idx] = sorted_idx.roll(-k)
        valid[sorted_idx] = spk_sorted != spk_sorted.roll(-k)
    if out_device is not None and out_device.type != "cpu":
        perm = perm.to(out_device)
        valid = valid.to(out_device)
    return perm, valid


def swap_spk_ramp_weight(current_epoch, start_epoch, ramp_epochs):
    """swap-SCL の ramp 重み (v10 §3.4: KL annealing 完了後に 0→1 線形)。

    ``weight = c_swap_spk * swap_spk_ramp_weight(...)`` として使う。
    epoch < start → 0.0 / ramp 中 → (epoch - start) / ramp_epochs /
    start + ramp 以降 → 1.0。``ramp_epochs=0`` は step 関数 (start 以降 1.0)。
    """
    if current_epoch < start_epoch:
        return 0.0
    if ramp_epochs <= 0:
        return 1.0
    return min(1.0, (current_epoch - start_epoch) / float(ramp_epochs))


def gather_speaker_loss_inputs(gen_embedding, ref_embedding, speaker_ids=None):
    """DDP 全 rank の SCL 入力を結合する (v10 §3.2、--spk-loss-gather)。

    InfoNCE/SupCon の負例数を batch 28 → 4 GPU で 124 に増やす。
    embedding 側は **勾配が通る** ``torch.distributed.nn.all_gather`` を使う
    (素の ``torch.distributed.all_gather`` は勾配を切る既知の footgun)。
    speaker_ids は勾配不要なので素の all_gather で結合する。

    dist 未初期化 / world_size == 1 なら no-op (入力をそのまま返す)。

    NOTE: ``all_gather`` は全 rank で同一 shape を要求する。DDP 学習では
    epoch 末端の端数 batch で shape が揃わない可能性があるため、本関数は
    固定 batch サイズの sampler (SpeakerBalancedBatchSampler 等) との
    併用を前提とする。
    """
    if not torch.distributed.is_available() or not torch.distributed.is_initialized():
        return gen_embedding, ref_embedding, speaker_ids
    world_size = torch.distributed.get_world_size()
    if world_size <= 1:
        return gen_embedding, ref_embedding, speaker_ids

    # 遅延 import: torch.distributed.nn は distributed 非対応ビルドで import
    # 不能な場合があり、dist 初期化済みの分岐に入るまで触らない
    import torch.distributed.nn as dist_nn  # noqa: PLC0415

    gen_all = torch.cat(list(dist_nn.all_gather(gen_embedding)), dim=0)
    ref_all = torch.cat(list(dist_nn.all_gather(ref_embedding)), dim=0)
    sids_all = None
    if speaker_ids is not None:
        sid_list = [torch.zeros_like(speaker_ids) for _ in range(world_size)]
        torch.distributed.all_gather(sid_list, speaker_ids.contiguous())
        sids_all = torch.cat(sid_list, dim=0)
    return gen_all, ref_all, sids_all


def is_latent_filling_step(global_step, tau):
    """Latent Filling step の決定論的判定 (v10 §3.3、arXiv:2310.03538)。

    ``global_step`` を seed にした CPU ``torch.Generator`` で確率 τ の
    ベルヌーイ判定を行う。同 step 同結果 = DDP 全 rank 一致が保証される
    (rank ごとに判定がずれると LF step の D-skip / 損失置換で all_reduce
    mismatch → NCCL timeout になるため、ここでの決定論は生命線)。

    tau <= 0 で常に False (default = 既存挙動と bit 互換)。
    """
    if tau <= 0.0:
        return False
    if tau >= 1.0:
        return True
    g = torch.Generator()
    # 連番 seed の相関を避けるための multiplicative hash (Knuth)。
    # Python の hash() は PYTHONHASHSEED でプロセスごとに変わるため使わない
    # (rank 間不一致の源になる)。
    g.manual_seed((int(global_step) * 2654435761 + 0x5F3759DF) % (2**63))
    return bool(torch.rand((), generator=g).item() < tau)


def should_run_latent_filling_step(global_step, tau, d_update_interval=1):
    """LF step の最終判定 — G 更新が走る step に限定する (ラッチ防止)。

    ``d_update_interval >= 2`` では ``global_step % d_update_interval != 0``
    の step は G 更新を skip する (D-only step)。そこで LF step が発動すると
    G 更新なし (かつ LF は D 更新も skip) → ``optimizer.step()`` が 1 回も
    走らず PL manual optimization の ``global_step`` (= optimizer.step()
    回数) が凍結する。G-update 判定と LF 判定は両方とも凍結した
    ``global_step`` の純関数なので、以降の全 batch が同一分岐 (forward のみ
    更新ゼロ) を永久に取る **決定論的ラッチ**になる (silent、自己回復不能)。
    LF を G 更新 step に限定することでラッチを構造的に排除する。

    ``d_update_interval=1`` (CLI default) では :func:`is_latent_filling_step`
    と同一判定。決定論性 (同 step 同結果 = DDP 全 rank 一致) は維持される。
    """
    if int(global_step) % max(int(d_update_interval), 1) != 0:
        return False
    return is_latent_filling_step(global_step, tau)


def sample_latent_filling_lambda(n, generator=None):
    """λ ~ Beta(0.5, 0.5) (arcsine 分布) を n 個サンプルする (v10 §3.3)。

    ``torch.distributions.Beta`` は generator を受けないため、逆関数法で
    実装する: U ~ Uniform(0,1) に対し X = sin²(πU/2) ~ Beta(0.5, 0.5)
    (arcsine 分布の CDF は (2/π)·arcsin(√x))。mean 0.5 / var 0.125 /
    U 字型 (両端に質量) — 補間で端点付近 (≈ 片方の話者) を多めに踏む。
    """
    u = torch.rand(n, generator=generator)
    return torch.sin(math.pi * u / 2.0) ** 2


def build_latent_filling_embeddings(
    speaker_embeddings, language_ids=None, speaker_ids=None, generator=None
):
    """Latent Filling の摂動済み条件 embedding s̃ を作る (v10 §3.3)。

    行ごとに確率 0.5 で「同一言語の別話者と λ~Beta(0.5,0.5) 補間」、
    確率 0.5 で「s + N(0, σ=1e-4) noise」(arXiv:2310.03538 の 2 branch)。
    補間ペアは :func:`build_same_language_permutation` を流用し言語グループを
    跨がない。``speaker_ids`` を渡すと同一話者ペア (補間が ≒恒等に希釈)
    も除外される。同一言語 (異話者) ペアが作れない行は noise branch に
    フォールバックする。乱数は全て CPU generator から引く (決定論 +
    グローバル RNG stream を汚さない)。

    Returns
    -------
    torch.Tensor [B, D]
        s̃ (入力と同 device / dtype)。補間 branch の行は L2 再正規化済み
        (unit-norm 不変条件、下の NOTE 参照)
    """
    b = speaker_embeddings.size(0)
    device = speaker_embeddings.device
    dtype = speaker_embeddings.dtype

    perm, valid = build_same_language_permutation(
        b, language_ids=language_ids, speaker_ids=speaker_ids, generator=generator
    )
    perm = perm.to(device)
    valid = valid.to(device)

    lam = sample_latent_filling_lambda(b, generator=generator).to(device, dtype)
    use_interp = (torch.rand(b, generator=generator) < 0.5).to(device)
    noise = (
        torch.randn(speaker_embeddings.shape, generator=generator).to(device, dtype)
        * 1e-4
    )

    partner = speaker_embeddings[perm]
    interp = (
        lam.unsqueeze(-1) * speaker_embeddings + (1.0 - lam.unsqueeze(-1)) * partner
    )
    # NOTE: unit-norm 不変条件の維持。パイプライン全体 (dataset の CAM++
    # emb / σ-noise 経路の加算後 renormalize / 推論時) は「spk_proj 入力は
    # L2 unit-norm」を保つ。単位ベクトル 2 本の λ 補間は norm < 1 (直交
    # ペアの λ=0.5 で 1/√2) になるため、再正規化せず条件付けに渡すと
    # magnitude 不一致 → 学習進行と共に spk_proj が発散する既知事故
    # (lightning.py の σ-noise renormalize コメント、v7 実測) と同型の
    # 経路になる。LFCL の cosine 目標は norm 不変なので損失定義は不変。
    interp = F.normalize(interp, p=2, dim=-1)
    noised = speaker_embeddings + noise
    # 補間 branch は同一言語 (異話者) ペアが存在する行のみ
    # (singleton / 1 話者グループは noise branch)
    use_interp = use_interp & valid
    return torch.where(use_interp.unsqueeze(-1), interp, noised)


def dino_loss(student_emb, teacher_emb, center, tau_s=0.1, tau_t=0.07):
    """DINO自己蒸留損失 — 話者埋め込み空間の正則化

    Parameters
    ----------
    student_emb : torch.Tensor
        学生ネットワーク出力 [B, D]
    teacher_emb : torch.Tensor
        教師ネットワーク出力 [B, D] (通常は detach 済み)
    center : torch.Tensor
        EMA センター [D]
    tau_s : float
        学生温度パラメータ (default: 0.1)
    tau_t : float
        教師温度パラメータ (default: 0.07)

    Returns
    -------
    torch.Tensor
        スカラー損失値 (正の値、NaN/Inf 時は 0)
    """
    # NaN/Inf を入力段階で検出し、後段でロガーが原因を切り分けられるようにする。
    # PyTorch の clamp は NaN を素通しするため、上流から NaN が伝播してきた場合は
    # log_softmax → NaN → loss=0 マスクで「DINO が黙って機能停止する」状態に陥る。
    # 既知の現象 (multi-6lang スクラッチで step ~1249 から発生)。
    if not torch.isfinite(student_emb).all():
        _LOGGER.warning(
            "dino_loss: student_emb has non-finite values "
            "(NaN=%d, Inf=%d, total=%d). Returning 0.",
            int(torch.isnan(student_emb).sum().item()),
            int(torch.isinf(student_emb).sum().item()),
            student_emb.numel(),
        )
        return torch.tensor(0.0, device=student_emb.device)
    if not torch.isfinite(teacher_emb).all():
        _LOGGER.warning(
            "dino_loss: teacher_emb has non-finite values "
            "(NaN=%d, Inf=%d). Returning 0.",
            int(torch.isnan(teacher_emb).sum().item()),
            int(torch.isinf(teacher_emb).sum().item()),
        )
        return torch.tensor(0.0, device=student_emb.device)
    if not torch.isfinite(center).all():
        _LOGGER.warning("dino_loss: dino_center has non-finite values. Returning 0.")
        return torch.tensor(0.0, device=student_emb.device)

    # Clamp softmax inputs to prevent exp overflow (NaN fix #8)
    student_logits = (student_emb / tau_s).clamp(min=-50.0, max=50.0)
    teacher_logits = ((teacher_emb - center.to(teacher_emb.dtype)) / tau_t).clamp(
        min=-50.0, max=50.0
    )
    student_out = F.log_softmax(student_logits, dim=-1)
    teacher_out = F.softmax(teacher_logits, dim=-1)
    loss = -(teacher_out * student_out).sum(dim=-1).mean()
    # NaN防止: 損失が異常な場合は0を返す (上流チェックで漏れた数値発散の最終ガード)
    if torch.isnan(loss) or torch.isinf(loss):
        _LOGGER.warning(
            "dino_loss: post-softmax loss is non-finite "
            "(student_emb stats: min=%.3f max=%.3f, teacher_emb: min=%.3f max=%.3f). "
            "Returning 0.",
            float(student_emb.min()),
            float(student_emb.max()),
            float(teacher_emb.min()),
            float(teacher_emb.max()),
        )
        return torch.tensor(0.0, device=student_emb.device)
    return loss


# ---------------------------------------------------------------------------
# Pre-computed mel filterbank cache (keyed by (n_fft, n_mels, sr, fmin, fmax))
# ---------------------------------------------------------------------------
_mel_basis_cache: dict[tuple, torch.Tensor] = {}


def _get_mel_basis(
    n_fft: int = 1024,
    n_mels: int = 80,
    sample_rate: int = 22050,
    fmin: float = 0.0,
    fmax: float | None = None,
    device: torch.device | None = None,
    dtype: torch.dtype = torch.float32,
) -> torch.Tensor:
    """Return a mel filterbank matrix, caching across calls."""
    key = (n_fft, n_mels, sample_rate, fmin, fmax)
    if key not in _mel_basis_cache:
        fb = librosa_mel_fn(
            sr=sample_rate, n_fft=n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax
        )
        _mel_basis_cache[key] = torch.from_numpy(fb)
    basis = _mel_basis_cache[key]
    if device is not None:
        basis = basis.to(device=device, dtype=dtype)
    return basis


def mel_speaker_consistency_loss(
    y_hat: torch.Tensor,
    y: torch.Tensor,
    n_fft: int = 1024,
    n_mels: int = 80,
    hop_length: int = 256,
    win_length: int = 1024,
    sample_rate: int = 22050,
    mel_fmin: float = 0.0,
    mel_fmax: float | None = None,
) -> torch.Tensor:
    """Differentiable speaker consistency loss via mel spectrogram statistics.

    Compares per-band mean and standard-deviation of the mel spectrograms of
    generated audio (``y_hat``) and real audio (``y``) from the **same
    speaker**.  This captures speaker-specific spectral characteristics such as
    formant structure and spectral tilt without requiring a separate speaker
    encoder, and -- crucially -- the entire computation is differentiable so
    gradients flow back through the generator.

    Parameters
    ----------
    y_hat : Tensor [B, 1, T]
        Generated waveform (in the computation graph).
    y : Tensor [B, 1, T]
        Ground-truth waveform from the same speaker (detached).

    Returns
    -------
    loss : scalar Tensor
        L1 distance between per-band (mean, std) statistics.
    """
    # Squeeze to [B, T]
    if y_hat.dim() == 3:
        y_hat = y_hat.squeeze(1)
    if y.dim() == 3:
        y = y.squeeze(1)

    window = torch.hann_window(win_length, device=y_hat.device, dtype=y_hat.dtype)

    mel_basis = _get_mel_basis(
        n_fft=n_fft,
        n_mels=n_mels,
        sample_rate=sample_rate,
        fmin=mel_fmin,
        fmax=mel_fmax,
        device=y_hat.device,
        dtype=y_hat.dtype,
    )

    def _to_mel(wav: torch.Tensor) -> torch.Tensor:
        """wav [B, T] -> log-mel [B, n_mels, frames]"""
        # cuFFT does not support BFloat16 / FP16 (same as mel_processing.py).
        # Under bf16-mixed autocast the generator output arrives here in bf16
        # and torch.stft raises. Upcast defensively; downstream mel/log ops
        # keep fp32 throughput.
        if wav.dtype in (torch.bfloat16, torch.float16):
            wav = wav.float()
        pad = (n_fft - hop_length) // 2
        wav = torch.nn.functional.pad(wav, (pad, pad), mode="reflect")
        stft = torch.stft(
            wav,
            n_fft,
            hop_length=hop_length,
            win_length=win_length,
            window=window,
            center=False,
            return_complex=True,
        )
        mag = stft.abs().clamp(min=1e-5)
        mel = torch.matmul(mel_basis.to(mag.dtype), mag)
        log_mel = torch.log(mel.clamp(min=1e-5))
        return log_mel

    mel_hat = _to_mel(y_hat)
    mel_real = _to_mel(y.detach())

    mean_hat = mel_hat.mean(dim=-1)
    std_hat = mel_hat.std(dim=-1) + 1e-6
    mean_real = mel_real.mean(dim=-1)
    std_real = mel_real.std(dim=-1) + 1e-6

    loss = F.l1_loss(mean_hat, mean_real) + F.l1_loss(std_hat, std_real)
    return loss
