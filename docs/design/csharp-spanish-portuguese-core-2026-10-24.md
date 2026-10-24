# C# のスペイン語・ポルトガル語 G2P を PiperPlus.Core に移す (Issue #832)

C# CLI は、es/pt の G2P を外部パッケージ `DotNetG2P.Spanish` / `DotNetG2P.Portuguese` (1.8.0) に任せていました。これらの規則は学習時の Python (`piper_plus_g2p.spanish` / `portuguese`) と違うため、Python の正解 (`phoneme_test_cases_golden.json`) と es 28 件、pt 39 件がずれていました。

pt では、6 言語モデルの `phoneme_id_map` にない `ɐ`・`w̃` も出していました (例: `dia` → `dʒ i ɐ`)。これらは ID 変換で黙って捨てられるため、学習時と違うだけでなく音素が欠けていました。

## 変更

- Python の規則を Core に移植しました。新しいエンジンは `SpanishG2PEngine` と `PortugueseG2PEngine` (BR) です。フランス語 (#838 の `FrenchG2PEngine`) と同じ形にしてあります。
- 強勢と prosody を付ける既存の `SpanishPhonemizer` / `PortuguesePhonemizer` は、Python と同じ動きだったので変えていません。エンジンは強勢のある母音の直前に `ˈ` を置き、phonemizer がそれを A2=2 に変えます。`EuropeanPortuguesePhonemizer` (pt-PT) も新しいエンジンの上で Python と一致します。
- CLI (`TextModePhonemizer`) とベンチマークの配線を新しいエンジンに替えました。あわせて `DotNetSpanishG2PEngine.cs` / `DotNetPortugueseG2PEngine.cs` と 2 つのパッケージ参照を削除しました。日本語用の DotNetG2P (MeCab) と英語用の DotNetG2P.English は残しています。英語は別の PR で扱います。
- `known_divergences.json` の csharp/832 から es/pt の 67 件を削除しました。残りは en 4 件です。

## 再発防止

- `TextModeCoreEnginesTests`: CLI のアセンブリとテストの deps.json に DotNetG2P.Spanish / Portuguese / French がないことを検査します。また、`--language es/pt/fr` の出力が Core のエンジンで組んだ音素化器の出力と同じであることを検査します。外部パッケージに戻すと失敗します。
- `CliPhonemes_ForGoldenInputs_AreAllInModelPhonemeIdMap`: golden の es/pt/fr の全入力で、CLI が出すトークンがすべてモデルの `phoneme_id_map` にあることを検査します。ID 表にない音素が黙って捨てられる不具合を防ぎます。
- csharp-ci の path filter に、モデル config (`test/models/multilingual-test-medium.onnx.json`) と Python の `spanish.py` / `portuguese.py` を加えました。

## 移植しなかった点

golden の範囲では、es/pt の差は残っていません。次の 2 点は golden の外でずれる可能性があります。フランス語の移植と同じ扱いにしました。

- Python の `re.IGNORECASE` は、ASCII 以外の ſ / ı / K (ケルビン記号) も文字クラスに含めます。今回の移植では、これらを単語の文字として扱いません。
- Python の `str.lower()` と .NET の `ToLowerInvariant()` は、İ などの文字で結果が違う場合があります。

Python 側の規則の癖も、そのまま移しています。es では語頭の子音連続を音節に数え、`xc` を 1 音素と数えます。pt では `ou` に強勢を置けません。これを直すと学習データとずれるため、今回は直していません。
