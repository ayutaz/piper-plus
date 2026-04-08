// LanguageSwitchDemo.cs — Multilingual language switching demo
//
// Demonstrates:
//   - Querying available languages from the model
//   - Switching language at runtime via dropdown
//   - Synthesizing the same or different text in each language
//   - Language-specific sample texts

using System.Collections.Generic;
using PiperPlus;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Multilingual demo with a dropdown to switch the synthesis language.
/// Attach to a GameObject with an AudioSource. Assign a PiperModel in the Inspector.
/// </summary>
public class LanguageSwitchDemo : MonoBehaviour
{
    /// <summary>
    /// Sample text for each supported language.
    /// </summary>
    [System.Serializable]
    public class LanguageSample
    {
        public string code;
        public string displayName;
        public string sampleText;
    }

    [Header("Model")]
    [SerializeField] private PiperModel model;

    [Header("UI")]
    [SerializeField] private Dropdown languageDropdown;
    [SerializeField] private InputField textInput;
    [SerializeField] private Button speakButton;
    [SerializeField] private Toggle useSampleTextToggle;
    [SerializeField] private Text statusText;

    [Header("Language Samples")]
    [SerializeField] private LanguageSample[] languageSamples = new[]
    {
        new LanguageSample { code = "ja", displayName = "Japanese",   sampleText = "\u3053\u3093\u306b\u3061\u306f\u3001\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3067\u3059\u306d\u3002" },
        new LanguageSample { code = "en", displayName = "English",    sampleText = "Hello, how are you today?" },
        new LanguageSample { code = "zh", displayName = "Chinese",    sampleText = "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u5f88\u597d\u3002" },
        new LanguageSample { code = "es", displayName = "Spanish",    sampleText = "\u00bfHola, c\u00f3mo est\u00e1s hoy?" },
        new LanguageSample { code = "fr", displayName = "French",     sampleText = "Bonjour, comment allez-vous aujourd'hui ?" },
        new LanguageSample { code = "pt", displayName = "Portuguese", sampleText = "Ol\u00e1, como voc\u00ea est\u00e1 hoje?" },
    };

    private AudioSource _audioSource;
    private PiperTTSAsync _tts;
    private readonly List<LanguageSample> _availableLanguages = new List<LanguageSample>();
    private int _selectedLanguageIndex;

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
        }
        catch (PiperException ex)
        {
            SetStatus($"Failed to create engine: {ex.Message}");
            return;
        }

        // Build the dropdown from languages that the model actually supports
        PopulateLanguageDropdown();

        if (speakButton != null)
            speakButton.onClick.AddListener(OnSpeakClicked);

        if (languageDropdown != null)
            languageDropdown.onValueChanged.AddListener(OnLanguageChanged);

        if (useSampleTextToggle != null)
            useSampleTextToggle.onValueChanged.AddListener(OnToggleSampleText);

        UpdateSampleText();
        SetStatus($"Ready. {_availableLanguages.Count} language(s) available.");
    }

    void OnDestroy()
    {
        _tts?.Dispose();
    }

    /// <summary>
    /// Speak the given text in the given language.
    /// </summary>
    public async void Speak(string text, string languageCode)
    {
        if (_tts == null) return;

        SetStatus($"Synthesizing ({languageCode}): \"{text}\"...");

        try
        {
            var clip = await _tts.SynthesizeAsync(text, languageCode);
            if (clip != null)
            {
                _audioSource.clip = clip;
                _audioSource.Play();
                SetStatus($"Playing ({languageCode}): {clip.length:F2}s");
            }
        }
        catch (PiperException ex)
        {
            SetStatus($"Synthesis error: {ex.Message}");
        }
    }

    private void PopulateLanguageDropdown()
    {
        _availableLanguages.Clear();

        // Query which languages are available in the loaded model
        string available = _tts.AvailableLanguages;
        var modelLanguages = new HashSet<string>();

        if (!string.IsNullOrEmpty(available))
        {
            foreach (string lang in available.Split(','))
            {
                string trimmed = lang.Trim();
                if (!string.IsNullOrEmpty(trimmed))
                    modelLanguages.Add(trimmed);
            }
        }

        // Filter to languages the model supports
        foreach (var sample in languageSamples)
        {
            if (modelLanguages.Count == 0 || modelLanguages.Contains(sample.code))
            {
                _availableLanguages.Add(sample);
            }
        }

        // If no match, fall back to all defined samples
        if (_availableLanguages.Count == 0)
        {
            _availableLanguages.AddRange(languageSamples);
        }

        // Populate dropdown
        if (languageDropdown != null)
        {
            languageDropdown.ClearOptions();
            var options = new List<string>();
            foreach (var lang in _availableLanguages)
            {
                options.Add($"{lang.displayName} ({lang.code})");
            }
            languageDropdown.AddOptions(options);
        }

        _selectedLanguageIndex = 0;
    }

    private void OnLanguageChanged(int index)
    {
        _selectedLanguageIndex = index;
        UpdateSampleText();
    }

    private void OnSpeakClicked()
    {
        if (_availableLanguages.Count == 0) return;

        var lang = _availableLanguages[_selectedLanguageIndex];
        string text = textInput != null && !string.IsNullOrEmpty(textInput.text)
            ? textInput.text
            : lang.sampleText;

        Speak(text, lang.code);
    }

    private void OnToggleSampleText(bool useSample)
    {
        UpdateSampleText();
    }

    private void UpdateSampleText()
    {
        bool useSample = useSampleTextToggle == null || useSampleTextToggle.isOn;
        if (useSample && textInput != null && _availableLanguages.Count > 0)
        {
            textInput.text = _availableLanguages[_selectedLanguageIndex].sampleText;
        }
    }

    private void SetStatus(string message)
    {
        Debug.Log($"[LanguageSwitchDemo] {message}");
        if (statusText != null)
            statusText.text = message;
    }
}
