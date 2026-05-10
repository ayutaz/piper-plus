#!/usr/bin/env python3
"""
Test text constants for TTS testing.
Centralized location for all test texts used in various TTS tests.
"""

# Japanese test sentences
JAPANESE_TEST_SENTENCES = {
    "basic": {
        "hiragana": "こんにちは、これはテストです。",
        "katakana": "コンニチハ、コレハテストデス。",
        "kanji": "今日は良い天気です。",
        "mixed": "今日は2025年7月2日です。",
        "english_mixed": "これはPiperのテストです。",
    },
    "comprehensive": {
        "long_sentence": "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。",
        "punctuation": "これは、句読点のテストです。疑問符は使えますか？感嘆符も使えます！",
        "numbers": "値段は1,234円です。電話番号は03-1234-5678です。",
        "symbols": "メールアドレスはtest@example.comです。URLはhttps://example.com/です。",
        "particles": "私は学校へ行きます。彼と一緒に勉強をしています。",
        "honorifics": "田中さん、佐藤様、山田先生がいらっしゃいます。",
        "onomatopoeia": "犬がワンワンと吠えています。雨がザーザー降っています。",
        "dialects": "大阪弁：めっちゃええやん。標準語：とても良いですね。",
    },
}

# Multilingual test texts
MULTILINGUAL_TEST_TEXTS = {
    "en_US": "Hello, this is a test of the text to speech system.",
    "en_GB": "Good morning, this is a British English voice test.",
    "de_DE": "Hallo, dies ist ein Test des Sprachsynthesesystems.",
    "fr_FR": "Bonjour, ceci est un test du système de synthèse vocale.",
    "es_ES": "Hola, esta es una prueba del sistema de síntesis de voz.",
    "it_IT": "Ciao, questo è un test del sistema di sintesi vocale.",
    "pt_BR": "Olá, este é um teste do sistema de síntese de voz.",
    "ru_RU": "Привет, это тест системы синтеза речи.",
    "zh_CN": "你好，这是语音合成系统的测试。",
    "nl_NL": "Hallo, dit is een test van het spraaksynthesesysteem.",
    "pl_PL": "Witaj, to jest test systemu syntezy mowy.",
    "sv_SE": "Hej, detta är ett test av talsyntessystemet.",
    "ar_JO": "مرحبا، هذا اختبار لنظام تركيب الكلام.",
    "cs_CZ": "Ahoj, toto je test systému syntézy řeči.",
    "fi_FI": "Hei, tämä on puhesynteesijärjestelmän testi.",
    "hu_HU": "Helló, ez a beszédszintézis rendszer tesztje.",
    "no_NO": "Hei, dette er en test av talesyntesesystemet.",
    "da_DK": "Hej, dette er en test af talesyntesesystemet.",
    "el_GR": "Γεια σου, αυτή είναι μια δοκιμή του συστήματος σύνθεσης ομιλίας.",
    "tr_TR": "Merhaba, bu konuşma sentezi sisteminin bir testidir.",
    "uk_UA": "Привіт, це тест системи синтезу мовлення.",
    "vi_VN": "Xin chào, đây là bài kiểm tra hệ thống tổng hợp giọng nói.",
    "ja_JP": "こんにちは、これは音声合成システムのテストです。",
    "ko_KR": "안녕하세요, 이것은 음성 합성 시스템의 테스트입니다.",
}


def get_test_text_description(language: str) -> str:
    """Get a description of what test texts are used for a given language."""
    if language == "ja_JP":
        return """
## 日本語テストテキスト

### 基本テスト:
- **ひらがな**: こんにちは、これはテストです。
- **カタカナ**: コンニチハ、コレハテストデス。
- **漢字**: 今日は良い天気です。
- **混合**: 今日は2025年7月2日です。
- **英語混合**: これはPiperのテストです。

### 総合テスト:
- **長文**: 吾輩は猫である。名前はまだ無い...（夏目漱石）
- **句読点**: 疑問符？感嘆符！を含むテスト
- **数字**: 値段、電話番号のテスト
- **記号**: メールアドレス、URLのテスト
- **助詞**: 複数の助詞を含む文章
- **敬語**: さん、様、先生などの敬称
- **擬音語**: ワンワン、ザーザーなど
- **方言**: 大阪弁と標準語の比較
"""
    elif language in MULTILINGUAL_TEST_TEXTS:
        return f"""
## {language} テストテキスト

テスト文章: "{MULTILINGUAL_TEST_TEXTS[language]}"

この文章は、各言語の基本的な音声合成能力をテストするために選ばれました。
"""
    else:
        return "テストテキスト情報なし"
