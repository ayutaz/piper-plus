// StreamingTTSDemo.cs — Sentence-by-sentence streaming synthesis demo
//
// Demonstrates:
//   - Splitting text into sentences
//   - Playing each sentence sequentially
//   - Prefetching the next sentence while the current one plays
//   - Smooth continuous playback across multiple sentences

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using PiperPlus;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Streaming TTS demo that splits text into sentences and plays them sequentially.
/// The next sentence is synthesized (prefetched) while the current one is playing.
/// Attach to a GameObject with an AudioSource. Assign a PiperModel in the Inspector.
/// </summary>
public class StreamingTTSDemo : MonoBehaviour
{
    [Header("Model")]
    [SerializeField] private PiperModel model;

    [Header("UI")]
    [SerializeField] private InputField textInput;
    [SerializeField] private Button speakButton;
    [SerializeField] private Button stopButton;
    [SerializeField] private Text statusText;
    [SerializeField] private Text currentSentenceText;

    [Header("Default Text")]
    [TextArea(3, 10)]
    [SerializeField] private string defaultText =
        "This is the first sentence. This is the second sentence. And here is the third one.";

    private AudioSource _audioSource;
    private PiperTTSAsync _tts;
    private CancellationTokenSource _cts;
    private bool _isPlaying;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        if (_audioSource == null)
            _audioSource = gameObject.AddComponent<AudioSource>();

        if (model == null)
        {
            SetStatus("Error: No PiperModel assigned.");
            return;
        }

        try
        {
            _tts = PiperTTSAsync.Create(model);
            SetStatus($"Ready. Enter text with multiple sentences.");
        }
        catch (PiperException ex)
        {
            SetStatus($"Failed to create engine: {ex.Message}");
            return;
        }

        if (speakButton != null)
            speakButton.onClick.AddListener(OnSpeakClicked);

        if (stopButton != null)
        {
            stopButton.onClick.AddListener(OnStopClicked);
            stopButton.interactable = false;
        }
    }

    void OnDestroy()
    {
        Stop();
        _tts?.Dispose();
    }

    /// <summary>
    /// Start streaming synthesis of the given text.
    /// The text is split into sentences, each synthesized and played sequentially.
    /// The next sentence is prefetched during playback of the current one.
    /// </summary>
    public async void SpeakStreaming(string text)
    {
        if (_tts == null || _isPlaying) return;

        Stop();

        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        _isPlaying = true;

        if (stopButton != null)
            stopButton.interactable = true;

        var sentences = SplitSentences(text);
        if (sentences.Count == 0)
        {
            SetStatus("No sentences to synthesize.");
            _isPlaying = false;
            return;
        }

        SetStatus($"Streaming {sentences.Count} sentence(s)...");

        try
        {
            // Prefetch: start synthesizing the first sentence immediately
            Task<AudioClip> nextClipTask = _tts.SynthesizeAsync(
                sentences[0], model.defaultLanguage, null, token);

            for (int i = 0; i < sentences.Count; i++)
            {
                if (token.IsCancellationRequested) break;

                string currentSentence = sentences[i];
                SetCurrentSentence(i + 1, sentences.Count, currentSentence);

                // Await the current sentence's clip
                var clip = await nextClipTask;
                if (token.IsCancellationRequested) break;

                // Start prefetching the next sentence while the current one plays
                if (i + 1 < sentences.Count)
                {
                    nextClipTask = _tts.SynthesizeAsync(
                        sentences[i + 1], model.defaultLanguage, null, token);
                }

                // Play the current clip
                if (clip != null)
                {
                    _audioSource.clip = clip;
                    _audioSource.Play();

                    // Wait for playback to finish
                    while (_audioSource.isPlaying && !token.IsCancellationRequested)
                    {
                        await Task.Yield();
                    }
                }
            }

            if (!token.IsCancellationRequested)
                SetStatus("Streaming complete.");
        }
        catch (System.OperationCanceledException)
        {
            SetStatus("Streaming stopped.");
        }
        catch (PiperException ex)
        {
            SetStatus($"Synthesis error: {ex.Message}");
        }
        finally
        {
            _isPlaying = false;
            if (stopButton != null)
                stopButton.interactable = false;
            if (currentSentenceText != null)
                currentSentenceText.text = "";
        }
    }

    /// <summary>
    /// Stop streaming playback and cancel any in-flight synthesis.
    /// </summary>
    public void Stop()
    {
        if (_cts != null)
        {
            _cts.Cancel();
            _cts.Dispose();
            _cts = null;
        }

        _audioSource.Stop();
        _isPlaying = false;
    }

    /// <summary>
    /// Split text into sentences. Handles common sentence-ending punctuation
    /// for multiple languages (period, exclamation, question mark, and CJK equivalents).
    /// </summary>
    private static List<string> SplitSentences(string text)
    {
        var sentences = new List<string>();
        if (string.IsNullOrEmpty(text)) return sentences;

        var delimiters = new[] { '.', '!', '?', '\u3002', '\uff01', '\uff1f' };
        int start = 0;

        for (int i = 0; i < text.Length; i++)
        {
            bool isDelimiter = System.Array.IndexOf(delimiters, text[i]) >= 0;
            if (isDelimiter || i == text.Length - 1)
            {
                int end = isDelimiter ? i + 1 : i + 1;
                string sentence = text.Substring(start, end - start).Trim();
                if (!string.IsNullOrEmpty(sentence))
                    sentences.Add(sentence);
                start = end;
            }
        }

        return sentences;
    }

    private void OnSpeakClicked()
    {
        string text = textInput != null && !string.IsNullOrEmpty(textInput.text)
            ? textInput.text
            : defaultText;
        SpeakStreaming(text);
    }

    private void OnStopClicked()
    {
        Stop();
        SetStatus("Stopped by user.");
    }

    private void SetCurrentSentence(int index, int total, string sentence)
    {
        string msg = $"[{index}/{total}] {sentence}";
        Debug.Log($"[StreamingTTSDemo] {msg}");
        if (currentSentenceText != null)
            currentSentenceText.text = msg;
    }

    private void SetStatus(string message)
    {
        Debug.Log($"[StreamingTTSDemo] {message}");
        if (statusText != null)
            statusText.text = message;
    }
}
