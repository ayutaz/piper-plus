# Home Assistant 統合ガイド

piper-plus を Home Assistant の TTS プロバイダーとして利用する方法を説明します。Wyoming Protocol を介して、6 言語 (ja, en, zh, es, fr, pt) の音声合成を Home Assistant から直接呼び出せます。

---

## 前提条件

- Home Assistant 2024.1 以上 (Wyoming Protocol 統合を標準搭載)
- Docker および Docker Compose がインストール済み (方法 1, 2)
- piper-plus 用の ONNX モデルと config.json (自動ダウンロードも可能)
  - HuggingFace: `ayousanz/piper-plus-tsukuyomi-chan` (つくよみちゃん 6 言語) または `ayousanz/piper-plus-base` (ベースモデル)

---

## Wyoming Protocol とは

[Wyoming Protocol](https://github.com/rhasspy/wyoming) は、Home Assistant が音声アシスタントコンポーネント (STT, TTS, Wake Word) と通信するための軽量 TCP プロトコルです。Home Assistant は Wyoming Protocol を標準でサポートしており、piper-plus の Wyoming アダプタを起動するだけで TTS プロバイダーとして自動検出されます。

**通信フロー:**

```
Home Assistant  ── Describe ──>  piper-plus Wyoming adapter
                <── TTS Info ──

Home Assistant  ── Synthesize (text + language) ──>  piper-plus
                <── AudioStart + AudioChunk... + AudioStop ──
```

---

## セットアップ方法

### 方法 1: Docker Compose (推奨)

最も簡単な方法です。デフォルトモデル (tsukuyomi) は初回起動時に HuggingFace から自動ダウンロードされます。

```bash
cd docker/wyoming
docker compose up -d
```

起動確認:

```bash
# TCP ポートへの接続を確認
nc -zv localhost 10200

# コンテナのヘルスチェック状態を確認
docker inspect --format='{{json .State.Health.Status}}' wyoming-piper-plus
```

#### 環境変数によるカスタマイズ

`.env.example` を `.env` にコピーして設定を変更できます:

```bash
cp .env.example .env
```

| 変数 | デフォルト | 説明 |
|------|----------|------|
| `PIPER_MODEL` | `tsukuyomi` | モデル名、エイリアス、HuggingFace リポジトリ ID、またはコンテナ内パス |
| `PIPER_LANGUAGE` | `ja` | デフォルト言語 (`ja`, `en`, `zh`, `es`, `fr`, `pt`) |
| `PIPER_SPEAKER_ID` | `0` | 話者 ID (シングルスピーカーモデルでは 0) |
| `PIPER_PORT` | `10200` | ホスト側ポート |

#### ローカルモデルを使用する場合

```yaml
services:
  wyoming-piper-plus:
    volumes:
      - ./models:/app/models:ro
    command:
      - --model
      - /app/models/my-model.onnx
      - --uri
      - tcp://0.0.0.0:10200
```

`models/` ディレクトリに `.onnx` ファイルと `config.json` の両方を配置してください。

### 方法 2: Docker Compose (Home Assistant と同一ネットワーク)

Home Assistant を Docker Compose で管理している場合、同じ `docker-compose.yml` に piper-plus を追加できます。

```yaml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./ha-config:/config
    network_mode: host
    restart: unless-stopped

  wyoming-piper-plus:
    build:
      context: .
      dockerfile: docker/wyoming/Dockerfile
    # image: ayousanz/wyoming-piper-plus:latest
    container_name: wyoming-piper-plus
    ports:
      - "10200:10200"
    volumes:
      - piper-models:/home/piper/.cache/piper-plus/models
    restart: unless-stopped

volumes:
  piper-models:
```

Home Assistant が `network_mode: host` で動作している場合、`localhost:10200` で piper-plus に接続できます。

### 方法 3: 手動インストール

Docker を使用しない場合は、Wyoming サーバーを直接起動できます。

```bash
# 依存パッケージのインストール
# wyoming 1.5.0 は Artifact.version フィールドが無く、本アダプターと非互換。
# 1.5.1 で追加されたが、HA 公式 (2026.x) と上流 wyoming-piper に揃え 1.7+ を推奨。
pip install "wyoming>=1.7,<2"
pip install piper-plus-g2p[all]
# src/python/ 内の piper_train[inference] もインストール必要

# サーバーの起動
uv run python -m piper_wyoming \
  --model tsukuyomi \
  --port 10200 \
  --language ja
```

#### systemd サービスとして登録

長期運用する場合は systemd で管理できます:

```ini
# /etc/systemd/system/wyoming-piper-plus.service
[Unit]
Description=Wyoming piper-plus TTS
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=piper
ExecStart=/usr/local/bin/python -m piper_wyoming \
    --model tsukuyomi \
    --port 10200 \
    --language ja
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wyoming-piper-plus
```

---

## Home Assistant 設定

### 自動検出 (Zeroconf / mDNS)

Wyoming Protocol サーバーが Home Assistant と同じ LAN 上で動作している場合、**通知** セクションに自動検出の提案が表示されることがあります。表示された場合は、そのまま追加してください。

### 手動追加

自動検出されない場合、手動で追加します:

1. **設定** > **デバイスとサービス** を開く
2. 右下の **統合を追加** をクリック
3. 検索ボックスに **Wyoming Protocol** と入力し選択
4. 接続情報を入力:

| 項目 | 値 |
|------|-----|
| ホスト | Docker ホストの IP アドレス (例: `192.168.1.100`) |
| ポート | `10200` |

5. **送信** をクリック

正常に接続されると、**piper-plus** が TTS プロバイダーとして登録されます。

> **Note:** `localhost` や `127.0.0.1` は Home Assistant が Docker コンテナ内で動作している場合、コンテナ自身を指すため使用できません。Docker ホストの実際の IP アドレスを使用してください。Home Assistant が `network_mode: host` で動作している場合は `localhost` を使用できます。

---

## 多言語設定

piper-plus の Wyoming アダプタは 6 言語をサポートしています。言語ごとに別の voice として Home Assistant に公開されます:

| Voice 名 | 言語 |
|----------|------|
| `piper-plus-ja` | 日本語 |
| `piper-plus-en` | 英語 |
| `piper-plus-zh` | 中国語 |
| `piper-plus-es` | スペイン語 |
| `piper-plus-fr` | フランス語 |
| `piper-plus-pt` | ポルトガル語 |

### サービスコールでの言語指定

自動化やスクリプトから TTS を呼び出す際に言語を指定できます:

```yaml
service: tts.speak
target:
  entity_id: tts.piper_plus
data:
  media_player_entity_id: media_player.living_room
  message: "Hello, how are you today?"
  language: en
```

言語を指定しない場合は、サーバー起動時の `--language` (デフォルト: `ja`) が使用されます。

---

## 音声アシスタント設定

Home Assistant の Assist パイプラインに piper-plus を TTS として組み込むことで、完全な音声アシスタントを構築できます。

### パイプラインの構成

```
Wake Word (例: openWakeWord)
    ↓
STT (例: Whisper / faster-whisper)
    ↓
会話エージェント (例: Home Assistant built-in / OpenAI)
    ↓
TTS: piper-plus (Wyoming)
    ↓
音声出力
```

### 設定手順

1. **設定** > **音声アシスタント** を開く
2. **アシスタントを追加** (または既存のアシスタントを編集)
3. **テキスト読み上げ** セクションで以下を設定:
   - エンジン: **piper-plus**
   - 言語: 任意の言語を選択
4. 他のパイプラインコンポーネント (STT, 会話エージェント) も設定
5. **保存** をクリック

### ESPHome デバイスとの連携

ESPHome の `voice_assistant` コンポーネントを使用するデバイス (ESP32-S3-BOX など) は、このパイプラインを通じて piper-plus の音声を再生できます:

```yaml
# ESPHome 設定例
voice_assistant:
  microphone: my_microphone
  speaker: my_speaker
```

Home Assistant 側でデバイスに割り当てるパイプラインの TTS に piper-plus を指定してください。

---

## サンプル自動化

### 時報の読み上げ

```yaml
automation:
  - alias: "毎時の時報"
    trigger:
      - platform: time_pattern
        minutes: "0"
    action:
      - service: tts.speak
        target:
          entity_id: tts.piper_plus
        data:
          media_player_entity_id: media_player.living_room
          message: "{{ now().strftime('%H時%M分') }}です。"
          language: ja
```

### ドアベル通知

```yaml
automation:
  - alias: "ドアベル通知"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: tts.speak
        target:
          entity_id: tts.piper_plus
        data:
          media_player_entity_id: media_player.living_room
          message: "玄関にお客様です。"
          language: ja
```

### 多言語天気予報

```yaml
automation:
  - alias: "朝の天気予報 (日本語 + 英語)"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: tts.speak
        target:
          entity_id: tts.piper_plus
        data:
          media_player_entity_id: media_player.bedroom
          message: >-
            今日の天気は{{ state_attr('weather.home', 'forecast')[0].condition }}、
            最高気温は{{ state_attr('weather.home', 'forecast')[0].temperature }}度です。
          language: ja
      - delay: "00:00:05"
      - service: tts.speak
        target:
          entity_id: tts.piper_plus
        data:
          media_player_entity_id: media_player.bedroom
          message: >-
            Today's weather is {{ state_attr('weather.home', 'forecast')[0].condition }},
            high of {{ state_attr('weather.home', 'forecast')[0].temperature }} degrees.
          language: en
```

---

## トラブルシューティング

### Wyoming 統合で接続できない

1. コンテナが起動しているか確認:

   ```bash
   docker ps | grep wyoming-piper-plus
   docker compose -f docker/wyoming/docker-compose.yml logs
   ```

2. ポートが到達可能か確認:

   ```bash
   nc -zv <docker-host-ip> 10200
   ```

3. ファイアウォールの設定を確認:

   ```bash
   # Ubuntu/Debian
   sudo ufw allow 10200/tcp

   # CentOS/RHEL
   sudo firewall-cmd --add-port=10200/tcp --permanent
   sudo firewall-cmd --reload
   ```

4. Home Assistant の IP 設定を確認:
   - Home Assistant が HAOS の場合: Docker ホストの IP を使用
   - Home Assistant が Docker の場合: `network_mode: host` なら `localhost`、それ以外はホスト IP
   - Home Assistant が同じ Docker Compose の場合: コンテナ名 `wyoming-piper-plus` を使用

### 音声が生成されない

1. Wyoming サーバーのログを確認:

   ```bash
   docker compose -f docker/wyoming/docker-compose.yml logs -f
   ```

2. モデルが正しくロードされているか確認:
   - 初回起動時は HuggingFace からのダウンロードに数分かかる場合があります
   - ネットワークの問題でダウンロードが失敗した場合は、コンテナを再起動してください

3. メモリ不足の確認:
   - ONNX モデルは起動時に ~200MB のメモリを使用します
   - Raspberry Pi 4 (4GB) 以上を推奨

### 言語検出が正しくない

Wyoming アダプタの言語解決の優先順位:

1. `voice.language` フィールド (Home Assistant が設定)
2. `voice.name` フィールド (`piper-plus-en` 形式)
3. `voice.name` フィールド (bare language code: `en`)
4. デフォルト言語 (`--language` で指定、デフォルト `ja`)

言語が正しく指定されているか確認するには、`--debug` フラグを有効にします:

```yaml
# docker-compose.yml
command:
  - --model
  - tsukuyomi
  - --language
  - ja
  - --debug
  - --uri
  - tcp://0.0.0.0:10200
```

ログに `Synthesizing: 'text...' (lang=XX)` と表示されるので、正しい言語コードが使用されているか確認してください。

### 初回応答が遅い

- 初回起動時のモデルダウンロード: インターネット速度に依存 (モデルサイズ ~75MB)
- モデルロード後のウォームアップ: ~1-2 秒 (ONNX Runtime のグラフ最適化)
- 2 回目以降の合成: 通常 200-500ms (テキスト長に依存)

モデルキャッシュは Docker ボリューム (`piper-models`) に保存されるため、コンテナの再作成後も再ダウンロードは不要です。

### Docker ネットワーク設定

| Home Assistant の形態 | piper-plus ホスト指定 |
|---------------------|---------------------|
| HAOS (VM/ネイティブ) | Docker ホストの LAN IP (例: `192.168.1.100`) |
| Docker (`network_mode: host`) | `localhost` |
| Docker (bridge network) | Docker ホストの LAN IP |
| 同一 Docker Compose | コンテナ名 `wyoming-piper-plus` |

---

## CLI オプション一覧

Wyoming サーバーの全オプション:

```
uv run python -m piper_wyoming --help
```

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--model` | `tsukuyomi` | モデル名、エイリアス、またはパス |
| `--config` | (自動検出) | config.json パス |
| `--uri` | `tcp://0.0.0.0:10200` | サーバー URI |
| `--port` | (なし) | ポート番号 (`--uri` のポートをオーバーライド) |
| `--speaker-id` | `0` | 話者 ID |
| `--language` | `ja` | デフォルト言語 |
| `--device` | `cpu` | 推論デバイス (`cpu`, `gpu`, `auto`) |
| `--debug` | (なし) | デバッグログ出力 |

---

## 関連ガイド

- [Open WebUI 統合](open-webui-integration.md) -- OpenAI 互換 API 経由の統合
- [LLM エコシステム統合](llm-ecosystem.md) -- AnythingLLM, LangChain, Ollama との統合
- [Docker Wyoming README](../../docker/wyoming/README.md) -- Docker イメージの詳細
