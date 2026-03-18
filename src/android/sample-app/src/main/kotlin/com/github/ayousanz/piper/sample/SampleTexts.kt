package com.github.ayousanz.piper.sample

/**
 * Default sample texts for each supported language.
 */
object SampleTexts {

    fun forLanguage(language: TtsLanguage): List<String> = when (language) {
        TtsLanguage.JAPANESE -> listOf(
            "こんにちは、今日は良い天気ですね。",
            "つくよみちゃんは、フリー素材のキャラクターです。",
            "明日の会議は午前十時から始まります。",
        )
        TtsLanguage.ENGLISH -> listOf(
            "Hello, how are you today?",
            "The quick brown fox jumps over the lazy dog.",
            "Welcome to the Piper text-to-speech engine.",
        )
        TtsLanguage.CHINESE -> listOf(
            "你好，今天天气很好。",
            "欢迎使用语音合成系统。",
            "明天我们一起去公园吧。",
        )
        TtsLanguage.SPANISH -> listOf(
            "Hola, ¿cómo estás hoy?",
            "Bienvenido al motor de síntesis de voz.",
            "El clima está muy agradable esta mañana.",
        )
        TtsLanguage.FRENCH -> listOf(
            "Bonjour, comment allez-vous aujourd'hui?",
            "Bienvenue dans le moteur de synthèse vocale.",
            "Il fait très beau ce matin.",
        )
        TtsLanguage.PORTUGUESE -> listOf(
            "Olá, como você está hoje?",
            "Bem-vindo ao motor de síntese de voz.",
            "O tempo está muito agradável esta manhã.",
        )
    }
}
