# Svenska i piper-plus — Implementeringsplan

## Arkitekturanalys

piper-plus har en clean plug-in-arkitektur för nya språk:

### Vad som behövs för ett nytt språk

1. **Phonemizer** (`src/python/piper_train/phonemize/swedish.py`)
   - Klass `SwedishPhonemizer(Phonemizer)` med tre metoder:
     - `phonemize(text) -> list[str]` — text till IPA-fonem
     - `phonemize_with_prosody(text) -> (list[str], list[ProsodyInfo])` — med prosodi
     - `get_phoneme_id_map() -> None` — None = använd multilingual ID map
   - Regelbaserad G2P (som SpanishPhonemizer, FrenchPhonemizer)
   - ELLER espeak-ng-baserad (enklare, men less control)

2. **Phoneme ID map** (`src/python/piper_train/phonemize/sv_id_map.py`)
   - `SWEDISH_PHONEMES: list[str]` — fullständigt foneminventarium
   - Registreras i `multilingual_id_map.py`

3. **PUA-mappning** (`token_mapper.py`)
   - Multi-tecken IPA-symboler → PUA-codepoints
   - Svenska specifika: ɕ, ɧ, ʉ, ɵ, ɛː, øː etc.

4. **Registrering** i:
   - `registry.py` → `_auto_register()` — lägga till SwedishPhonemizer
   - `multilingual_id_map.py` → `_register_builtin_phonemes()` — foneminventarium
   - `multilingual.py` (runtime) → `_get_phonemize_func()` — inference-rutt

5. **Runtime phonemizer** (`src/python_run/piper/phonemize/swedish.py`)
   - Lättare version för inference (samma API)

6. **Tester** (`test/test_swedish_phonemizer.py`)

## Svenska fonem-inventariet

### Vokaler (monoftonger)
| IPA | Exempel | Beskrivning |
|-----|---------|-------------|
| iː | bil | lång sluten i |
| ɪ | bill | kort i |
| yː | by | lång rund y |
| ʏ | bygg | kort rund y |
| ʉː | hus | lång central ʉ (unikt för svenska!) |
| ɵ | hund | kort central ɵ |
| eː | ben | lång halvsluten e |
| ɛ | bett | kort halvöppen e |
| ɛː | bär | lång halvöppen ɛ |
| øː | höst | lång rund ø |
| œ | hörn | kort rund œ |
| ɑː | far | lång bakre a |
| a | fatt | kort a |
| oː | bok | lång o |
| ɔ | boll | kort o |
| uː | ful | lång u |
| ʊ | full | kort u |

### Konsonanter
| IPA | Exempel | Beskrivning |
|-----|---------|-------------|
| p | pil | |
| b | bil | |
| t | tak | |
| d | dag | |
| k | kal | |
| ɡ | gal | |
| f | fisk | |
| v | val | |
| s | sol | |
| ɕ | kjol, tjugo | alveolopalatal frikativa |
| ɧ | sjö, sju | "sje-ljud" (UNIKT för svenska!) |
| h | hund | |
| m | mat | |
| n | natt | |
| ŋ | kung | velar nasal |
| l | lag | |
| r | rak | dental/alveolar tremulant |
| j | ja | palatal approximant |

### Retroflexer (r + dental/alveolar)
| IPA | Exempel | Beskrivning |
|-----|---------|-------------|
| ʈ | kart | retroflex t |
| ɖ | bord | retroflex d |
| ɳ | barn | retroflex n |
| ʂ | mars | retroflex s |
| ɭ | Karl | retroflex l |

### Prosodi — TONACCENTER (unikt!)
Svenska har TVÅ tonaccenter — accent 1 (akut) och accent 2 (grav):
- **Accent 1**: `ˈandən` (anda/duck) — fallande ton
- **Accent 2**: `ˌandən` (ande/spirit) — fallande-stigande ton

Ingen annan TTS hanterar detta korrekt. piper-plus prosody-dim stöder detta:
- a1: tonaccent (1 eller 2)
- a2: betoningsgrad (0=obetonad, 1=bibetonad, 2=huvudbetoning)
- a3: antal fonem i ordet

## Approach

### Fas 1: espeak-ng-baserad phonemizer (snabb start)
- Använd espeak-ng som backend (redan installerat, fungerar)
- Wrappa i SwedishPhonemizer-klassen
- Fördel: snabbt, pålitligt, hanterar undantag
- Nackdel: ingen kontroll över tonaccenter

### Fas 2: Regelbaserad G2P (bättre kvalitet)
- Svenska har relativt regelbunden ortografi (som spanska)
- Implementera G2P-regler baserat på svenska fonotaktik
- Lägg till tonaccent-regler (accent 1 vs 2)
- Referens: `sv_list` och `sv_rules` i espeak-ng

### Fas 3: Tonaccent-prosodi
- Implementera tonaccent-detektion i prosody-info
- Kräver ordlistebaserad lookup (de flesta ord har fast accent)
- Kompositaanalys (sammansatta ord → accent 2)
- Integration med piper-plus prosody-dim

## Prioriteringar
1. ✅ Foneminventarium + ID-map (dag 1)
2. ✅ espeak-ng-baserad phonemizer (dag 1-2)
3. ✅ Registrering + tester (dag 2)
4. 🔄 Regelbaserad G2P (vecka 2)
5. 🔄 Tonaccent-prosodi (vecka 2-3)
6. 🔄 Träningsdata + modellträning (vecka 3-4)
