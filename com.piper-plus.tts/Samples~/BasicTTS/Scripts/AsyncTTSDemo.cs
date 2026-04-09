// AsyncTTSDemo.cs — Asynchronous TTS demo with loading indicator and cancellation
//
// Demonstrates:
//   - Non-blocking synthesis via PiperTTSAsync
//   - CancellationToken for aborting in-flight requests
//   - Simple request queue (newest request cancels the previous one)
//   - Loading indicator while synthesis is in progress

using System.Threading;
using PiperPlus;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Asynchronous TTS demo. Synthesis runs on a worker thread so the UI stays responsive.
/// Attach to a GameObject with an AudioSource. Assign a PiperModel in the Inspector.
/// </summary>
public class AsyncTTSDemo : MonoBehaviour
{
    [Header("Model")]
    [SerializeField] private PiperModel model;

    [Header("UI")]
    [SerializeField] private InputField textInput;
    [SerializeField] private Button speakButton;
    [SerializeField] private Button cancelButton;
    [SerializeField] private Text statusText;
    [SerializeField] private GameObject loadingIndicator;

    [Header("Default Text")]
    [SerializeField] private string defaultText = "Asynchronous synthesis keeps the UI responsive.";

    private AudioSource _audioSource;
    private PiperTTSAsync _tts;
    private CancellationTokenSource _cts;
    private bool _isSynthesizing;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        if (_audioSource == null)
            _audioSource = gameObject.AddComponent<AudioSource>();

        if (loadingIndicator != null)
            loadingIndicator.SetActive(false);

        if (model == null)
        {
            SetStatus("Error: No PiperModel assigned.");
            return;
        }

        try
        {
            _tts = PiperTTSAsync.Create(model);
            SetStatus($"Ready. Languages: {_tts.AvailableLanguages}");
        }
        catch (PiperException ex)
        {
            SetStatus($"Failed to create engine: {ex.Message}");
            return;
        }

        if (speakButton != null)
            speakButton.onClick.AddListener(OnSpeakClicked);

        if (cancelButton != null)
        {
            cancelButton.onClick.AddListener(OnCancelClicked);
            cancelButton.interactable = false;
        }
    }

    void OnDestroy()
    {
        CancelCurrent();
        _tts?.Dispose();
    }

    /// <summary>
    /// Start asynchronous synthesis. If a previous request is in-flight, it is cancelled.
    /// </summary>
    public async void SpeakAsync(string text)
    {
        if (_tts == null) return;

        // Cancel any in-flight request
        CancelCurrent();

        _cts = new CancellationTokenSource();
        var token = _cts.Token;

        SetSynthesizing(true);
        SetStatus($"Synthesizing: \"{text}\"...");

        try
        {
            var clip = await _tts.SynthesizeAsync(text, model.defaultLanguage, null, token);

            if (token.IsCancellationRequested) return;

            if (clip != null)
            {
                _audioSource.clip = clip;
                _audioSource.Play();
                SetStatus($"Playing: {clip.length:F2}s");
            }
            else
            {
                SetStatus("Synthesis returned empty audio.");
            }
        }
        catch (System.OperationCanceledException)
        {
            SetStatus("Synthesis cancelled.");
        }
        catch (PiperException ex)
        {
            SetStatus($"Synthesis error: {ex.Message}");
        }
        finally
        {
            SetSynthesizing(false);
        }
    }

    /// <summary>
    /// Cancel the current synthesis request, if any.
    /// </summary>
    public void CancelCurrent()
    {
        if (_cts != null)
        {
            _cts.Cancel();
            _cts.Dispose();
            _cts = null;
        }
    }

    private void OnSpeakClicked()
    {
        string text = textInput != null && !string.IsNullOrEmpty(textInput.text)
            ? textInput.text
            : defaultText;
        SpeakAsync(text);
    }

    private void OnCancelClicked()
    {
        CancelCurrent();
        _audioSource.Stop();
        SetStatus("Cancelled by user.");
        SetSynthesizing(false);
    }

    private void SetSynthesizing(bool active)
    {
        _isSynthesizing = active;

        if (loadingIndicator != null)
            loadingIndicator.SetActive(active);

        if (cancelButton != null)
            cancelButton.interactable = active;
    }

    private void SetStatus(string message)
    {
        Debug.Log($"[AsyncTTSDemo] {message}");
        if (statusText != null)
            statusText.text = message;
    }
}
