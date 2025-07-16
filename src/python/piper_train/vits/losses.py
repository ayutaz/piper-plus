import torch


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


def kl_loss(z_p, logs_q, m_p, logs_p, z_mask):
    """
    z_p, logs_q: [b, h, t_t]
    m_p, logs_p: [b, h, t_t]
    """
    z_p = z_p.float()
    logs_q = logs_q.float()
    m_p = m_p.float()
    logs_p = logs_p.float()
    z_mask = z_mask.float()

    kl = logs_p - logs_q - 0.5
    kl += 0.5 * ((z_p - m_p) ** 2) * torch.exp(-2.0 * logs_p)
    kl = torch.sum(kl * z_mask)
    l_kl = kl / torch.sum(z_mask)
    return l_kl


def duration_consistency_loss(pred_durations, text_lengths, phoneme_ids=None):
    """Duration consistency loss to promote stable speech rhythm.
    
    Args:
        pred_durations: Predicted durations [B, T]
        text_lengths: Length of text sequences [B]
        phoneme_ids: Optional phoneme IDs for phoneme-specific weighting [B, T]
    
    Returns:
        consistency_loss: Scalar loss value
        metrics: Dictionary of metrics for logging
    """
    batch_size = pred_durations.size(0)
    
    # Create mask for valid positions
    max_len = pred_durations.size(1)
    mask = torch.arange(max_len, device=pred_durations.device).expand(
        batch_size, max_len
    ) < text_lengths.unsqueeze(1)
    mask = mask.float()
    
    # Apply log transform to durations for better stability
    log_durations = torch.log(pred_durations + 1.0)  # +1 to avoid log(0)
    
    # Calculate mean duration per utterance
    mean_duration = (log_durations * mask).sum(dim=1) / text_lengths.float()
    
    # Calculate variance penalty
    duration_diff = log_durations - mean_duration.unsqueeze(1)
    variance_loss = ((duration_diff ** 2) * mask).sum() / mask.sum()
    
    # Calculate smoothness penalty (adjacent phoneme duration differences)
    if pred_durations.size(1) > 1:
        duration_diff_adjacent = log_durations[:, 1:] - log_durations[:, :-1]
        adjacent_mask = mask[:, 1:] * mask[:, :-1]
        smoothness_loss = ((duration_diff_adjacent ** 2) * adjacent_mask).sum() / adjacent_mask.sum()
    else:
        smoothness_loss = torch.tensor(0.0, device=pred_durations.device)
    
    # Phoneme-specific penalties (optional)
    phoneme_penalty = torch.tensor(0.0, device=pred_durations.device)
    if phoneme_ids is not None:
        # Penalize very short durations for vowels (assuming vowel IDs are in a certain range)
        # This is a simplified example - in practice, you'd have proper phoneme categories
        vowel_mask = (phoneme_ids >= 5) & (phoneme_ids <= 15)  # Example vowel ID range
        vowel_mask = vowel_mask.float() * mask
        
        short_duration_mask = pred_durations < 3.0  # Minimum 3 frames for vowels
        phoneme_penalty = (short_duration_mask.float() * vowel_mask).sum() / (vowel_mask.sum() + 1e-5)
    
    # Combine losses
    total_loss = variance_loss + 0.5 * smoothness_loss + 0.1 * phoneme_penalty
    
    # Metrics for logging
    metrics = {
        "duration_variance": variance_loss.item(),
        "duration_smoothness": smoothness_loss.item(),
        "duration_phoneme_penalty": phoneme_penalty.item(),
    }
    
    return total_loss, metrics


def duration_discriminator_loss(real_durations, pred_durations, text_lengths):
    """Adversarial loss for duration prediction.
    
    Args:
        real_durations: Ground truth durations [B, T]
        pred_durations: Predicted durations [B, T]
        text_lengths: Length of text sequences [B]
    
    Returns:
        disc_loss: Discriminator loss
        gen_loss: Generator loss
    """
    # Simple discriminator using statistical features
    def extract_duration_features(durations, lengths):
        """Extract statistical features from duration sequences."""
        features = []
        
        for i in range(durations.size(0)):
            dur = durations[i, :lengths[i]]
            
            # Statistical features
            mean_dur = dur.mean()
            std_dur = dur.std()
            max_dur = dur.max()
            min_dur = dur.min()
            
            # Rhythm features
            if lengths[i] > 1:
                diff = dur[1:] - dur[:-1]
                rhythm_var = diff.var()
            else:
                rhythm_var = torch.tensor(0.0, device=durations.device)
            
            features.append(torch.stack([
                mean_dur, std_dur, max_dur, min_dur, rhythm_var
            ]))
        
        return torch.stack(features)
    
    real_features = extract_duration_features(real_durations, text_lengths)
    pred_features = extract_duration_features(pred_durations, text_lengths)
    
    # Simple distance-based discriminator
    disc_loss = torch.mean((real_features - pred_features) ** 2)
    gen_loss = -disc_loss  # Generator tries to minimize distance
    
    return disc_loss, gen_loss
