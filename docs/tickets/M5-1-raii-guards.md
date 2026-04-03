# M5-1: RAII ガード導入 (ConfigGuard / BusyGuard)

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- 保守性向上、バグの温床となる手動 save/restore を自動化
> **見積り:** 小
> **依存:** Phase 4 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

`piper_plus_c_api.cpp` 内に散在する手動の SynthesisConfig save/restore (`savedConfig` 復元 11 箇所 + `savedLangId` 復元 3 箇所 = 計 14 箇所) と `inProgress.store(false)` (17 箇所) を RAII クラスで自動化し、例外安全性と保守性を向上させる。

**現状:** `synthesize`, `synth_start`, `synth_next`, `synthesize_streaming`, `phonemize` の各関数で、`SynthesisConfig` の一時変更と復元を手動で行っている (`savedConfig` 復元 11 箇所、`phonemize` の `savedLangId` 復元 3 箇所)。`inProgress.store(false)` は 17 箇所に散在している。早期 return や例外発生時に restore が漏れるリスクがある。

**ゴール:** RAII クラスにより手動の `savedConfig` restore と `inProgress.store(false)` が 0 箇所になること。既存の動作は一切変更しないリファクタリングのみ。

---

## 2. 実装する内容の詳細

### 2.1 ConfigGuard クラス

```cpp
// piper_plus_c_api.cpp 内部 (anonymous namespace)
class ConfigGuard {
public:
    ConfigGuard(piper::SynthesisConfig &config)
        : config_(config), saved_(config) {}
    ~ConfigGuard() { config_ = saved_; }

    // コピー・ムーブ禁止
    ConfigGuard(const ConfigGuard &) = delete;
    ConfigGuard &operator=(const ConfigGuard &) = delete;

private:
    piper::SynthesisConfig &config_;
    piper::SynthesisConfig  saved_;
};
```

- デストラクタで `config_` を `saved_` に自動復元
- 例外・早期 return 時も確実に restore される

### 2.2 BusyGuard クラス

```cpp
// piper_plus_c_api.cpp 内部 (anonymous namespace)
class BusyGuard {
public:
    BusyGuard(std::atomic<bool> &flag) : flag_(flag) {
        bool expected = false;
        if (!flag_.compare_exchange_strong(expected, true)) {
            throw std::runtime_error("Engine is busy");
        }
    }
    ~BusyGuard() { flag_.store(false, std::memory_order_release); }

    BusyGuard(const BusyGuard &) = delete;
    BusyGuard &operator=(const BusyGuard &) = delete;

private:
    std::atomic<bool> &flag_;
};
```

- コンストラクタで `inProgress` を acquire (CAS)、失敗時は例外
- デストラクタで自動 release

### 2.3 適用対象関数

| 関数 | ConfigGuard | BusyGuard |
|------|:-----------:|:---------:|
| `piper_plus_synthesize` | o | o |
| `piper_plus_synth_start` | o | o |
| `piper_plus_synth_next` | - | - |
| `piper_plus_synthesize_streaming` | o | o |
| `piper_plus_phonemize` | o | - |

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus_c_api.cpp` | ConfigGuard / BusyGuard クラス追加、全関数の手動 save/restore を RAII に置換 |

**変更不要:** ヘッダー (`piper_plus.h`)、テストコード、その他のソースファイル。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | RAII クラス実装 + 既存コードのリファクタリング |

合計 1 名。純粋なリファクタリングで新規ロジックは不要。

---

## 4. 提供範囲とテスト項目

### スコープ

- ConfigGuard / BusyGuard の 2 クラスを `piper_plus_c_api.cpp` の anonymous namespace に追加
- 全関数の手動 save/restore を RAII に置換
- 動作変更なし (リファクタリングのみ)

### テスト

**新規テスト不要。** 既存テスト全 PASS で完了。

| 確認項目 | 方法 |
|----------|------|
| 既存ユニットテスト全 PASS | `ctest --test-dir build -R test_c_api` |
| 既存統合テスト全 PASS | `ctest --test-dir build -R test_c_api_integration` |
| 手動 restore が 0 箇所 | `grep -n 'savedConfig' src/cpp/piper_plus_c_api.cpp` が空 |
| 手動 inProgress.store(false) が 0 箇所 | `grep -n 'inProgress.store(false)' src/cpp/piper_plus_c_api.cpp` が空 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ConfigGuard のコピーコスト | 低 | `SynthesisConfig` は軽量構造体 (数十バイト)。コピーコストは無視できる |
| BusyGuard の例外パス | 低 | `PIPER_PLUS_CATCH` マクロで既に例外を捕捉しているため、BusyGuard コンストラクタの例外も正しく処理される |
| synth_next での BusyGuard 不使用 | 低 | `synth_next` は `synth_start` で設定された状態を読むだけで、`inProgress` の acquire/release は `synth_start` / 最終 `synth_next` で行う。既存のセマンティクスを維持 |

### レビュー時の確認項目

1. 手動の `savedConfig` restore が全て削除されていること (`grep` で 0 件)
2. 手動の `inProgress.store(false)` が全て削除されていること (`grep` で 0 件)
3. ConfigGuard / BusyGuard が anonymous namespace 内に定義されていること
4. コピー・ムーブコンストラクタが `= delete` されていること
5. 既存テストが全 PASS すること

---

## 6. 一から作り直すとしたら

**初期実装から RAII を採用すべきだった。** Phase 1 (M1-6) の C API 実装時点で ConfigGuard / BusyGuard を導入していれば、Phase 2 のストリーミング実装で手動管理箇所が増殖することを防げた。C API のような C++ 内部実装では、リソース管理に RAII を最初から適用するのが C++ のベストプラクティス。

---

## 7. 後続タスクへの連絡事項

- **M5-3 (Iterator crossfade):** IteratorState の拡張時に、新しいリソース (crossfade バッファ) が追加される。RAII パターンに従い、IteratorState のデストラクタで適切にクリーンアップすること。
- **将来の関数追加:** 新しい C API 関数を追加する際は、手動の save/restore ではなく ConfigGuard / BusyGuard を使用すること。
