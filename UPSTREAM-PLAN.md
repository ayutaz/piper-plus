# Uppströms-bidragsplan: Svenska TTS i Piper-ekosystemet

## Tre mål parallellt

### 1. espeak-ng (fonem-backend)
**Repo**: github.com/espeak-ng/espeak-ng
**Status**: PR #2391 öppen (50+ svenska fixar)
**Åtgärd**:
- Följ upp PR #2391, svara på review-kommentarer
- Utöka med fler compound word-regler
- Lägga till tonaccent-regler (sv_accent1, sv_accent2 envelopes)
- När mergad: alla Piper-varianter får bättre svenska fonem automatiskt

### 2. piper1-gpl (officiella Piper)
**Repo**: github.com/OHF-Voice/piper1-gpl
**Arkitektur**: C-bridge till espeak-ng, ONNX inference
**Bidrag**:
- Träna och publicera sv_SE ONNX-modell på HuggingFace
  - Minst medium-kvalitet (standard Piper-format)
  - Baserat på Alma/Axel-röster (om licenskompatibla) eller public domain-data
- Modellen fungerar automatiskt i:
  - Home Assistant (Wyoming)
  - speech-dispatcher (via generic module)
  - Alla piper1-gpl-installationer
- JSON config med: `"language": "sv_SE"`, `"espeak_voice": "sv"`, `"phoneme_type": "espeak"`

### 3. Spiel speech-provider-piper
**Repo**: github.com/project-spiel/speech-provider-piper
**Arkitektur**: Rust, sonata-piper, D-Bus, Flatpak-distribuerbar
**Bidrag**:
- ONNX-modellen från (2) fungerar direkt — Spiel upptäcker röster automatiskt
- Eventuellt bidra Flatpak-metadata för svensk röst
- Testa Orca → Spiel → Piper → svenska kedjan end-to-end
- Om nödvändigt: bidra svenska SSML-regler (say-as, sentence detection)

## Kedjans flöde

```
Text → espeak-ng (fonemisering) → Piper ONNX (syntesmodell) → Audio
         ↑ våra fixar                ↑ vår tränade modell
```

Samma ONNX-modell fungerar i ALLA consumers:
- piper1-gpl CLI
- Home Assistant / Wyoming
- Spiel / Orca (GNOME tillgänglighet)
- speech-dispatcher
- piper-plus (vår utvecklingsmiljö)

## Prioritetsordning
1. **piper-plus svenska G2P** (pågår) — grunden
2. **Träna ONNX-modell** på DANNESBURK — kärnan
3. **Publicera på HuggingFace** — omedelbar distribution
4. **espeak-ng PR #2391** — förbättra fonem-kvalitet
5. **Testa i Spiel+Orca** — end-to-end verifiering
6. **piper1-gpl PR** — ev. bidra docs/tester specifikt för sv
