#!/usr/bin/env python3
"""Sample texts for Piper TTS WebUI demonstrations"""

# Categorized sample texts for different use cases
SAMPLE_TEXTS = {
    "en_US": {
        "short": [
            "Hello world!",
            "Welcome to Piper TTS.",
            "How are you today?",
            "Thank you very much.",
            "Have a great day!",
        ],
        "conversational": [
            "Hey there! I hope you're having a wonderful day.",
            "Could you please help me with this task?",
            "That's a great idea! Let's work on it together.",
            "I'll be there in about fifteen minutes.",
            "Sure thing! I'd be happy to assist you.",
        ],
        "professional": [
            "Thank you for attending today's meeting. Let's begin with the quarterly report.",
            "Our analysis shows a significant improvement in customer satisfaction ratings.",
            "I'd like to schedule a follow-up discussion for next Tuesday at 2 PM.",
            "Please find attached the revised proposal for your review.",
            "We appreciate your continued partnership and look forward to future collaborations.",
        ],
        "narrative": [
            "The city lights twinkled like stars against the darkening sky, casting a warm glow over the bustling streets below.",
            "As she opened the ancient book, a musty smell filled the air, and the yellowed pages whispered secrets of forgotten times.",
            "The train whistled as it pulled away from the station, beginning its journey through mountains and valleys unknown.",
            "In the quiet of the forest, only the gentle rustle of leaves and distant bird songs could be heard.",
            "The old clocktower chimed midnight, its deep tones echoing through the empty town square.",
        ],
        "technical": [
            "To initialize the system, press and hold the power button for three seconds.",
            "The application uses advanced machine learning algorithms to process natural language.",
            "Please ensure all connections are secure before proceeding with the installation.",
            "The update includes several bug fixes and performance improvements.",
            "Error code 404 indicates that the requested resource could not be found.",
        ],
    },
    "ja_JP": {
        "short": [
            "こんにちは！",
            "ありがとうございます。",
            "お元気ですか？",
            "よろしくお願いします。",
            "良い一日を！",
        ],
        "conversational": [
            "今日はとても良い天気ですね。散歩に行きませんか？",
            "昨日のテレビ番組、見ましたか？とても面白かったです。",
            "来週の予定はどうなっていますか？",
            "お腹が空きました。何か食べに行きましょうか。",
            "最近、新しいカフェがオープンしたそうですよ。",
        ],
        "professional": [
            "本日はお忙しい中、お集まりいただきありがとうございます。",
            "資料をご確認の上、ご意見をお聞かせください。",
            "次回の会議は来週月曜日の午後2時からを予定しております。",
            "ご提案いただいた内容について、検討させていただきます。",
            "プロジェクトの進捗状況について、ご報告させていただきます。",
        ],
        "narrative": [
            "春の訪れとともに、桜の花が街を彩り始めました。人々は花見を楽しみ、新しい季節の始まりを祝っていました。",
            "古い神社の石段を登ると、そこには静寂に包まれた境内が広がっていました。",
            "夕暮れ時、オレンジ色に染まった空を背景に、渡り鳥たちが南へと飛び立っていきました。",
            "雨上がりの朝、庭の紫陽花が生き生きと輝いていました。雫が葉から落ちる音が、静かに響いていました。",
            "月明かりの下、竹林の中を歩いていると、風で竹がささやくような音が聞こえてきました。",
        ],
        "announcement": [
            "お客様にお知らせいたします。本日は午後5時で閉店とさせていただきます。",
            "電車が遅れております。ご迷惑をおかけして申し訳ございません。",
            "次は新宿駅です。お出口は右側です。",
            "本日のイベントは、悪天候のため中止となりました。",
            "エレベーターは現在点検中です。階段をご利用ください。",
        ],
        "educational": [
            "今日は、日本の伝統文化について学習します。",
            "この漢字の読み方は「やま」です。山という意味があります。",
            "地球温暖化は、私たち全員が取り組むべき重要な課題です。",
            "プログラミングを学ぶことで、論理的思考力が身につきます。",
            "健康的な生活習慣を身につけることが大切です。",
        ],
    },
}

# Voice-over and narration samples
NARRATION_SAMPLES = {
    "documentary": {
        "en_US": "In the depths of the ocean, where sunlight never reaches, extraordinary creatures have evolved to thrive in complete darkness.",
        "ja_JP": "深海の闇の中で、太陽の光が届かない場所に、驚くべき生物たちが進化を遂げ、生息しています。",
    },
    "meditation": {
        "en_US": "Take a deep breath in... and slowly exhale. Feel your body relax with each breath.",
        "ja_JP": "深く息を吸って...ゆっくりと吐き出してください。呼吸とともに体がリラックスしていくのを感じてください。",
    },
    "children": {
        "en_US": "Once upon a time, in a magical forest, there lived a friendly dragon who loved to make new friends.",
        "ja_JP": "むかしむかし、魔法の森に、新しい友達を作るのが大好きな優しいドラゴンが住んでいました。",
    },
}

# Emotional expression samples
EMOTION_SAMPLES = {
    "happy": {
        "en_US": "What wonderful news! I'm so excited to hear about your success!",
        "ja_JP": "素晴らしいニュースですね！あなたの成功を聞いてとても嬉しいです！",
    },
    "calm": {
        "en_US": "Everything will be alright. Take your time and don't worry.",
        "ja_JP": "大丈夫ですよ。焦らずに、ゆっくりでいいですから。",
    },
    "serious": {
        "en_US": "This is a matter that requires our immediate attention and careful consideration.",
        "ja_JP": "これは私たちの即座の注意と慎重な検討を必要とする問題です。",
    },
}


def get_sample_by_category(language: str, category: str, index: int = 0) -> str:
    """Get a sample text by language and category"""
    if language in SAMPLE_TEXTS and category in SAMPLE_TEXTS[language]:
        samples = SAMPLE_TEXTS[language][category]
        return samples[index % len(samples)]
    return ""


def get_all_samples_flat(language: str) -> list:
    """Get all samples for a language as a flat list"""
    if language not in SAMPLE_TEXTS:
        return []

    all_samples = []
    for _category, samples in SAMPLE_TEXTS[language].items():
        all_samples.extend(samples)
    return all_samples
