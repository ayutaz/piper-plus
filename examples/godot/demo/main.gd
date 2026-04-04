extends Node
## PiperTTS GDExtension demo script.
##
## Demonstrates one-shot and streaming synthesis using the piper-plus C API
## via the PiperTTS GDExtension node.

@onready var model_input: LineEdit = %ModelLineEdit
@onready var text_input: LineEdit = %TextLineEdit
@onready var load_btn: Button = %LoadButton
@onready var speak_btn: Button = %SpeakButton
@onready var stream_btn: Button = %StreamButton
@onready var status_label: Label = %Status
@onready var tts: PiperTTS = %PiperTTS


func _ready() -> void:
	load_btn.pressed.connect(_on_load_pressed)
	speak_btn.pressed.connect(_on_speak_pressed)
	stream_btn.pressed.connect(_on_stream_pressed)
	tts.synthesis_complete.connect(_on_synthesis_complete)


func _on_load_pressed() -> void:
	var path := model_input.text.strip_edges()
	if path.is_empty():
		status_label.text = "Status: Please enter a model path."
		return

	tts.model_path = path
	status_label.text = "Status: Loading model..."

	if tts.load_model():
		status_label.text = "Status: Model loaded (speakers=%d, languages=%d)" % [
			tts.get_num_speakers(), tts.get_num_languages()
		]
		speak_btn.disabled = false
		stream_btn.disabled = false
	else:
		status_label.text = "Status: Failed to load model."
		speak_btn.disabled = true
		stream_btn.disabled = true


func _on_speak_pressed() -> void:
	var text := text_input.text.strip_edges()
	if text.is_empty():
		return
	status_label.text = "Status: Synthesizing..."
	tts.speak(text)


func _on_stream_pressed() -> void:
	var text := text_input.text.strip_edges()
	if text.is_empty():
		return
	status_label.text = "Status: Synthesizing (streaming)..."
	tts.speak_streaming(text)


func _on_synthesis_complete() -> void:
	status_label.text = "Status: Playback started."
