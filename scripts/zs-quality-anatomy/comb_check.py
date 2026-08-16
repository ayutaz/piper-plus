# -*- coding: utf-8 -*-
"""Verify 1) 128-sample periodicity of >4kHz residual (framing artifact),
2) GT clipping sanity, 3) strength of SR/128 comb per file."""
import numpy as np
import librosa
from scipy.signal import butter, sosfilt

SR = 22050
BASE = "C:/Users/yuta/Desktop/Private/piper-v8-dataset-backup"
GT_DIR = ("C:/Users/yuta/Downloads/tyc-corpus1/"
          "つくよみちゃんコーパス Vol.1 声優統計コーパス（JVSコーパス準拠）/"
          "02 WAV（+12dB増幅）")
FILES = {
    "r2_t0": f"{BASE}/v10a_listen_samples/r2_ep79_tsukuyomi/t0.wav",
    "r2_t1": f"{BASE}/v10a_listen_samples/r2_ep79_tsukuyomi/t1.wav",
    "r2_t2": f"{BASE}/v10a_listen_samples/r2_ep79_tsukuyomi/t2.wav",
    "v9_t1": f"{BASE}/v9_listen_samples/tsukuyomi_zeroshot/v9_zeroshot_t1.wav",
    "v9_t2": f"{BASE}/v9_listen_samples/tsukuyomi_zeroshot/v9_zeroshot_t2.wav",
    "GT_ref": f"{BASE}/v9_listen_samples/tsukuyomi_zeroshot/reference_original.wav",
    "GT_001": f"{GT_DIR}/VOICEACTRESS100_001.wav",
    "GT_005": f"{GT_DIR}/VOICEACTRESS100_005.wav",
}

sos = butter(6, 4000, btype="highpass", fs=SR, output="sos")
print(f"{'file':>8} {'clip%':>6} {'ac@64':>7} {'ac@128':>7} {'ac@256':>7} "
      f"{'acmax(16-512)':>14} {'comb_exc_dB':>11}")
for name, p in FILES.items():
    y, _ = librosa.load(p, sr=SR, mono=True)
    clip = float(np.mean(np.abs(y) > 0.985)) * 100
    y = y / (np.sqrt(np.mean(y ** 2)) + 1e-9)
    hp = sosfilt(sos, y)
    # autocorrelation of high-passed signal (FFT-based)
    n = len(hp)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    F = np.fft.rfft(hp, nfft)
    ac = np.fft.irfft(F * np.conj(F))[:601]
    ac = ac / ac[0]
    lag_max = int(np.argmax(np.abs(ac[16:513]))) + 16
    # comb excess: mean spectrum, bins at multiples of 16 (n_fft 2048) vs neighbors
    S = np.abs(librosa.stft(hp, n_fft=2048, hop_length=256)) ** 2
    Pm = S.mean(1)
    grid = np.arange(16, 1024, 16)  # 172.27 Hz multiples
    exc = []
    for g in grid:
        if 372 <= g <= 790:  # 4-8.5kHz
            neigh = np.concatenate([Pm[g - 8:g - 3], Pm[g + 4:g + 9]])
            exc.append(10 * np.log10((Pm[g - 1:g + 2].max() + 1e-15)
                                     / (np.median(neigh) + 1e-15)))
    print(f"{name:>8} {clip:6.2f} {ac[64]:7.3f} {ac[128]:7.3f} {ac[256]:7.3f} "
          f"{np.abs(ac[16:513]).max():7.3f}@{lag_max:<4d} {np.mean(exc):11.2f}")
