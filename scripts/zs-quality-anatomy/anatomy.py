# -*- coding: utf-8 -*-
"""Acoustic anatomy: r2_ep79 vs v9 vs GT (Tsukuyomi).

Metrics (voiced frames unless noted):
(a) band spectrum 0-11kHz / 500Hz bins, dB rel. 0-4kHz voiced power
(b) comb-based band HNR (harmonic vs inter-harmonic bin power)
(c) band spectral flatness (geo/arith mean, dB)
(d) frame-to-frame band flux + modulation spectrum high-band fraction
(e) silence / unvoiced band noise floor
(f) F0 stats, fine 250Hz envelope 0-4k for similarity
"""
import sys
import numpy as np
import librosa
from scipy.signal import welch, medfilt

SR = 22050
NFFT = 2048
HOP = 256
BW = SR / NFFT  # 10.77 Hz/bin
EDGES = np.arange(0, 11001, 500)          # 22 bands
EDGES_FINE = np.arange(0, 4001, 250)      # 16 fine bands for envelope
FREQS = librosa.fft_frequencies(sr=SR, n_fft=NFFT)
COARSE = [(0, 2000), (2000, 4000), (4000, 6000), (6000, 9000)]

BASE = "C:/Users/yuta/Desktop/Private/piper-v8-dataset-backup"
GT_DIR = ("C:/Users/yuta/Downloads/tyc-corpus1/"
          "つくよみちゃんコーパス Vol.1 声優統計コーパス（JVSコーパス準拠）/"
          "02 WAV（+12dB増幅）")

GROUPS = {
    "r2_ep79": [f"{BASE}/v10a_listen_samples/r2_ep79_tsukuyomi/t{i}.wav" for i in range(3)],
    "v9": [f"{BASE}/v9_listen_samples/tsukuyomi_zeroshot/v9_zeroshot_t{i}.wav" for i in (1, 2, 3)],
    "GT": [f"{BASE}/v9_listen_samples/tsukuyomi_zeroshot/reference_original.wav"]
          + [f"{GT_DIR}/VOICEACTRESS100_{i:03d}.wav" for i in range(1, 11)],
}


def band_index(freqs, edges):
    idx = np.searchsorted(edges, freqs, side="right") - 1
    idx[freqs >= edges[-1]] = -1
    return idx


BIDX = band_index(FREQS, EDGES)
BIDX_F = band_index(FREQS, EDGES_FINE)
NB = len(EDGES) - 1
NBF = len(EDGES_FINE) - 1


def band_sum(P, bidx, nb):
    """P: [F, T] -> [nb, T]"""
    out = np.zeros((nb, P.shape[1]))
    for b in range(nb):
        m = bidx == b
        if m.any():
            out[b] = P[m].sum(0)
    return out


def analyze(path):
    y, _ = librosa.load(path, sr=SR, mono=True)
    y = y / (np.sqrt(np.mean(y ** 2)) + 1e-9) * 0.1  # RMS normalize
    S = librosa.stft(y, n_fft=NFFT, hop_length=HOP)
    P = np.abs(S) ** 2
    f0, vflag, _ = librosa.pyin(y, fmin=70, fmax=600, sr=SR,
                                frame_length=NFFT, hop_length=HOP)
    T = min(P.shape[1], len(f0))
    P, f0, vflag = P[:, :T], f0[:T], vflag[:T].astype(bool)
    rms_db = 10 * np.log10(P.sum(0) + 1e-12)
    p95 = np.percentile(rms_db, 95)
    voiced = vflag & (rms_db > p95 - 30) & ~np.isnan(f0)
    silence = rms_db < p95 - 45
    unvoiced = ~voiced & ~silence

    r = {"path": path, "n_voiced": int(voiced.sum()),
         "n_sil": int(silence.sum()), "n_unv": int(unvoiced.sum())}

    # --- (a) band spectrum, ref = 0-4k voiced power
    Pv = P[:, voiced]
    Pm = Pv.mean(1)
    ref = Pm[(FREQS >= 0) & (FREQS < 4000)].sum() + 1e-12
    bp = np.array([Pm[BIDX == b].sum() for b in range(NB)])
    r["band_db"] = 10 * np.log10(bp / ref + 1e-15)
    bpf = np.array([Pm[BIDX_F == b].sum() for b in range(NBF)])
    r["band_db_fine"] = 10 * np.log10(bpf / ref + 1e-15)

    # tonal peak scan on mean voiced spectrum (>2.5kHz, +6dB over median-smoothed)
    spec_db = 10 * np.log10(Pm + 1e-15)
    smooth = medfilt(spec_db, 51)
    exc = spec_db - smooth
    peaks = [(float(FREQS[i]), float(exc[i]))
             for i in range(len(FREQS))
             if FREQS[i] > 2500 and exc[i] > 6
             and exc[i] == exc[max(0, i - 3):i + 4].max()]
    r["tonal_peaks"] = peaks

    # --- (b) comb HNR per band
    hnr_acc = [[] for _ in range(NB)]
    vidx = np.where(voiced & (f0 >= 120))[0]
    for t in vidx:
        f = f0[t]
        harm = np.zeros(len(FREQS), bool)
        kmax = int(10990 // f)
        for k in range(1, kmax + 1):
            c = k * f / BW
            hw = max(2, int(round(0.015 * k * f / BW)))
            hw = min(hw, max(2, int(f / BW / 3)))
            lo, hi = int(round(c)) - hw, int(round(c)) + hw
            harm[max(0, lo):min(len(FREQS), hi + 1)] = True
        col = P[:, t]
        for b in range(NB):
            bm = BIDX == b
            hbins, nbins = bm & harm, bm & ~harm
            if hbins.sum() >= 2 and nbins.sum() >= 2:
                hnr_acc[b].append(10 * np.log10(
                    (col[hbins].mean() + 1e-15) / (col[nbins].mean() + 1e-15)))
    r["hnr_db"] = np.array([np.median(a) if len(a) >= 10 else np.nan for a in hnr_acc])

    # --- (c) band flatness (median over voiced frames), dB
    flat = np.full(NB, np.nan)
    for b in range(NB):
        bm = BIDX == b
        if bm.sum() < 4:
            continue
        pb = Pv[bm] + 1e-15
        gm = np.exp(np.mean(np.log(pb), 0))
        am = pb.mean(0)
        flat[b] = np.median(10 * np.log10(gm / am))
    r["flat_db"] = flat

    # --- (d1) frame-to-frame band flux (voiced pairs), dB/frame
    bpow = band_sum(P, BIDX, NB) + 1e-15
    lb = 10 * np.log10(bpow)
    pair = voiced[1:] & voiced[:-1]
    r["flux_db"] = (np.abs(lb[:, 1:] - lb[:, :-1])[:, pair].mean(1)
                    if pair.sum() > 10 else np.full(NB, np.nan))

    # --- (d2) modulation spectrum: fraction of mod power 30-170 Hz
    S2 = librosa.stft(y, n_fft=1024, hop_length=64)
    P2 = np.abs(S2) ** 2
    fr2 = librosa.fft_frequencies(sr=SR, n_fft=1024)
    T2 = P2.shape[1]
    v2 = np.repeat(voiced, 4)[:T2]
    if len(v2) < T2:
        v2 = np.pad(v2, (0, T2 - len(v2)))
    fs_env = SR / 64  # 344.5 Hz
    mod_hi = []
    for lo, hi in COARSE:
        bm = (fr2 >= lo) & (fr2 < hi)
        env = 10 * np.log10(P2[bm].sum(0) + 1e-15)
        # contiguous voiced runs >= 0.3 s
        runs, start = [], None
        for i, v in enumerate(v2):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if i - start >= int(0.3 * fs_env):
                    runs.append((start, i))
                start = None
        if start is not None and T2 - start >= int(0.3 * fs_env):
            runs.append((start, T2))
        num = den = 0.0
        for s0, s1 in runs:
            seg = env[s0:s1] - env[s0:s1].mean()
            fq, psd = welch(seg, fs=fs_env, nperseg=min(256, len(seg)))
            num += psd[(fq >= 30) & (fq <= 170)].sum()
            den += psd[(fq >= 1) & (fq <= 170)].sum()
        mod_hi.append(num / den if den > 0 else np.nan)
    r["mod_hi_frac"] = np.array(mod_hi)

    # --- (e) silence & unvoiced band floor, dB rel 0-4k voiced power
    for name, mask in (("sil_db", silence), ("unv_db", unvoiced)):
        if mask.sum() >= 5:
            Pmx = P[:, mask].mean(1)
            bx = np.array([Pmx[BIDX == b].sum() for b in range(NB)])
            r[name] = 10 * np.log10(bx / ref + 1e-15)
        else:
            r[name] = np.full(NB, np.nan)

    # --- (f) F0 stats
    fv = f0[voiced]
    r["f0"] = dict(mean=float(np.mean(fv)), med=float(np.median(fv)),
                   std=float(np.std(fv)), p5=float(np.percentile(fv, 5)),
                   p95=float(np.percentile(fv, 95)))
    return r


def agg(results, key):
    a = np.array([r[key] for r in results], dtype=float)
    return np.nanmean(a, 0), np.nanstd(a, 0)


def main():
    np.seterr(all="ignore")
    res = {}
    for g, paths in GROUPS.items():
        res[g] = []
        for p in paths:
            print(f"# analyzing [{g}] {p.split('/')[-1]}", file=sys.stderr)
            res[g].append(analyze(p))

    centers = (EDGES[:-1] + EDGES[1:]) / 2
    G, V9, R2 = res["GT"], res["v9"], res["r2_ep79"]

    def table(key, title, fine=False):
        cs = (EDGES_FINE[:-1] + EDGES_FINE[1:]) / 2 if fine else centers
        gm, gs = agg(G, key)
        vm, _ = agg(V9, key)
        rm, _ = agg(R2, key)
        print(f"\n== {title} ==")
        print(f"{'band(Hz)':>10} {'GT':>7} {'GTsd':>5} {'v9':>7} {'r2':>7} {'v9-GT':>7} {'r2-GT':>7}")
        for i, c in enumerate(cs):
            print(f"{int(c - (125 if fine else 250))}-{int(c + (125 if fine else 250)):>5} "
                  f"{gm[i]:7.1f} {gs[i]:5.1f} {vm[i]:7.1f} {rm[i]:7.1f} "
                  f"{vm[i] - gm[i]:7.1f} {rm[i] - gm[i]:7.1f}")

    table("band_db", "(a) voiced band spectrum  dB rel 0-4k power")
    table("hnr_db", "(b) comb HNR per band  dB (harm/inter-harm bin power)")
    table("flat_db", "(c) band spectral flatness  dB (0=noise, more negative=tonal)")
    table("flux_db", "(d1) frame-to-frame band flux  dB/frame (voiced)")

    print("\n== (d2) modulation high-band (30-170Hz) power fraction, voiced env ==")
    gm, gs = agg(G, "mod_hi_frac")
    vm, _ = agg(V9, "mod_hi_frac")
    rm, _ = agg(R2, "mod_hi_frac")
    for i, (lo, hi) in enumerate(COARSE):
        print(f"{lo}-{hi}Hz: GT {gm[i]:.3f}±{gs[i]:.3f}  v9 {vm[i]:.3f}  r2 {rm[i]:.3f}")

    table("sil_db", "(e1) SILENCE band floor  dB rel 0-4k voiced power")
    table("unv_db", "(e2) UNVOICED band spectrum  dB rel 0-4k voiced power")
    table("band_db_fine", "(f1) fine envelope 0-4k (250Hz bins)  dB rel 0-4k power", fine=True)

    print("\n== (f2) F0 stats (Hz) ==")
    print(f"{'group':>8} {'mean':>6} {'med':>6} {'std':>6} {'p5':>6} {'p95':>6} {'range':>6}")
    for g in ("GT", "v9", "r2_ep79"):
        for r in res[g]:
            f = r["f0"]
            nm = r["path"].split("/")[-1]
            print(f"{g:>8} {f['mean']:6.1f} {f['med']:6.1f} {f['std']:6.1f} "
                  f"{f['p5']:6.1f} {f['p95']:6.1f} {f['p95'] - f['p5']:6.1f}  {nm}")

    print("\n== tonal peaks >2.5kHz (+6dB over smoothed, voiced mean spectrum) ==")
    for g in ("GT", "v9", "r2_ep79"):
        for r in res[g]:
            if r["tonal_peaks"]:
                pk = ", ".join(f"{f:.0f}Hz(+{e:.1f}dB)" for f, e in r["tonal_peaks"])
                print(f"[{g}] {r['path'].split('/')[-1]}: {pk}")

    print("\n== frame counts ==")
    for g in ("GT", "v9", "r2_ep79"):
        for r in res[g]:
            print(f"[{g}] {r['path'].split('/')[-1]}: voiced={r['n_voiced']} "
                  f"unv={r['n_unv']} sil={r['n_sil']}")


if __name__ == "__main__":
    main()
