# Swedish per-word LID parity (Issue #539) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swedish (sv) の per-word 言語検出を全ランタイムで単一の canonical 仕様に統一し、`å`/`ä`/`ö` を含むスウェーデン語が全経路で sv として一致して音素化されるようにする (cross-runtime parity 回復 + 再発防止 gate)。

**Architecture:** canonical な関数語リストを JSON データファイル (`sv_function_words.json`) に外出しし、全 7 ランタイム (Python training/runtime, Rust, Go, C++, C#, WASM) がこれをロード。検出は **conservative policy** — `å`/`Å` + 関数語のみ strong indicator、`ä`/`ö` 単独は不可。char レベル segmenter の後段に word-level post-pass を置く (#297 設計を踏襲)。ZH-EN loanword と同型の `_mirror_check` ベース sync gate で JSON の byte-identical を強制。

**Tech Stack:** Python (uv / pytest), Rust (cargo), Go (go test), C++ (CMake/ctest), C# (xUnit v3 / net10.0), JS (node test), TOML contract + `scripts/_mirror_check.py`。

---

## 設計判断 (確定済み)

Issue #539 の調査で確定した方針 (ユーザ承認済み):

1. **conservative policy**: `å`/`Å` を含む語、または関数語リスト完全一致のみを sv の strong indicator とする。`ä`/`ö`/`Ä`/`Ö` は独語・芬語・借用語と共有するため**単独では sv にしない** (char レベルでは従来通り default_latin に落ち、関数語リストに載っている ä/ö 語のみ救済)。
2. **canonical 関数語リスト = 46語**: 既存 C++/C# の byte-identical な 45語 + `är` (スウェーデン語頻度第3位の頻出 ä 語。受け入れ条件「ä/ö を含む語が sv として一致」を満たすために明示追加)。
3. **canonical = Python**。全ランタイムが JSON をミラーし、Python (training) の `src/python/g2p/piper_plus_g2p/data/sv_function_words.json` を source of truth とする。
4. **検出有効化条件** (全ランタイム共通、現状維持): `detect_swedish = ("sv" in languages) and (count of languages in {en,es,pt,fr,sv}) >= 2`。

### Canonical アルゴリズム仕様 (全ランタイム共通・厳密版)

char レベル `detect_char` は**変更しない** (`å`/`ä`/`ö` は従来通り `default_latin` を返す)。`segment_text` の末尾に post-pass を追加:

```
refine_latin_segments_for_swedish(segments):
  if not detect_swedish: return segments        # 呼び出し側でガード
  if default_latin_language == "sv": return segments
  for each (lang, text) in segments:
    if lang != default_latin_language: keep (lang, text); continue
    strong = False
    for word in text.split():                    # 空白分割
      w = strip_ascii_punct(word, ".,;:!?").lower()   # 前後の .,;:!? を除去 → 小文字化
      if w == "": continue
      if w in FUNCTION_WORDS: strong = True; break     # 完全一致 = strong
      if any(c in STRONG_CHARS for c in w): strong = True; break  # å/Å = strong
      # ä/ö は無視 (weak)
    if strong: emit ("sv", text)                 # セグメント全体を sv に
    else:      emit (default_latin_language, text)
  return result
```

`STRONG_CHARS = {"å","Å"}`、`FUNCTION_WORDS` = JSON の 46 語。

### Canonical データファイル内容

`src/python/g2p/piper_plus_g2p/data/sv_function_words.json`:

```json
{
  "schema_version": 1,
  "strong_chars": ["å", "Å"],
  "function_words": [
    "och", "att", "jag", "det", "den", "inte", "som", "han", "hon",
    "var", "har", "kan", "ska", "med", "för", "sig", "sin", "min",
    "din", "vill", "från", "när", "här", "där", "också", "alla",
    "denna", "efter", "eller", "under", "utan", "mycket", "mellan",
    "genom", "bara", "sedan", "redan", "aldrig", "alltid", "igen",
    "något", "några", "varje", "vilken", "vilket", "är"
  ]
}
```

> JSON は `\uXXXX` エスケープではなく **UTF-8 リテラル** (`för`, `från`, `när`, `är` …) で書く (loanword JSON と同様、`ensure_ascii=false` 相当)。上記はドキュメント表記の都合でエスケープ表示。実ファイルは UTF-8 生文字で保存し、全ミラーと byte-identical にする。`strong_chars` = `å`, `Å`。

---

## File Structure

### 新規作成

| パス | 責務 |
|------|------|
| `src/python/g2p/piper_plus_g2p/data/sv_function_words.json` | **canonical** 関数語 + strong_chars |
| `src/python_run/piper/phonemize/data/sv_function_words.json` | Python runtime ミラー |
| `src/rust/piper-plus-g2p/data/sv_function_words.json` | Rust g2p crate ミラー |
| `src/rust/piper-core/data/sv_function_words.json` | Rust core crate ミラー |
| `src/go/phonemize/data/sv_function_words.json` | Go ミラー |
| `src/csharp/PiperPlus.Core/Phonemize/Data/sv_function_words.json` | C# ミラー |
| `src/wasm/g2p/data/sv_function_words.json` | WASM ミラー |
| `src/cpp/data/sv_function_words.json` | C++ ミラー |
| `docs/spec/swedish-lid-mirrors.toml` | mirror 宣言 (gate 入力) |
| `scripts/check_swedish_lid_consistency.py` | thin wrapper gate |
| `.github/workflows/swedish-lid-sync.yml` | CI gate |
| `tests/fixtures/g2p/swedish_lid_matrix.json` | cross-runtime parity fixture (canonical) |
| 各ランタイム配下の fixture ミラー (Phase 8 で列挙) | parity fixture mirror |

### 修正

| パス | 変更 |
|------|------|
| `src/python/g2p/piper_plus_g2p/multilingual.py` | JSON ロード + conservative post-pass 復元 |
| `src/python_run/piper/phonemize/multilingual.py` | 同上 (regex スタイルに合わせて) |
| `src/rust/piper-plus-g2p/src/multilingual.rs` | conservative 検出復元 + JSON ロード |
| `src/rust/piper-core/...` (multilingual re-export 経路) | 同上 (crate 構成に従う) |
| `src/go/phonemize/unicode_detect.go` | 12→46語 (JSON ロード), conservative 維持 |
| `src/cpp/language_detector.cpp` / `.hpp` | lenient→conservative + JSON ロード |
| `src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` | lenient→conservative + JSON ロード |
| `src/wasm/g2p/src/detect.js` | char単位→word単位 post-pass + JSON ロード |
| `.github/workflows/ci.yml` | swedish-lid gate を job に追加 (loanword gate と並べる) |
| `CHANGELOG.md` (各パッケージ) | unreleased エントリ |

> **JSON ロード実装の指針 (全ランタイム共通):** 既存の ZH-EN loanword JSON ロード機構を**そのまま踏襲**する。各ランタイムの loanword ローダー (`zh_en_loanword.json` を読む既存コード) を参照し、同じディレクトリ規約・同じ forward-compat (unknown フィールド黙認 / `schema_version` 後方互換) で `sv_function_words.json` を読む。実行時は subagent がまず該当ランタイムの loanword ローダーを Read してパターンを確認すること。

---

## Phase 0: Canonical データ + Python training canonical (本体バグ修正)

**Files:**
- Create: `src/python/g2p/piper_plus_g2p/data/sv_function_words.json`
- Modify: `src/python/g2p/piper_plus_g2p/multilingual.py`
- Test: `src/python/g2p/tests/test_swedish_lid.py` (新規)

- [ ] **Step 0.1: canonical JSON を作成**

`src/python/g2p/piper_plus_g2p/data/sv_function_words.json` を上記「Canonical データファイル内容」の通り UTF-8 生文字で作成 (46語、`strong_chars`=å/Å、`schema_version`=1)。

- [ ] **Step 0.2: 失敗するテストを書く**

`src/python/g2p/tests/test_swedish_lid.py`:

```python
"""Swedish per-word LID (conservative policy) — Issue #539 regression tests."""

from piper_plus_g2p.multilingual import MultilingualPhonemizer


def _langs(text):
    phon = MultilingualPhonemizer(["en", "sv"], default_latin_language="en")
    return [s["language"] for s in phon.segment_text(text)]


def test_strong_char_a_ring_detected_as_swedish():
    # å is a strong indicator
    assert "sv" in _langs("så")
    assert "sv" in _langs("från")


def test_function_word_detected_as_swedish():
    # function words without å/ä/ö
    assert _langs("och") == ["sv"]
    assert _langs("jag") == ["sv"]
    assert _langs("inte") == ["sv"]


def test_function_words_with_diacritics_detected():
    # ä/ö words that ARE in the 46-word list (rescued by exact match)
    assert _langs("för") == ["sv"]   # ö, in list
    assert _langs("när") == ["sv"]   # ä, in list
    assert _langs("är") == ["sv"]    # ä, explicitly added (46th word)


def test_bare_umlaut_not_swedish_conservative():
    # ä/ö-only words NOT in the list must NOT be classified as Swedish
    # (German/loanword false-positive guard). "Mädchen" is German.
    assert "sv" not in _langs("Mädchen")
    assert "sv" not in _langs("schön")


def test_detection_requires_sv_in_language_set():
    # When sv is absent, no Swedish reclassification happens.
    phon = MultilingualPhonemizer(["en", "es"], default_latin_language="en")
    langs = [s["language"] for s in phon.segment_text("från")]
    assert "sv" not in langs


def test_sentence_reclassified_whole_segment():
    # one strong indicator promotes the whole Latin segment
    assert _langs("jag heter Anna") == ["sv"]
```

- [ ] **Step 0.3: テスト失敗を確認**

Run: `cd src/python/g2p && uv run pytest tests/test_swedish_lid.py -v`
Expected: FAIL (現状 `så`/`och` 等が `["en"]` になる)

- [ ] **Step 0.4: multilingual.py に conservative 検出を実装**

`src/python/g2p/piper_plus_g2p/multilingual.py` を編集:

(a) モジュール先頭付近にローダーを追加 (loanword ローダーの規約に合わせ `importlib.resources` か `Path(__file__).parent / "data"` のどちらか既存方式を踏襲):

```python
import json
from pathlib import Path

_SV_DATA_PATH = Path(__file__).parent / "data" / "sv_function_words.json"


def _load_sv_lid_data() -> tuple[frozenset[str], frozenset[str]]:
    """Load canonical Swedish function words + strong chars.

    Forward-compat: unknown top-level keys and absent/extra fields are
    ignored (mirrors the zh_en_loanword loader policy).
    """
    data = json.loads(_SV_DATA_PATH.read_text(encoding="utf-8"))
    words = frozenset(w.lower() for w in data.get("function_words", []))
    strong = frozenset(data.get("strong_chars", []))
    return words, strong


_SV_FUNCTION_WORDS, _SV_STRONG_CHARS = _load_sv_lid_data()
```

(b) `UnicodeLanguageDetector.__init__` に sv フラグ追加:

```python
        self._has_sv = "sv" in self.languages
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr", "sv")
        }
        self._detect_swedish = self._has_sv and len(self._latin_languages) >= 2
```

(c) `_segment_text_multilingual` の `return segments` 直前に post-pass を追加:

```python
    if detector._detect_swedish:
        segments = _refine_latin_segments_for_swedish(segments, detector)

    return segments
```

(d) モジュールレベル関数を追加 (conservative 版):

```python
def _refine_latin_segments_for_swedish(
    segments: list[tuple[str, str]],
    detector: "UnicodeLanguageDetector",
) -> list[tuple[str, str]]:
    """Re-classify default-Latin segments as Swedish (conservative).

    Strong indicators (sufficient): å/Å, or an exact function-word match.
    Weak chars ä/ö are NOT sufficient on their own (shared with German etc.).
    """
    default = detector.default_latin_language
    if default == "sv":
        return segments

    result: list[tuple[str, str]] = []
    for lang, text in segments:
        if lang != default:
            result.append((lang, text))
            continue
        strong = False
        for word in text.split():
            w = word.strip(".,;:!?").lower()
            if not w:
                continue
            if w in _SV_FUNCTION_WORDS:
                strong = True
                break
            if any(c in _SV_STRONG_CHARS for c in w):
                strong = True
                break
        result.append(("sv", text) if strong else (default, text))
    return result
```

- [ ] **Step 0.5: テスト合格を確認**

Run: `cd src/python/g2p && uv run pytest tests/test_swedish_lid.py -v`
Expected: PASS (6 件)

- [ ] **Step 0.6: 既存テストの非破壊を確認**

Run: `cd src/python/g2p && uv run pytest tests/test_swedish.py tests/ -q`
Expected: PASS (回帰なし)

- [ ] **Step 0.7: Commit**

```bash
git add src/python/g2p/piper_plus_g2p/data/sv_function_words.json \
        src/python/g2p/piper_plus_g2p/multilingual.py \
        src/python/g2p/tests/test_swedish_lid.py
git commit -m "fix(g2p): restore Swedish per-word LID in canonical Python (conservative, #539)"
```

---

## Phase 1: Python runtime mirror

**Files:**
- Create: `src/python_run/piper/phonemize/data/sv_function_words.json` (Phase 0 の byte-identical コピー)
- Modify: `src/python_run/piper/phonemize/multilingual.py` (regex スタイル)
- Test: `src/python/tests/test_swedish_lid_runtime.py` (新規) または既存 runtime テストに追加

- [ ] **Step 1.1: JSON ミラーをコピー**

```bash
cp src/python/g2p/piper_plus_g2p/data/sv_function_words.json \
   src/python_run/piper/phonemize/data/sv_function_words.json
```

- [ ] **Step 1.2: 失敗テストを書く** — Phase 0 の `test_swedish_lid.py` と同じケースを runtime import パス (`from piper.phonemize.multilingual import ...`) で。

- [ ] **Step 1.3: テスト失敗を確認** — Run: `uv run pytest src/python/tests/test_swedish_lid_runtime.py -v` → FAIL

- [ ] **Step 1.4: 実装** — runtime の `multilingual.py` は `re.compile` スタイル。Phase 0 と同一の `_load_sv_lid_data` / `_refine_latin_segments_for_swedish` / `_detect_swedish` を移植 (char detect の regex `_RE_LATIN` は不変、post-pass のみ追加)。

- [ ] **Step 1.5: テスト合格を確認** — PASS

- [ ] **Step 1.6: Commit**

```bash
git add src/python_run/piper/phonemize/data/sv_function_words.json \
        src/python_run/piper/phonemize/multilingual.py \
        src/python/tests/test_swedish_lid_runtime.py
git commit -m "fix(g2p): mirror Swedish per-word LID into Python runtime (#539)"
```

---

## Phase 2: Rust (piper-plus-g2p + piper-core)

**Files:**
- Create: `src/rust/piper-plus-g2p/data/sv_function_words.json`, `src/rust/piper-core/data/sv_function_words.json`
- Modify: `src/rust/piper-plus-g2p/src/multilingual.rs` (+ piper-core 経路が独自実装なら同様)
- Test: `src/rust/piper-plus-g2p/tests/test_swedish_lid.rs` (新規)

> 参照: #297 原典 Rust (`git show c3f44bb:src/rust/.../multilingual.rs`) に 45語 + `SWEDISH_CHARS` の実装あり。これを **conservative 化** (ä/ö を strong から除外、å のみ) + JSON ロード化して復元。

- [ ] **Step 2.1: JSON ミラーをコピー** (Phase 0 と byte-identical)

- [ ] **Step 2.2: 失敗テストを書く** (`tests/test_swedish_lid.rs`):

```rust
use piper_plus_g2p::multilingual::{segment_text, UnicodeLanguageDetector};

fn langs(text: &str) -> Vec<String> {
    let det = UnicodeLanguageDetector::new(&["en", "sv"], "en");
    segment_text(text, &det).into_iter().map(|(l, _)| l).collect()
}

#[test]
fn a_ring_is_strong() { assert!(langs("så").contains(&"sv".to_string())); }

#[test]
fn function_word_detected() { assert_eq!(langs("och"), vec!["sv"]); }

#[test]
fn umlaut_word_in_list_detected() { assert_eq!(langs("är"), vec!["sv"]); }

#[test]
fn bare_umlaut_not_swedish() { assert!(!langs("schön").contains(&"sv".to_string())); }
```

> ※ `UnicodeLanguageDetector::new` / `segment_text` の正確なシグネチャは現行 `multilingual.rs` に合わせて調整 (現状 `detect_char`/`segment_text` あり)。

- [ ] **Step 2.3: テスト失敗を確認** — Run: `cd src/rust && cargo test -p piper-plus-g2p test_swedish_lid` → FAIL (現状 sv 未検出)

- [ ] **Step 2.4: 実装** — `multilingual.rs` に:
  - JSON を `include_str!("../data/sv_function_words.json")` で埋め込み (loanword crate の既存方式に合わせる。ランタイム読込なら踏襲), `serde_json` でパース → `HashSet<String>` + strong chars。
  - `detect_swedish: bool` フィールド (`has_sv && latin_count >= 2`) を構造体に復元。
  - `segment_text` 末尾に `refine_latin_segments_for_swedish` post-pass (conservative: 関数語 or å/Å のみ strong)。

- [ ] **Step 2.5: テスト合格 + clippy** — Run: `cd src/rust && cargo test -p piper-plus-g2p && cargo clippy -p piper-plus-g2p -- -D warnings` → PASS

- [ ] **Step 2.6: piper-core 経路の確認** — `multilingual` を re-export しているか独自実装か確認。独自なら同等変更 + JSON ミラー。re-export なら JSON ミラーのみ (loanword と同じ 2-crate 重複規約)。

- [ ] **Step 2.7: Commit**

```bash
git add src/rust/piper-plus-g2p/data/sv_function_words.json \
        src/rust/piper-core/data/sv_function_words.json \
        src/rust/piper-plus-g2p/src/multilingual.rs \
        src/rust/piper-plus-g2p/tests/test_swedish_lid.rs
git commit -m "fix(g2p): restore Swedish per-word LID in Rust (conservative, #539)"
```

---

## Phase 3: Go (12→46 語に拡張、JSON ロード化)

**Files:**
- Create: `src/go/phonemize/data/sv_function_words.json`
- Modify: `src/go/phonemize/unicode_detect.go`
- Test: `src/go/phonemize/unicode_detect_test.go` (既存に追加)

> Go は既に conservative (`svUniqueChars`=å/Å, ä/ö 除外) なので **policy は正しい**。問題は関数語が 12 語しかない点。これを canonical 46 語の JSON ロードに置換。

- [ ] **Step 3.1: JSON ミラーをコピー** (byte-identical)

- [ ] **Step 3.2: 失敗テストを書く** — `unicode_detect_test.go` に追加:

```go
func TestSwedishLID_FunctionWordsExpanded(t *testing.T) {
	det := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	cases := map[string]bool{"för": true, "är": true, "när": true, "och": true, "så": true, "schön": false}
	for word, wantSv := range cases {
		segs := det.SegmentText(word)
		gotSv := false
		for _, s := range segs {
			if s.Language == "sv" { gotSv = true }
		}
		if gotSv != wantSv {
			t.Errorf("%q: got sv=%v want %v", word, gotSv, wantSv)
		}
	}
}
```

> ※ `för`/`när` は現行 Go の 12 語に無く、ö/ä は weak なので現状 `en` → このテストは現状 FAIL する。

- [ ] **Step 3.3: テスト失敗を確認** — Run: `cd src/go && go test ./phonemize/ -run TestSwedishLID_FunctionWordsExpanded -v` → FAIL

- [ ] **Step 3.4: 実装** — `svDetectFunctionWords` のハードコード 12 語マップを削除し、`sv_function_words.json` を `embed` (`//go:embed data/sv_function_words.json`) でロードして 46 語マップを構築。`svUniqueChars` は JSON `strong_chars` から構築 (å/Å 維持)。`refineLatinSegmentsForSwedish` のロジック (conservative) は不変。loanword の Go ローダー規約に合わせる。

- [ ] **Step 3.5: テスト合格** — Run: `cd src/go && go test ./phonemize/...` → PASS

- [ ] **Step 3.6: Commit**

```bash
git add src/go/phonemize/data/sv_function_words.json src/go/phonemize/unicode_detect.go src/go/phonemize/unicode_detect_test.go
git commit -m "fix(g2p): expand Go Swedish LID to canonical 46-word list (#539)"
```

---

## Phase 4: C++ (lenient→conservative + JSON ロード)

**Files:**
- Create: `src/cpp/data/sv_function_words.json`
- Modify: `src/cpp/language_detector.cpp`, `src/cpp/language_detector.hpp`
- Test: `src/cpp/tests/test_language_detector*.cpp` (既存に追加、CMakeLists に既存なら不要)

> C++ は現状 lenient (`isSwedishChar` に ä/ö/å 全部)。**conservative 化**: post-pass の char 判定を `å`/`Å` のみに変更。関数語は 45→46 (JSON ロード)。

- [ ] **Step 4.1: JSON ミラーをコピー** (byte-identical)

- [ ] **Step 4.2: 失敗テストを書く** — 既存テストファイルに:

```cpp
TEST_CASE("Swedish LID is conservative on bare umlauts") {
    UnicodeLanguageDetector det({"en", "sv"}, "en");
    // "schön" (German) has ö but is NOT Swedish under conservative policy
    auto segs = det.segmentText("schön");
    bool hasSv = false;
    for (auto& s : segs) if (s.lang == "sv") hasSv = true;
    CHECK_FALSE(hasSv);
    // "är" (in 46-word list) IS Swedish
    CHECK(detectDominantLanguage("är", det) == "sv");
}
```

- [ ] **Step 4.3: テスト失敗を確認** — Run: CMake build + `ctest -R language_detector` → FAIL (現状 "schön" の ö が sv 判定)

- [ ] **Step 4.4: 実装**:
  - `isSwedishChar` を `å`/`Å` のみ (0x00E5/0x00C5) に変更、関数名を `isSwedishStrongChar` にリネーム (意味明確化)。`SWEDISH_FUNCTION_WORDS` のハードコードを削除し JSON (`sv_function_words.json`) ロードに置換 (loanword C++ ローダー規約に合わせる)。`är` 追加で 46 語。
  - `refineLatinSegmentsForSwedish` のロジック (関数語 or strong char) は不変。

- [ ] **Step 4.5: テスト合格** — `ctest -R language_detector` → PASS

- [ ] **Step 4.6: Commit**

```bash
git add src/cpp/data/sv_function_words.json src/cpp/language_detector.cpp src/cpp/language_detector.hpp src/cpp/tests/
git commit -m "fix(g2p): make C++ Swedish LID conservative + JSON-load (#539)"
```

---

## Phase 5: C# (lenient→conservative + JSON ロード)

**Files:**
- Create: `src/csharp/PiperPlus.Core/Phonemize/Data/sv_function_words.json`
- Modify: `src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs`
- Test: `src/csharp/PiperPlus.Core.Tests/UnicodeLanguageDetectorTests.cs` (新規/既存)

> C# も lenient。conservative 化 + JSON ロード。

- [ ] **Step 5.1: JSON ミラーをコピー** + `.csproj` に `<EmbeddedResource>` or `<Content CopyToOutputDirectory>` 登録 (loanword JSON の登録方式に合わせる)。

- [ ] **Step 5.2: 失敗テストを書く**:

```csharp
[Fact]
public void SwedishLid_IsConservativeOnBareUmlaut()
{
    var det = new UnicodeLanguageDetector(new[] { "en", "sv" }, "en");
    // German "schön" must NOT become sv
    Assert.DoesNotContain("sv", det.SegmentText("schön").Select(s => s.Lang));
    // "är" (in list) must be sv
    Assert.Contains("sv", det.SegmentText("är").Select(s => s.Lang));
}
```

- [ ] **Step 5.3: テスト失敗を確認** — Run: `cd src/csharp && dotnet test --filter SwedishLid_IsConservativeOnBareUmlaut` → FAIL

- [ ] **Step 5.4: 実装**:
  - `SwedishChars` を strong (`å`/`Å`) のみに縮小 → `SwedishStrongChars`。`SwedishFunctionWords` ハードコードを JSON ロードに置換 (46語)。loanword C# ローダー規約に合わせる。
  - `RefineLatinSegmentsForSwedish` の `hasSwedishChar` 判定を strong chars のみに変更 (ä/ö を除外)。

- [ ] **Step 5.5: テスト合格** — `dotnet test` → PASS

- [ ] **Step 5.6: Commit**

```bash
git add src/csharp/PiperPlus.Core/Phonemize/Data/sv_function_words.json \
        src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs \
        src/csharp/PiperPlus.Core/PiperPlus.Core.csproj \
        src/csharp/PiperPlus.Core.Tests/
git commit -m "fix(g2p): make C# Swedish LID conservative + JSON-load (#539)"
```

---

## Phase 6: WASM/npm (char単位→word単位 post-pass)

**Files:**
- Create: `src/wasm/g2p/data/sv_function_words.json`
- Modify: `src/wasm/g2p/src/detect.js`
- Test: `src/wasm/g2p/test/test-detect.js` (既存に追加)

> WASM は char 単位 (`_isSwedishSpecific` で å/ä/ö を即 sv)。これが (1) 単語分断、(2) 関数語 (och 等) 未検出 を起こす。**word 単位 post-pass に置換**して他ランタイムと統一。

- [ ] **Step 6.1: JSON ミラーをコピー** (byte-identical) + bundler が `data/` を含めるか確認 (loanword JSON の同梱方式に合わせる)。

- [ ] **Step 6.2: 失敗テストを書く** — `test-detect.js`:

```js
import { UnicodeLanguageDetector } from "../src/detect.js";

const det = new UnicodeLanguageDetector(["en", "sv"], { defaultLatinLanguage: "en" });
const langs = (t) => det.segmentText(t).map((s) => s.language);

test("för is a single sv segment (not fragmented)", () => {
  expect(langs("för")).toEqual(["sv"]);   // 現状: ["en","sv","en"]
});
test("function word och detected (no special char)", () => {
  expect(langs("och")).toEqual(["sv"]);   // 現状: ["en"]
});
test("bare umlaut word not swedish", () => {
  expect(langs("schön")).not.toContain("sv");  // 現状: 分断 + sv 混入
});
```

- [ ] **Step 6.3: テスト失敗を確認** — Run: `cd src/wasm/g2p && npm test -- test-detect` → FAIL

- [ ] **Step 6.4: 実装**:
  - `_isSwedishSpecific` を `detectChar` から削除 (char レベルでは å/ä/ö → default_latin に戻す。`_isLatin` が既に包含)。
  - JSON `sv_function_words.json` をロード (`_svFunctionWords` Set, `_svStrongChars` Set)。`_detectSwedish = _hasSv && latinCount >= 2` を constructor に追加。
  - `segmentText` 末尾に `_refineLatinSegmentsForSwedish(segments)` を追加 (conservative: 関数語 or å/Å)。`detectLanguage` も同様に post-pass を通すか要検討 (今回は segmentText 経路を canonical に)。

- [ ] **Step 6.5: テスト合格** — `npm test` → PASS (既存 detect テストの char 単位前提があれば更新)

- [ ] **Step 6.6: Commit**

```bash
git add src/wasm/g2p/data/sv_function_words.json src/wasm/g2p/src/detect.js src/wasm/g2p/test/test-detect.js
git commit -m "fix(g2p): switch WASM Swedish LID to word-level post-pass (#539)"
```

---

## Phase 7: Sync gate (byte-identical 強制)

**Files:**
- Create: `docs/spec/swedish-lid-mirrors.toml`, `scripts/check_swedish_lid_consistency.py`, `.github/workflows/swedish-lid-sync.yml`
- Modify: `.github/workflows/ci.yml` (gate job 追加)

> `scripts/check_loanword_consistency.py` + `docs/spec/loanword-mirrors.toml` を雛形に複製。

- [ ] **Step 7.1: mirror 宣言 TOML を作成** — `docs/spec/swedish-lid-mirrors.toml`:

```toml
[meta]
forward_compat_policy = "strict"
schema_version = 1

[[groups]]
name = "sv_function_words runtime data (8 mirrors)"
canonical = "src/python/g2p/piper_plus_g2p/data/sv_function_words.json"
mirrors = [
  "src/python_run/piper/phonemize/data/sv_function_words.json",
  "src/rust/piper-plus-g2p/data/sv_function_words.json",
  "src/rust/piper-core/data/sv_function_words.json",
  "src/go/phonemize/data/sv_function_words.json",
  "src/csharp/PiperPlus.Core/Phonemize/Data/sv_function_words.json",
  "src/wasm/g2p/data/sv_function_words.json",
  "src/cpp/data/sv_function_words.json",
]
incident_refs = ["Issue #539", "PR #297 (regression introduced by #300)"]
notes = "Conservative policy: strong_chars=å/Å + function_words; ä/ö weak."
```

- [ ] **Step 7.2: wrapper gate を作成** — `scripts/check_swedish_lid_consistency.py` (loanword wrapper を複製、schema validator を sv 形に: `function_words` は list[str]、`strong_chars` は list[str]、`schema_version` 後方互換)。`run_from_toml("docs/spec/swedish-lid-mirrors.toml")` に委譲。`--fix` で canonical → 7 ミラー同期。

- [ ] **Step 7.3: gate がパスすることを確認** — Run: `python scripts/check_swedish_lid_consistency.py` → exit 0 (全ミラー一致)

- [ ] **Step 7.4: gate の検出力を確認 (negative test)** — 1 ミラーを意図的に 1 語削って実行 → exit 1 を確認 → `--fix` で復旧 → exit 0。

- [ ] **Step 7.5: CI 配線** — `.github/workflows/swedish-lid-sync.yml` を `zh-en-loanword-sync.yml` を雛形に作成。`ci.yml` の該当 job 群に gate を追加。

- [ ] **Step 7.6: Commit**

```bash
git add docs/spec/swedish-lid-mirrors.toml scripts/check_swedish_lid_consistency.py \
        .github/workflows/swedish-lid-sync.yml .github/workflows/ci.yml
git commit -m "ci(g2p): add Swedish LID sync gate (byte-identical mirrors, #539)"
```

---

## Phase 8: Cross-runtime parity fixture matrix

**Files:**
- Create: `tests/fixtures/g2p/swedish_lid_matrix.json` (canonical) + 各ランタイム fixture ミラー
- Modify: 各ランタイムの fixture-driven parity テスト (loanword matrix テストと同じ場所)

- [ ] **Step 8.1: canonical fixture を作成** — `tests/fixtures/g2p/swedish_lid_matrix.json`:

```json
{
  "schema_version": 1,
  "languages": ["en", "sv"],
  "default_latin": "en",
  "cases": [
    {"text": "så",    "expect_contains_sv": true},
    {"text": "från",  "expect_contains_sv": true},
    {"text": "för",   "expect_contains_sv": true},
    {"text": "när",   "expect_contains_sv": true},
    {"text": "är",    "expect_contains_sv": true},
    {"text": "och",   "expect_contains_sv": true},
    {"text": "jag heter Anna", "expect_contains_sv": true},
    {"text": "schön", "expect_contains_sv": false},
    {"text": "Mädchen", "expect_contains_sv": false},
    {"text": "hello world", "expect_contains_sv": false}
  ]
}
```

- [ ] **Step 8.2: fixture を各ランタイムへミラー** — loanword fixture matrix と同じ配置:
  `src/go/phonemize/testdata/`, `src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/`, `src/cpp/tests/fixtures/`, `src/wasm/g2p/test/fixtures/`, `src/rust/piper-plus-g2p/tests/fixtures/`, `src/rust/piper-core/tests/fixtures/`, (Python は canonical 直読)。swedish-lid-mirrors.toml に fixture group を追加。

- [ ] **Step 8.3: 各ランタイムで fixture-driven テストを追加** — fixture を読み、各 `text` の `expect_contains_sv` を検証。loanword matrix テストの構造を踏襲。

- [ ] **Step 8.4: 全ランタイムでテスト合格を確認**

```bash
cd src/python/g2p && uv run pytest -k swedish_lid -q
cd src/rust && cargo test swedish_lid
cd src/go && go test ./phonemize/... -run SwedishLid
cd src/csharp && dotnet test --filter SwedishLid
cd src/wasm/g2p && npm test -- swedish
# C++: ctest -R swedish_lid
```
Expected: 全 PASS、全ランタイムで同一 `expect_contains_sv` 結果

- [ ] **Step 8.5: gate に fixture group を含めて再実行** — `python scripts/check_swedish_lid_consistency.py` → exit 0

- [ ] **Step 8.6: Commit**

```bash
git add tests/fixtures/g2p/swedish_lid_matrix.json <各 fixture ミラー> <各テスト> docs/spec/swedish-lid-mirrors.toml
git commit -m "test(g2p): cross-runtime Swedish LID parity fixture matrix (#539)"
```

---

## Phase 9: CHANGELOG + ドキュメント + 仕上げ

- [ ] **Step 9.1: CHANGELOG unreleased エントリ** — 各パッケージ (`src/python/g2p/CHANGELOG.md`, ルート `CHANGELOG.md`, Rust/C#/Go/npm の該当 CHANGELOG) に "Fixed: Swedish per-word LID parity across runtimes (#539)" を追加 (CHANGELOG unreleased gate を満たす)。

- [ ] **Step 9.2: CLAUDE.md / G2P ドキュメント更新** — `CLAUDE.md` の G2P セクションに sv per-word LID + gate を追記。`docs/reference/` に Swedish LID の canonical/mirror マップを追加 (任意、loanword README に倣う)。

- [ ] **Step 9.3: pre-commit + 全 gate を full-repo 実行**

```bash
pre-commit run --all-files
python scripts/check_swedish_lid_consistency.py
```
Expected: 全 PASS

- [ ] **Step 9.4: docs/research の取り扱い確認** — `docs/README.md` 変更と `docs/research/` は本 PR と分離 (別途コミット or stash)。本ブランチには混ぜない。

- [ ] **Step 9.5: Commit + PR** — `/create-pr` skill で PR 作成 (pull_request_template.md 準拠、CI 監視ループまで)。

---

## Self-Review チェック結果

**Spec coverage (受け入れ条件 4 点):**
1. `å`/`ä`/`ö` 含む語が全ランタイムで sv 一致 → Phase 0-6 (統一アルゴリズム) + Phase 8 (parity fixture) ✓
2. function word リストが byte-identical (gate) → Phase 7 ✓
3. cross-runtime parity テスト green → Phase 8 ✓
4. canonical = Python → Phase 0 (Python が source of truth、他は JSON ミラー) ✓

**Issue 提案修正 6 点との対応:** (1) Python 復元=Phase 0/1、(2) Rust=Phase 2、(3) WASM 単語化=Phase 6、(4) C++/C#/Go 統一=Phase 3/4/5、(5) spec mirror+gate=Phase 7、(6) parity テスト=Phase 8。全網羅。

**既知の留意点 (executor 向け):**
- 各ランタイムの JSON ロード機構は **既存 loanword ローダーを必ず Read してから**踏襲 (ディレクトリ規約・embed/同梱方式・forward-compat がランタイム毎に違う)。
- `är` は canonical 46語の一部。テスト・fixture と JSON が常に一致するよう、語の増減は **canonical JSON のみ編集 → `--fix` で伝播**。
- conservative policy のため `ä`/`ö` のみの未知語 (例 独語 "schön") は **意図的に en**。これは仕様でありバグではない (negative test で固定)。
- 6lang モデルは sv 非含有 → 既定推論経路は不変 (dormant)。影響は sv を language set に含む G2P 利用・将来 sv モデルのみ。
