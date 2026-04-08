// NPCDialogDemo.cs — NPC dialog system demo with subtitle sync
//
// Demonstrates:
//   - Serializable dialog data (Inspector-editable dialog sequences)
//   - Subtitle text synchronized with audio playback
//   - Automatic progression to the next dialog line
//   - Manual advance via button or method call

using System.Threading;
using System.Threading.Tasks;
using PiperPlus;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// NPC dialog demo with sequential dialog lines, subtitle display, and auto-advance.
/// Attach to an NPC GameObject with an AudioSource. Assign a PiperModel in the Inspector.
/// </summary>
public class NPCDialogDemo : MonoBehaviour
{
    /// <summary>
    /// A single line of NPC dialog.
    /// </summary>
    [System.Serializable]
    public class DialogLine
    {
        [Tooltip("The text to speak and display as a subtitle.")]
        [TextArea(1, 3)]
        public string text;

        [Tooltip("Language code for this line (e.g., 'ja', 'en'). Leave empty to use the model default.")]
        public string language;

        [Tooltip("Pause in seconds after this line before advancing to the next.")]
        public float pauseAfter = 0.5f;
    }

    [Header("Model")]
    [SerializeField] private PiperModel model;

    [Header("Dialog")]
    [Tooltip("Sequence of dialog lines to play.")]
    [SerializeField] private DialogLine[] dialogLines = new[]
    {
        new DialogLine { text = "Hello, traveler. Welcome to this village.", language = "en", pauseAfter = 0.5f },
        new DialogLine { text = "I have a quest for you, if you are interested.", language = "en", pauseAfter = 0.3f },
        new DialogLine { text = "Please bring me the ancient artifact from the forest.", language = "en", pauseAfter = 1.0f },
    };

    [Header("UI")]
    [SerializeField] private Text subtitleText;
    [SerializeField] private Text speakerNameText;
    [SerializeField] private Button advanceButton;
    [SerializeField] private GameObject dialogPanel;

    [Header("Settings")]
    [SerializeField] private string speakerName = "NPC";
    [SerializeField] private bool autoAdvance = true;
    [SerializeField] private bool loopDialog;

    private AudioSource _audioSource;
    private PiperTTSAsync _tts;
    private CancellationTokenSource _cts;
    private int _currentLineIndex;
    private bool _isPlaying;
    private bool _waitingForAdvance;

    void Start()
    {
        _audioSource = GetComponent<AudioSource>();
        if (_audioSource == null)
            _audioSource = gameObject.AddComponent<AudioSource>();

        if (dialogPanel != null)
            dialogPanel.SetActive(false);

        if (model == null)
        {
            Debug.LogError("[NPCDialogDemo] No PiperModel assigned.");
            return;
        }

        try
        {
            _tts = PiperTTSAsync.Create(model);
        }
        catch (PiperException ex)
        {
            Debug.LogError($"[NPCDialogDemo] Failed to create engine: {ex.Message}");
            return;
        }

        if (advanceButton != null)
            advanceButton.onClick.AddListener(AdvanceDialog);

        if (speakerNameText != null)
            speakerNameText.text = speakerName;
    }

    void OnDestroy()
    {
        StopDialog();
        _tts?.Dispose();
    }

    /// <summary>
    /// Begin the dialog sequence from the first line.
    /// Call this from a trigger, interaction system, or button.
    /// </summary>
    public void StartDialog()
    {
        if (_tts == null || dialogLines == null || dialogLines.Length == 0) return;
        if (_isPlaying) return;

        _currentLineIndex = 0;
        if (dialogPanel != null)
            dialogPanel.SetActive(true);

        PlayDialogSequence();
    }

    /// <summary>
    /// Stop the dialog and hide the panel.
    /// </summary>
    public void StopDialog()
    {
        if (_cts != null)
        {
            _cts.Cancel();
            _cts.Dispose();
            _cts = null;
        }

        _audioSource.Stop();
        _isPlaying = false;
        _waitingForAdvance = false;

        if (dialogPanel != null)
            dialogPanel.SetActive(false);
    }

    /// <summary>
    /// Advance to the next dialog line. Used when autoAdvance is false.
    /// </summary>
    public void AdvanceDialog()
    {
        if (_waitingForAdvance)
        {
            _waitingForAdvance = false;
        }
        else if (!_isPlaying)
        {
            StartDialog();
        }
    }

    private async void PlayDialogSequence()
    {
        _cts = new CancellationTokenSource();
        var token = _cts.Token;
        _isPlaying = true;

        try
        {
            while (_currentLineIndex < dialogLines.Length)
            {
                if (token.IsCancellationRequested) break;

                var line = dialogLines[_currentLineIndex];
                string lang = string.IsNullOrEmpty(line.language) ? model.defaultLanguage : line.language;

                // Show subtitle
                SetSubtitle(line.text);

                // Synthesize and play
                var clip = await _tts.SynthesizeAsync(line.text, lang, null, token);
                if (token.IsCancellationRequested) break;

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

                if (token.IsCancellationRequested) break;

                // Pause between lines
                if (line.pauseAfter > 0f)
                {
                    float elapsed = 0f;
                    while (elapsed < line.pauseAfter && !token.IsCancellationRequested)
                    {
                        elapsed += Time.deltaTime;
                        await Task.Yield();
                    }
                }

                if (token.IsCancellationRequested) break;

                // Wait for manual advance if autoAdvance is disabled
                if (!autoAdvance)
                {
                    _waitingForAdvance = true;
                    while (_waitingForAdvance && !token.IsCancellationRequested)
                    {
                        await Task.Yield();
                    }
                }

                _currentLineIndex++;
            }

            // Handle loop
            if (loopDialog && !token.IsCancellationRequested)
            {
                _currentLineIndex = 0;
                _isPlaying = false;
                PlayDialogSequence();
                return;
            }
        }
        catch (System.OperationCanceledException)
        {
            // Stopped by StopDialog()
        }
        catch (PiperException ex)
        {
            Debug.LogError($"[NPCDialogDemo] Synthesis error: {ex.Message}");
        }
        finally
        {
            _isPlaying = false;
            SetSubtitle("");

            if (dialogPanel != null)
                dialogPanel.SetActive(false);
        }
    }

    private void SetSubtitle(string text)
    {
        if (subtitleText != null)
            subtitleText.text = text;
    }
}
