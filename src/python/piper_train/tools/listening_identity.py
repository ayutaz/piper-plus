"""話者の同一性を聞き分ける、条件を伏せた聴感試験を作り、答えを集計する。

計画書 docs/design/zero-shot-speaker-identity-plan-2026-10-29.md §3.1 / §5 の
試験。各試行では、話者 S の実録音 (参照) を聞いた後に試験音声を聞き、
「同じ人か」を 4 段階 (1 確実に別人 / 2 たぶん別人 / 3 たぶん本人 /
4 確実に本人) で答える。3 と 4 を「本人」と数える。

試験音声の条件:

    R+  S の別の実録音                 聞き手にとっての上限
    R-  別話者の実録音                 別人を本人と誤る率
    Z+  S の参照から合成した音声       合成が本人に聞こえるか
    Z-  別話者の参照から合成した音声   合成が誰にでも似た声になっていないか

試聴用の音声は、帯域の違いで合成と分からないよう、すべて 22.05kHz に
揃えてから RMS で音量を揃え、16bit で書く。この加工は試聴用だけで、数値の
測定は素の出力で別に行う (zs-eval-contract §2-5)。ファイル名はハッシュにし、
条件・話者の対応表 (key) はページの directory の外に書く。本ツールは
合否を判定しない。集計した率を計画書の規則に照らして人が判定する。

使い方:

    # 開発群の試験を作る (pools は set と合成音声の directory から作る)
    python -m piper_train.tools.listening_identity build \\
        --set <built set> --synth <run>/torch-ema/secs-run/synth [--synth ...] \\
        --per-condition 6 --seed 1 --sessions 2 \\
        --output <pages dir> --key-dir <key dir>

    # 答えを集計する
    python -m piper_train.tools.listening_identity score \\
        --key <key dir>/s1.json --answers answers-s1.json [...] --json-out result.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

import numpy as np


CONDITIONS = ("R+", "R-", "Z+", "Z-")
SAMPLE_RATE = 22050
TARGET_RMS = 10 ** (-23 / 20)
PEAK_LIMIT = 0.99


def _pool_for(pools: dict, voice: str, condition: str) -> list[Path]:
    record = pools[voice]
    if condition == "R+":
        return list(record["real"])
    if condition == "Z+":
        return list(record["synth"])
    kind = "real" if condition == "R-" else "synth"
    return [path for other in record["others"] for path in pools[other][kind]]


def plan_trials(pools: dict, per_condition: int, seed: int) -> list[dict]:
    """Pick ``per_condition`` trials for every voice and condition."""
    rng = random.Random(seed)
    trials = []
    for voice in sorted(pools):
        references = list(pools[voice]["references"])
        for condition in CONDITIONS:
            pool = _pool_for(pools, voice, condition)
            if not pool or not references:
                raise ValueError(f"{voice}/{condition}: empty pool")
            picks = []
            while len(picks) < per_condition:
                picks += rng.sample(pool, min(len(pool), per_condition - len(picks)))
            for test in picks:
                trials.append(
                    {
                        "voice": voice,
                        "condition": condition,
                        "reference": rng.choice(references),
                        "test": test,
                    }
                )
    return trials


def _prepare_audio(source: Path, target: Path) -> None:
    import soundfile as sf  # noqa: PLC0415
    import soxr  # noqa: PLC0415

    audio, rate = sf.read(source, dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != SAMPLE_RATE:
        audio = soxr.resample(audio, rate, SAMPLE_RATE, quality="HQ")
    rms = float(np.sqrt(np.mean(audio**2)))
    if rms > 0:
        audio = audio * (TARGET_RMS / rms)
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > PEAK_LIMIT:
        audio = audio * (PEAK_LIMIT / peak)
    sf.write(target, audio, SAMPLE_RATE, subtype="PCM_16")


def build_session(
    trials: list[dict],
    output: Path,
    key_path: Path,
    *,
    session: str,
    seed: int,
    repeat_fraction: float = 0.1,
) -> dict:
    """Write the page and audio to ``output`` and the condition key to ``key_path``."""
    output, key_path = Path(output), Path(key_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    if key_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("the key must be written outside the page directory")
    rng = random.Random(seed)
    order = list(trials)
    rng.shuffle(order)
    repeats = rng.sample(range(len(order)), round(repeat_fraction * len(order)))
    items = [(trial, None) for trial in order]
    for index in repeats:
        # A repeat goes after its original (found by identity: earlier
        # insertions shift positions, and two trials may be equal dicts).
        original = next(
            i for i, (t, r) in enumerate(items) if t is order[index] and r is None
        )
        items.insert(rng.randint(original + 1, len(items)), (order[index], index))

    (output / "audio").mkdir(parents=True, exist_ok=True)
    names: dict[Path, str] = {}

    def audio_name(path: Path) -> str:
        path = Path(path)
        if path not in names:
            digest = hashlib.sha256(f"{session}\0{path.resolve()}".encode()).hexdigest()
            names[path] = digest[:16]
            _prepare_audio(path, output / "audio" / f"{names[path]}.wav")
        return names[path]

    original_ids = {}
    key_trials, page_trials = [], []
    for number, (trial, repeat_index) in enumerate(items):
        trial_id = f"t{number:03d}"
        if repeat_index is None:
            original_ids[id(trial)] = trial_id
        reference, test = audio_name(trial["reference"]), audio_name(trial["test"])
        page_trials.append(
            {"id": trial_id, "a": f"audio/{reference}.wav", "b": f"audio/{test}.wav"}
        )
        key_trials.append(
            {
                "trial": trial_id,
                "voice": trial["voice"],
                "condition": trial["condition"],
                "reference": str(trial["reference"]),
                "test": str(trial["test"]),
                "repeat_of": None,
                "_repeat_index": repeat_index,
            }
        )
    for entry, (trial, repeat_index) in zip(key_trials, items, strict=True):
        if repeat_index is not None:
            entry["repeat_of"] = original_ids[id(trial)]
        del entry["_repeat_index"]

    key = {"session": session, "seed": seed, "trials": key_trials}
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    page = _PAGE.replace("__SESSION__", json.dumps(session)).replace(
        "__TRIALS__", json.dumps(page_trials)
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    return key


def _wilson(hits: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z = 1.959963984540054
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0.0, center - half), min(1.0, center + half)]


def _rate(values: list[int]) -> dict:
    hits = sum(1 for v in values if v >= 3)
    return {
        "n": len(values),
        "identity": hits,
        "identity_rate": hits / len(values) if values else None,
        "wilson95": _wilson(hits, len(values)),
        "mean_rating": sum(values) / len(values) if values else None,
    }


def score(keys: list[dict], answer_sets: list[dict]) -> dict:
    """Identity rates per condition (and per voice) plus repeat agreement."""
    by_session = {}
    for answers in answer_sets:
        if answers["session"] in by_session:
            raise ValueError(f"duplicate answers for session {answers['session']!r}")
        by_session[answers["session"]] = answers["answers"]
    per_condition: dict[str, list[int]] = {c: [] for c in CONDITIONS}
    per_voice: dict[str, dict[str, list[int]]] = {}
    agree, pairs = 0, 0
    for key in keys:
        answers = by_session.get(key["session"])
        if answers is None:
            raise ValueError(f"no answers for session {key['session']!r}")
        for trial in key["trials"]:
            value = answers.get(trial["trial"])
            if not isinstance(value, int) or not 1 <= value <= 4:
                raise ValueError(f"{key['session']}/{trial['trial']}: answer {value!r}")
            if trial["repeat_of"] is not None:
                first = answers[trial["repeat_of"]]
                pairs += 1
                agree += (first >= 3) == (value >= 3)
                continue
            per_condition[trial["condition"]].append(value)
            per_voice.setdefault(trial["voice"], {}).setdefault(
                trial["condition"], []
            ).append(value)
    return {
        "conditions": {c: _rate(v) for c, v in per_condition.items()},
        "voices": {
            voice: {c: _rate(v) for c, v in sorted(conds.items())}
            for voice, conds in sorted(per_voice.items())
        },
        "repeat_pairs": pairs,
        "repeat_agreement": agree / pairs if pairs else None,
    }


def pools_from_set(set_dir: Path, synth_roots: list[Path]) -> dict:
    """Voices from a built evaluation set and per-group synth directories.

    ``others`` are the voices whose speaker id appears in this voice's floor
    files (the fixed floor speakers); if none match, every other voice.
    """
    set_dir = Path(set_dir)
    record = json.loads((set_dir / "set.json").read_text(encoding="utf-8"))
    groups = list(record["groups"])
    pools = {}
    for group in groups:
        base = set_dir / "groups" / group
        references = [
            base / "speaker" / e["reference"]
            for e in record["groups"][group]["embeddings"]
        ]
        reference_names = {p.name for p in references}
        real = sorted(
            p for p in (base / "speaker").glob("*.wav") if p.name not in reference_names
        )
        synth = sorted(
            p for root in synth_roots for p in (Path(root) / group).glob("*.wav")
        )
        floor_names = " ".join(p.name for p in (base / "floor").glob("*.wav"))
        others = [
            g for g in groups if g != group and g.split("_", 1)[-1] in floor_names
        ] or [g for g in groups if g != group]
        pools[group] = {
            "references": references,
            "real": real,
            "synth": synth,
            "others": others,
        }
    return pools


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--set", type=Path, required=True)
    build.add_argument("--synth", type=Path, action="append", required=True)
    build.add_argument("--per-condition", type=int, required=True)
    build.add_argument("--seed", type=int, required=True)
    build.add_argument("--sessions", type=int, default=1)
    build.add_argument("--session-prefix", default="s")
    build.add_argument("--repeat-fraction", type=float, default=0.1)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--key-dir", type=Path, required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("--key", type=Path, action="append", required=True)
    scoring.add_argument("--answers", type=Path, action="append", required=True)
    scoring.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "build":
        pools = pools_from_set(args.set, args.synth)
        trials = plan_trials(pools, args.per_condition, args.seed)
        rng = random.Random(args.seed)
        rng.shuffle(trials)
        for index in range(args.sessions):
            session = f"{args.session_prefix}{index + 1}"
            part = trials[index :: args.sessions]
            build_session(
                part,
                args.output / session,
                args.key_dir / f"{session}.json",
                session=session,
                seed=args.seed * 1000 + index,
                repeat_fraction=args.repeat_fraction,
            )
            print(
                f"{session}: {len(part)} trials -> {args.output / session / 'index.html'}"
            )
        return 0

    keys = [json.loads(p.read_text(encoding="utf-8")) for p in args.key]
    answers = [json.loads(p.read_text(encoding="utf-8")) for p in args.answers]
    result = score(keys, answers)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0


_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>話者の聞き分け</title>
<style>
:root { --bg: #fafafa; --fg: #1d1d1f; --muted: #6e6e73; --line: #d2d2d7; --accent: #0a66c2; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161617; --fg: #f5f5f7; --muted: #a1a1a6; --line: #3a3a3c; --accent: #4da3ff; }
}
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Yu Gothic UI", sans-serif; }
main { max-width: 640px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 20px; margin: 0 0 8px; }
.muted { color: var(--muted); font-size: 14px; }
.card { border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin: 16px 0; }
.play { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 16px; }
button { font: inherit; padding: 10px 14px; border-radius: 10px; border: 1px solid var(--line);
  background: transparent; color: var(--fg); cursor: pointer; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.answers { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.answers button { padding: 14px 8px; }
.answers button.chosen { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.bar { height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }
.bar div { height: 100%; background: var(--accent); width: 0; }
.nav { display: flex; justify-content: space-between; margin-top: 12px; }
</style>
</head>
<body>
<main>
<h1>話者の聞き分け</h1>
<p class="muted">最初に聞く声 (A) と、次に聞く声 (B) が同じ人かどうかを答えてください。
話している内容や音質ではなく、声の主が同じかどうかで判断してください。
キーボードの 1〜4 でも答えられます。答えると次の試行に進みます。</p>
<div class="bar" aria-hidden="true"><div id="progress"></div></div>
<p class="muted" id="count"></p>
<section class="card" id="trial">
  <div class="play">
    <button id="playA">A を再生</button>
    <button id="playB">B を再生</button>
    <button id="playAB">A → B を再生</button>
  </div>
  <div class="answers">
    <button data-v="1">1 確実に別人</button>
    <button data-v="2">2 たぶん別人</button>
    <button data-v="3">3 たぶん本人</button>
    <button data-v="4">4 確実に本人</button>
  </div>
  <div class="nav">
    <button id="prev">前へ</button>
    <button id="next">次へ</button>
  </div>
</section>
<section class="card">
  <p class="muted" id="status"></p>
  <button id="save">答えを保存 (JSON)</button>
</section>
</main>
<script>
const SESSION = __SESSION__;
const TRIALS = __TRIALS__;
const STORE = "listening-identity-" + SESSION;
let state = { answers: {}, index: 0, started: new Date().toISOString() };
try { const saved = localStorage.getItem(STORE); if (saved) state = JSON.parse(saved); } catch (e) {}
const audioA = new Audio(), audioB = new Audio();
function persist() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) {} }
function done() { return TRIALS.filter(t => state.answers[t.id]).length; }
function render() {
  const t = TRIALS[state.index];
  audioA.src = t.a; audioB.src = t.b;
  document.getElementById("count").textContent =
    "試行 " + (state.index + 1) + " / " + TRIALS.length + "(回答済み " + done() + ")";
  document.getElementById("progress").style.width = (100 * done() / TRIALS.length) + "%";
  document.querySelectorAll(".answers button").forEach(b =>
    b.classList.toggle("chosen", Number(b.dataset.v) === state.answers[t.id]));
  document.getElementById("status").textContent = done() === TRIALS.length
    ? "すべて答えました。保存ボタンで JSON を保存してください。"
    : "途中の答えはこのブラウザに保存されます。最後に保存ボタンで JSON を保存してください。";
}
function playAB() {
  audioB.pause(); audioA.currentTime = 0;
  audioA.onended = () => { setTimeout(() => { audioB.currentTime = 0; audioB.play(); }, 400); };
  audioA.play();
}
function answer(v) {
  state.answers[TRIALS[state.index].id] = v; persist();
  if (state.index < TRIALS.length - 1) { state.index += 1; persist(); render(); playAB(); }
  else render();
}
document.getElementById("playA").onclick = () => { audioA.onended = null; audioB.pause(); audioA.currentTime = 0; audioA.play(); };
document.getElementById("playB").onclick = () => { audioA.onended = null; audioA.pause(); audioB.currentTime = 0; audioB.play(); };
document.getElementById("playAB").onclick = playAB;
document.querySelectorAll(".answers button").forEach(b => b.onclick = () => answer(Number(b.dataset.v)));
document.getElementById("prev").onclick = () => { if (state.index > 0) { state.index -= 1; persist(); render(); } };
document.getElementById("next").onclick = () => { if (state.index < TRIALS.length - 1) { state.index += 1; persist(); render(); } };
document.addEventListener("keydown", e => { if (["1","2","3","4"].includes(e.key)) answer(Number(e.key)); });
document.getElementById("save").onclick = () => {
  const body = { session: SESSION, started: state.started, saved: new Date().toISOString(), answers: state.answers };
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(body, null, 1)], { type: "application/json" }));
  link.download = "answers-" + SESSION + ".json"; link.click();
};
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
