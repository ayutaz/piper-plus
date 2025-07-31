#!/usr/bin/env python3
"""
Simplified Piper TTS Demo - Lightweight version without models
"""

import gradio as gr


def synthesize_speech_demo(text, model_name, speaker_id, length_scale, noise_scale, noise_w):
    """Demo function that returns a placeholder message"""
    return f"""
    🎙️ Piper TTS Demo (Simplified Version)
    
    Model: {model_name}
    Text: "{text}"
    
    Parameters:
    - Speaker ID: {speaker_id}
    - Length Scale: {length_scale}
    - Noise Scale: {noise_scale}
    - Noise W: {noise_w}
    
    Note: This is a lightweight demo without actual TTS models.
    For the full version with working TTS, please use the 'full' deployment mode.
    """


def create_interface():
    """Create simplified Gradio interface"""
    
    with gr.Blocks(title="Piper TTS Demo - Simplified") as interface:
        gr.Markdown("""
        # 🎙️ Piper TTS Demo (Simplified Version)
        
        This is a lightweight demo interface without model files.
        
        Features in the full version:
        - ✅ Japanese text-to-speech with OpenJTalk phonemization
        - ✅ English text-to-speech synthesis
        - ✅ Real-time audio generation
        - ✅ Adjustable voice parameters
        
        Repository: [piper-plus](https://github.com/ayutaz/piper-plus)
        """)
        
        with gr.Row():
            with gr.Column():
                model_dropdown = gr.Dropdown(
                    choices=["Japanese (Medium)", "English (Test)"],
                    label="Select Model",
                    value="Japanese (Medium)",
                )
                
                text_input = gr.Textbox(
                    label="Text to synthesize",
                    placeholder="Enter text here...",
                    lines=3,
                    value="こんにちは、世界！",
                )
                
                with gr.Accordion("Advanced Settings", open=False):
                    speaker_id = gr.Number(
                        label="Speaker ID",
                        value=0,
                        precision=0,
                    )
                    
                    length_scale = gr.Slider(
                        label="Length Scale (speaking rate)",
                        minimum=0.5,
                        maximum=2.0,
                        value=1.0,
                        step=0.1,
                    )
                    
                    noise_scale = gr.Slider(
                        label="Noise Scale (expressiveness)",
                        minimum=0.0,
                        maximum=2.0,
                        value=0.667,
                        step=0.01,
                    )
                    
                    noise_w = gr.Slider(
                        label="Noise W (phoneme duration variation)",
                        minimum=0.0,
                        maximum=2.0,
                        value=0.8,
                        step=0.01,
                    )
                
                synthesize_btn = gr.Button("Generate Speech", variant="primary")
                
            with gr.Column():
                output_text = gr.Textbox(
                    label="Demo Output",
                    lines=15,
                )
        
        synthesize_btn.click(
            fn=synthesize_speech_demo,
            inputs=[
                text_input,
                model_dropdown,
                speaker_id,
                length_scale,
                noise_scale,
                noise_w,
            ],
            outputs=output_text,
        )
        
        gr.Examples(
            examples=[
                ["こんにちは、世界！", "Japanese (Medium)"],
                ["音声合成のデモンストレーションです。", "Japanese (Medium)"],
                ["Hello, world!", "English (Test)"],
                ["This is a text-to-speech demonstration.", "English (Test)"],
            ],
            inputs=[text_input, model_dropdown],
        )
    
    return interface


# Create and launch the app
interface = create_interface()

if __name__ == "__main__":
    interface.launch(server_name="0.0.0.0", server_port=7860)