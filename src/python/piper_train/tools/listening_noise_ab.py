"""comb 超過が聞いて分かる雑音と対応しているかを、伏せた A/B 聞き比べで確かめる。

計画書 docs/design/zero-shot-speaker-identity-plan-2026-10-29.md P0-6。
同じ文・同じ参照から 2 つのモデル (arm) で合成した音声を組にし、「雑音
(ざらつき・がびがび) が多いのはどちらか」を選んでもらう。comb 超過
(``measure_comb_artifacts``) の大きい方を選んだ率を集計する。

組の選び方 (``select_pairs``):

- 両 arm の comb 超過の差が ``min_diff`` (既定 0.67 dB = P0-3 で測った話者
  1 人あたりの合成時の振れ幅の最大) 未満の組は使わない。
- 指標の上で「もう一方の arm の方が雑音が多い」組 (逆向きの組) は、条件を
  満たすものをすべて入れる。arm の違いそのもの (声の感じなど) を雑音と
  取り違えた答えが、指標と一致して見えるのを防ぐため。
- 残りは seed で無作為に選び、1 声あたり ``max_per_voice`` 組までにする。

試聴用の音声は RMS で音量だけ揃え (帯域は変えない)、16bit で書く。左右
(A/B) は seed で入れ替え、arm と comb の対応表はページの外に書く。本ツールは
合否を判定しない。

使い方:

    python -m piper_train.tools.listening_noise_ab build \\
        --arm C0=<dir of wav> --arm C0-self=<dir of wav> \\
        --count 20 --seed 20261029 --output <page dir> --key <key json>

    python -m piper_train.tools.listening_noise_ab score \\
        --key <key json> --answers answers-noise.json [--json-out result.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from .listening_identity import _prepare_audio, _wilson


def _voice(stem: str) -> str:
    """``ja_361eb7a2_r0_t1`` -> ``ja_361eb7a2`` (strip the ``_r*_t*`` suffix)."""
    return stem.rsplit("_", 2)[0]


def select_pairs(
    scores: dict[str, dict[str, float]],
    arm_x: str,
    arm_y: str,
    *,
    count: int,
    min_diff: float,
    max_per_voice: int,
    seed: int,
) -> list[dict]:
    """Pick ``count`` stems whose comb difference exceeds ``min_diff``."""
    candidates = []
    for stem in sorted(scores):
        x, y = scores[stem].get(arm_x), scores[stem].get(arm_y)
        if x is None or y is None or abs(x - y) < min_diff:
            continue
        candidates.append({"stem": stem, "comb": {arm_x: x, arm_y: y}})
    majority_x = sum(c["comb"][arm_x] > c["comb"][arm_y] for c in candidates)
    majority = arm_x if 2 * majority_x >= len(candidates) else arm_y
    minority = arm_y if majority == arm_x else arm_x

    def reverse(c):
        return c["comb"][minority] > c["comb"][majority]

    chosen = [c for c in candidates if reverse(c)]
    rest = [c for c in candidates if not reverse(c)]
    random.Random(seed).shuffle(rest)
    per_voice: dict[str, int] = {}
    for c in chosen:
        per_voice[_voice(c["stem"])] = per_voice.get(_voice(c["stem"]), 0) + 1
    for c in rest:
        if len(chosen) >= count:
            break
        voice = _voice(c["stem"])
        if per_voice.get(voice, 0) >= max_per_voice:
            continue
        per_voice[voice] = per_voice.get(voice, 0) + 1
        chosen.append(c)
    if len(chosen) < count:
        raise ValueError(f"only {len(chosen)} pairs qualify (need {count})")
    return sorted(chosen[:count], key=lambda c: c["stem"])


def build_session(
    pairs: list[dict],
    output: Path,
    key_path: Path,
    *,
    session: str,
    seed: int,
    repeats: int = 2,
) -> dict:
    """``pairs``: ``{"stem", "files": {arm: path}, "comb": {arm: dB}}`` (2 arms)."""
    output, key_path = Path(output), Path(key_path)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    if key_path.resolve().is_relative_to(output.resolve()):
        raise ValueError("the key must be written outside the page directory")
    rng = random.Random(seed)
    order = list(pairs)
    rng.shuffle(order)
    # Balance sides exactly: half the pairs put the higher-comb file on A.
    sides = [i < len(order) // 2 for i in range(len(order))]
    rng.shuffle(sides)
    items = [
        (pair, high_on_a, None) for pair, high_on_a in zip(order, sides, strict=True)
    ]
    for index in rng.sample(range(len(order)), repeats):
        original = next(i for i, item in enumerate(items) if item[0] is order[index])
        items.insert(
            rng.randint(original + 1, len(items)), (order[index], sides[index], index)
        )

    (output / "audio").mkdir(parents=True, exist_ok=True)

    def audio_name(path: Path) -> str:
        digest = hashlib.sha256(
            f"{session}\0{Path(path).resolve()}".encode()
        ).hexdigest()
        target = output / "audio" / f"{digest[:16]}.wav"
        if not target.exists():
            _prepare_audio(Path(path), target)
        return f"audio/{target.name}"

    page_trials, key_trials, first_id = [], [], {}
    for number, (pair, high_on_a, repeat_index) in enumerate(items):
        trial_id = f"t{number:03d}"
        high, low = sorted(pair["comb"], key=pair["comb"].get, reverse=True)
        a_arm, b_arm = (high, low) if high_on_a else (low, high)
        page_trials.append(
            {
                "id": trial_id,
                "a": audio_name(pair["files"][a_arm]),
                "b": audio_name(pair["files"][b_arm]),
            }
        )
        if repeat_index is None:
            first_id[id(pair)] = trial_id
        key_trials.append(
            {
                "trial": trial_id,
                "stem": pair["stem"],
                "a": a_arm,
                "b": b_arm,
                "comb": pair["comb"],
                "higher_comb": "a" if high_on_a else "b",
                "repeat_of": None if repeat_index is None else first_id[id(pair)],
            }
        )
    key = {"session": session, "seed": seed, "trials": key_trials}
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    page = _PAGE.replace("__SESSION__", json.dumps(session)).replace(
        "__TRIALS__", json.dumps(page_trials)
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    return key


def score(key: dict, answers: dict) -> dict:
    if answers.get("session") != key["session"]:
        raise ValueError("answers belong to another session")
    given = answers.get("answers", {})
    for trial in key["trials"]:
        if given.get(trial["trial"]) not in ("a", "b"):
            raise ValueError(f"missing or invalid answer for {trial['trial']}")
    originals = [t for t in key["trials"] if t["repeat_of"] is None]
    hits = sum(given[t["trial"]] == t["higher_comb"] for t in originals)
    repeats = [t for t in key["trials"] if t["repeat_of"] is not None]
    same = sum(given[t["trial"]] == given[t["repeat_of"]] for t in repeats)
    return {
        "session": key["session"],
        "n": len(originals),
        "agreement": hits / len(originals),
        "wilson95": _wilson(hits, len(originals)),
        "repeat_pairs": len(repeats),
        "repeat_agreement": same / len(repeats) if repeats else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--arm", action="append", required=True, metavar="NAME=DIR")
    build.add_argument("--count", type=int, default=20)
    build.add_argument("--min-diff", type=float, default=0.67)
    build.add_argument("--max-per-voice", type=int, default=4)
    build.add_argument("--repeats", type=int, default=2)
    build.add_argument("--seed", type=int, required=True)
    build.add_argument("--session", default="noise")
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--key", type=Path, required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("--key", type=Path, required=True)
    scoring.add_argument("--answers", type=Path, required=True)
    scoring.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "build":
        from .measure_comb_artifacts import score_file  # noqa: PLC0415

        arms = dict(item.split("=", 1) for item in args.arm)
        if len(arms) != 2:
            raise SystemExit("exactly two --arm values are required")
        files: dict[str, dict[str, Path]] = {}
        scores: dict[str, dict[str, float]] = {}
        for arm, directory in arms.items():
            for path in sorted(Path(directory).glob("*.wav")):
                metrics = score_file(path)
                files.setdefault(path.stem, {})[arm] = path
                if metrics is not None:
                    scores.setdefault(path.stem, {})[arm] = metrics["comb_excess_db"]
        arm_x, arm_y = arms
        pairs = select_pairs(
            scores,
            arm_x,
            arm_y,
            count=args.count,
            min_diff=args.min_diff,
            max_per_voice=args.max_per_voice,
            seed=args.seed,
        )
        for pair in pairs:
            pair["files"] = files[pair["stem"]]
        build_session(
            pairs,
            args.output,
            args.key,
            session=args.session,
            seed=args.seed,
            repeats=args.repeats,
        )
        print(f"{len(pairs)} pairs -> {args.output / 'index.html'}")
        return 0

    key = json.loads(args.key.read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    text = json.dumps(score(key, answers), ensure_ascii=False, indent=1)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0


_PAGE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>雑音の聞き比べ</title>
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
<h1>雑音の聞き比べ</h1>
<p class="muted">同じ文を読んだ 2 つの音声 (A と B) を聞き、ざらつき・がびがびした雑音が
多いのはどちらかを選んでください。声の似方や話し方ではなく、雑音の多さで判断して
ください。差が分からないときも、どちらか近い方を選んでください。キーボードの 1 (A) /
2 (B) でも答えられます。</p>
<div class="bar" aria-hidden="true"><div id="progress"></div></div>
<p class="muted" id="count"></p>
<section class="card">
  <div class="play">
    <button id="playA">A を再生</button>
    <button id="playB">B を再生</button>
    <button id="playAB">A → B を再生</button>
  </div>
  <div class="answers">
    <button data-v="a">1 A の方が雑音が多い</button>
    <button data-v="b">2 B の方が雑音が多い</button>
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
const STORE = "listening-noise-ab-" + SESSION;
let state = { answers: {}, index: 0, started: new Date().toISOString() };
try { const saved = localStorage.getItem(STORE); if (saved) state = JSON.parse(saved); } catch (e) {}
const audioA = new Audio(), audioB = new Audio();
function persist() { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) {} }
function done() { return TRIALS.filter(t => state.answers[t.id]).length; }
function render() {
  const t = TRIALS[state.index];
  audioA.src = t.a; audioB.src = t.b;
  document.getElementById("count").textContent =
    "組 " + (state.index + 1) + " / " + TRIALS.length + "(回答済み " + done() + ")";
  document.getElementById("progress").style.width = (100 * done() / TRIALS.length) + "%";
  document.querySelectorAll(".answers button").forEach(b =>
    b.classList.toggle("chosen", b.dataset.v === state.answers[t.id]));
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
document.querySelectorAll(".answers button").forEach(b => b.onclick = () => answer(b.dataset.v));
document.getElementById("prev").onclick = () => { if (state.index > 0) { state.index -= 1; persist(); render(); } };
document.getElementById("next").onclick = () => { if (state.index < TRIALS.length - 1) { state.index += 1; persist(); render(); } };
document.addEventListener("keydown", e => { if (e.key === "1") answer("a"); if (e.key === "2") answer("b"); });
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
