#!/usr/bin/env python3
"""
Simplified Piper TTS Demo - Text only version
This version works without model files for initial deployment
"""

import gradio as gr


def synthesize_speech_placeholder(text, model_name):
    """Placeholder function for demo"""
    return f"""
    🎙️ Demo Placeholder
    
    This is a simplified demo interface. 
    
    Selected model: {model_name}
    Input text: "{text}"
    
    Note: Actual TTS functionality will be enabled once the storage issue is resolved.
    Please contact the repository owner for the full version.
    """


def create_interface():
    """Create simplified Gradio interface"""
    
    with gr.Blocks(title="Piper TTS Demo") as interface:
        gr.Markdown("""
        # 🎙️ Piper TTS Demo (Simplified Version)
        
        This is a placeholder demo while we resolve storage limitations.
        
        The full version includes:
        - Japanese and English text-to-speech synthesis
        - ONNX model inference
        - Adjustable speech parameters
        
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
                )
                
                synthesize_btn = gr.Button("Generate Speech", variant="primary")
                
            with gr.Column():
                output_text = gr.Textbox(
                    label="Output",
                    lines=10,
                )
        
        synthesize_btn.click(
            fn=synthesize_speech_placeholder,
            inputs=[text_input, model_dropdown],
            outputs=output_text,
        )
    
    return interface


# Create and launch the app
interface = create_interface()

if __name__ == "__main__":
    interface.launch()