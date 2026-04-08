// BasicTTSDemo.cs — Minimal text-to-speech example for piper-plus Unity package
//
// Setup:
//   1. Attach this script to a GameObject with an AudioSource component
//   2. Assign a PiperModel asset in the Inspector
//   3. Optionally wire up UI elements (InputField + Button)
//
// The core synthesis flow is just 3 lines:
//   var tts  = PiperTTS.Create(model);
//   var clip = tts.Synthesize("text");
//   audioSource.PlayOneShot(clip);

using PiperPlus;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Minimal TTS demo showing the simplest possible piper-plus integration.
/// Attach to a GameObject with an AudioSource. Assign a PiperModel in the Inspector.
/// </summary>
public class BasicTTSDemo : MonoBehaviour
{
    [Header("Model")]
    [Tooltip("Drag a PiperModel ScriptableObject here (Assets > Create > Piper Plus > Model).")]
    [SerializeField] private PiperModel model;

    [Header("UI (optional)")]
    [SerializeField] private InputField textInput;
    [SerializeField] private Button speakButton;
    [SerializeField] private Text statusText;

    [Header("Default Text")]
    [SerializeField] private string defaultText = "Hello, this is piper-plus running in Unity.";

    private AudioSource _audioSource;
    private PiperTTS _tts;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        if (_audioSource == null)
            _audioSource = gameObject.AddComponent<AudioSource>();

        if (model == null)
        {
            SetStatus("Error: No PiperModel assigned. Drag one into the Inspector.");
            return;
        }

        try
        {
            // --- Core line 1: Create the TTS engine ---
            _tts = PiperTTS.Create(model);

            SetStatus(
                $"Ready. Version: {PiperTTS.NativeVersion}, " +
                $"Languages: {_tts.AvailableLanguages}, " +
                $"Speakers: {_tts.NumSpeakers}, " +
                $"Sample rate: {_tts.SampleRate} Hz");
        }
        catch (PiperException ex)
        {
            SetStatus($"Failed to create engine: {ex.Message}");
            return;
        }

        if (speakButton != null)
            speakButton.onClick.AddListener(OnSpeakClicked);
    }

    void OnDestroy()
    {
        _tts?.Dispose();
    }

    /// <summary>
    /// Synthesize and play the given text. Call from UI or other scripts.
    /// </summary>
    public void Speak(string text)
    {
        if (_tts == null) return;

        try
        {
            // --- Core line 2: Synthesize text to AudioClip ---
            var clip = _tts.Synthesize(text, model.defaultLanguage);
            if (clip == null) return;

            // --- Core line 3: Play the audio ---
            _audioSource.PlayOneShot(clip);

            SetStatus($"Playing: \"{text}\" ({clip.length:F2}s)");
        }
        catch (PiperException ex)
        {
            SetStatus($"Synthesis error: {ex.Message}");
        }
    }

    private void OnSpeakClicked()
    {
        string text = textInput != null && !string.IsNullOrEmpty(textInput.text)
            ? textInput.text
            : defaultText;
        Speak(text);
    }

    private void SetStatus(string message)
    {
        Debug.Log($"[BasicTTSDemo] {message}");
        if (statusText != null)
            statusText.text = message;
    }
}
