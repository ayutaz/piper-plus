# P3-006: TypeScript 型定義

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: NFR-302
> 依存チケット: P3-001, P3-004
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

`@piper-plus/g2p` パッケージの全 API に対して完全な TypeScript 型定義を提供する。現在の `piper-plus` パッケージには `src/wasm/openjtalk-web/types/index.d.ts` (622 行) が存在するが、G2P 固有の型 (`PhonemizeResult`, `ProsodyInfo`, `EncodeResult` 等) は含まれていない。新パッケージの型定義は `tsc --noEmit` エラーなしを保証する。

### ゴール

- `@piper-plus/g2p` の全公開 API に対する完全な `.d.ts` ファイルを提供
- `tsc --noEmit --strict` がエラーなしで pass する
- 各 subpath export (`./ja`, `./en`, `./dict` 等) に対応する型定義が存在する
- TypeScript ユーザーが IntelliSense/autocompletion を利用できる
- JSDoc コメントが型定義に反映されている

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 新規 | `src/wasm/g2p/types/index.d.ts` | G2P メイン API の型定義 |
| 新規 | `src/wasm/g2p/types/ja.d.ts` | JA G2P の型定義 |
| 新規 | `src/wasm/g2p/types/en.d.ts` | EN G2P の型定義 |
| 新規 | `src/wasm/g2p/types/dict.d.ts` | DictLoader の型定義 |
| 新規 | `src/wasm/g2p/types/detect.d.ts` | 言語検出の型定義 |
| 新規 | `src/wasm/g2p/types/encode.d.ts` | エンコーダーの型定義 |
| 新規 | `src/wasm/g2p/types/custom-dict.d.ts` | カスタム辞書の型定義 |
| 変更 | `src/wasm/g2p/package.json` | `types` フィールドと `typesVersions` の設定 |
| 新規 | `src/wasm/g2p/tsconfig.json` | TypeScript 検証用設定 |
| 参照 | `src/wasm/openjtalk-web/types/index.d.ts` | 既存 piper-plus 型定義 (参考) |

### 実装手順

1. **メイン型定義 (`types/index.d.ts`)**: `G2P` クラス、`PhonemizeResult`, `ProsodyInfo`, `EncodeResult`, `G2POptions`, `PhonemizeOptions`, `Language` 型を定義。

2. **subpath export 型定義**: package.json の `exports` に対応する各 subpath の型定義:
   ```json
   {
     "typesVersions": {
       "*": {
         "ja": ["types/ja.d.ts"],
         "en": ["types/en.d.ts"],
         "dict": ["types/dict.d.ts"],
         "detect": ["types/detect.d.ts"],
         "custom-dict": ["types/custom-dict.d.ts"]
       }
     }
   }
   ```

3. **tsconfig.json の作成**: `tsc --noEmit` 検証用の設定ファイル。`strict: true` で型チェック。

4. **既存 piper-plus 型定義の更新**: `src/wasm/openjtalk-web/types/index.d.ts` に `@piper-plus/g2p` の re-export 型を追加。

### API / インターフェース

```typescript
// types/index.d.ts

export type Language = 'ja' | 'en' | 'zh' | 'es' | 'fr' | 'pt';

export interface ProsodyInfo {
    a1: number;
    a2: number;
    a3: number;
}

export interface PhonemizeResult {
    tokens: string[];
    prosody: (ProsodyInfo | null)[];
    language: Language;
}

export interface EncodeResult {
    phonemeIds: number[];
    prosodyFlat: number[] | null;
}

export interface G2POptions {
    languages?: Language[];
    openjtalkModule?: any;
    jaDict?: JaDictData;
    customDicts?: CustomDictionary[];
}

export interface PhonemizeOptions {
    language?: Language;
}

export interface JaDictData {
    dictFiles: Record<string, ArrayBuffer>;
    voiceData?: ArrayBuffer;
}

export class G2P {
    private constructor();
    static create(options?: G2POptions): Promise<G2P>;
    phonemize(text: string, options?: PhonemizeOptions): PhonemizeResult;
    phonemizeWithProsody(text: string, options?: PhonemizeOptions): PhonemizeResult;
    encode(
        text: string,
        phonemeIdMap: Record<string, number[]>,
        options?: PhonemizeOptions
    ): EncodeResult;
    detectLanguage(text: string): Language;
    segmentText(text: string): Array<{ language: Language; text: string }>;
    dispose(): void;
}

// types/ja.d.ts
export function extractPhonemesFromLabels(labels: string): string[];
export function extractPhonemesWithProsody(labels: string): {
    tokens: string[];
    prosody: (ProsodyInfo | null)[];
};
export function applyNPhonemeRules(tokens: string[]): string[];
export function mapToPUA(tokens: string[]): string[];
export const PUA_MAP: Record<string, string>;

// types/dict.d.ts
export interface DictLoaderOptions {
    cachePrefix?: string;
}
export interface LoadJaDictOptions {
    dictUrl?: string;
    includeVoice?: boolean;
    voiceUrl?: string;
    onProgress?: (info: { loaded: number; total: number }) => void;
}
export class DictLoader {
    constructor(options?: DictLoaderOptions);
    loadJaDict(options?: LoadJaDictOptions): Promise<JaDictData>;
    isCached(): Promise<boolean>;
    clearCache(): Promise<void>;
}

// types/detect.d.ts
export function detectLanguage(text: string): Language;
export function segmentText(text: string): Array<{ language: Language; text: string }>;

// types/encode.d.ts
export interface EncodeOptions {
    eosToken?: string;
}
export function encode(
    tokens: string[],
    phonemeIdMap: Record<string, number[]>,
    options?: EncodeOptions
): number[];
export function encodeWithProsody(
    tokens: string[],
    prosody: (ProsodyInfo | null)[],
    phonemeIdMap: Record<string, number[]>,
    options?: EncodeOptions
): EncodeResult;
export const FIXED_PUA_MAPPING: Record<string, number>;
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| TypeScript エンジニア | 1 | 型定義ファイルの作成、`tsc --noEmit` 検証 |
| フロントエンドエンジニア | 1 | JS 実装コードとの整合性チェック、JSDoc コメント |

---

## 4. テスト計画

### 提供範囲

- `tsc --noEmit --strict` がエラーなし
- 全 subpath export の型が解決される
- TypeScript プロジェクトからの import が正しく型推論される

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| tsc --noEmit | 型定義ファイル自体のコンパイルチェック | 1 |
| import テスト | 各 subpath export からの import が型エラーなし | 6 |
| 型推論テスト | `phonemize()` の戻り値が `PhonemizeResult` に推論される | 3 |
| Generic 互換 | `Language` 型が正しくユニオン型として動作 | 2 |
| null 安全 | `prosody` の要素が `ProsodyInfo | null` として扱われる | 2 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| サンプルプロジェクト | TypeScript プロジェクトで `@piper-plus/g2p` を import し、`tsc` が通る |
| IntelliSense | VSCode で autocompletion が動作する (手動検証) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **subpath export の型解決**: TypeScript の `moduleResolution: "node16"` / `"bundler"` で subpath export の型が正しく解決されるか。`typesVersions` と `exports` の両方を設定する必要がある (TypeScript 4.7+ は `exports` の `types` 条件をサポート)。
2. **OpenJTalk WASM モジュールの型**: `G2POptions.openjtalkModule` は `any` 型としているが、Emscripten 生成モジュールの正確な型定義は複雑。最低限 `allocateUTF8`, `_free`, `UTF8ToString`, `FS` のメソッド型を定義すべきか検討。
3. **既存 piper-plus 型定義との整合**: `SimpleUnifiedPhonemizer` の型は `src/wasm/openjtalk-web/types/index.d.ts` に既に定義済み。`@piper-plus/g2p` の型を re-export する際に型の重複や衝突が起きないか確認。
4. **JSDoc vs .d.ts**: JS ソースコード側に JSDoc を充実させれば `tsc` の `--declaration` + `--allowJs` で型定義を自動生成できる。手書き `.d.ts` と自動生成のどちらを選ぶか。手書きの方が型の精度が高いが、メンテナンスコストがかかる。

### レビュー項目

- [ ] `tsc --noEmit --strict` がエラーなし
- [ ] 全 subpath export に対応する型定義が存在する
- [ ] `ProsodyInfo` の型が Python/Rust の `ProsodyInfo` と同一フィールドを持つ
- [ ] `G2P.create()` の戻り値型が `Promise<G2P>` である
- [ ] `phonemize()` と `phonemizeWithProsody()` の戻り値型が `PhonemizeResult` で統一
- [ ] `package.json` の `types` / `typesVersions` が正しく設定されている

---

## 6. 一から作り直すとしたら

現在の `piper-plus` の型定義 (`types/index.d.ts`, 622 行) は手書きで網羅的だが、JS ソースコードの変更に追従するのが手作業になっている。一から作り直すなら:

- **TypeScript で書く**: JS + `.d.ts` ではなく、最初から TypeScript で実装する。型定義の自動生成が可能になり、型と実装の乖離がなくなる。
- **`@piper-plus/g2p` を TypeScript で実装し、`piper-plus` (JS) から利用する**。G2P パッケージは新規なので TypeScript 化の機会。ただし WASM 連携部分 (Emscripten) は JS のままの方が扱いやすい。
- **branded type の活用**: `phonemeIds: number[]` ではなく `phonemeIds: PhonemeId[]` のように branded type を使い、生の number[] との混同を防ぐ。

---

## 7. 後続タスクへの連絡事項

- **P3-007 (CI)**: CI で `tsc --noEmit --strict` を実行するステップを追加。
- **P3-008 (安定版リリース)**: 型定義の品質がユーザーフィードバックに直結する。v1.0.0 前に TypeScript ユーザーからのフィードバックを収集する。
- **P3-005 (互換レイヤー)**: 互換レイヤーの新 API (`phonemize()`, `infer()`) の型を `src/wasm/openjtalk-web/types/index.d.ts` に追加する。本チケットと並行作業可能。
