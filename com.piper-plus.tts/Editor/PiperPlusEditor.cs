// PiperPlusEditor.cs — Custom Inspector for PiperModel ScriptableObject

using UnityEditor;
using UnityEngine;

namespace PiperPlus.Editor
{
    [CustomEditor(typeof(PiperModel))]
    public class PiperPlusEditor : UnityEditor.Editor
    {
        private SerializedProperty _modelPath;
        private SerializedProperty _configPath;
        private SerializedProperty _defaultLanguage;
        private SerializedProperty _speakerId;
        private SerializedProperty _dictDir;
        private SerializedProperty _provider;

        private string _testText = "Hello, this is a test.";
        private bool _showAdvanced;
        private string _statusMessage;
        private MessageType _statusType;

        private static readonly string[] LanguageOptions = {
            "ja", "en", "zh", "ko", "es", "fr", "pt", "sv"
        };

        private void OnEnable()
        {
            _modelPath       = serializedObject.FindProperty("modelPath");
            _configPath      = serializedObject.FindProperty("configPath");
            _defaultLanguage = serializedObject.FindProperty("defaultLanguage");
            _speakerId       = serializedObject.FindProperty("speakerId");
            _dictDir         = serializedObject.FindProperty("dictDir");
            _provider        = serializedObject.FindProperty("provider");
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();

            EditorGUILayout.LabelField("Piper Plus Model", EditorStyles.boldLabel);
            EditorGUILayout.Space(4);

            // Model path with file picker
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PropertyField(_modelPath, new GUIContent("Model (.onnx)"));
            if (GUILayout.Button("Browse", GUILayout.Width(60)))
            {
                string path = EditorUtility.OpenFilePanel("Select ONNX Model", "", "onnx");
                if (!string.IsNullOrEmpty(path))
                {
                    // Convert to relative path from StreamingAssets if possible
                    string streamingAssets = Application.streamingAssetsPath;
                    if (path.StartsWith(streamingAssets))
                    {
                        path = path.Substring(streamingAssets.Length + 1);
                    }
                    _modelPath.stringValue = path;
                }
            }
            EditorGUILayout.EndHorizontal();

            // Config path with file picker
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PropertyField(_configPath, new GUIContent("Config (.json)"));
            if (GUILayout.Button("Browse", GUILayout.Width(60)))
            {
                string path = EditorUtility.OpenFilePanel("Select Config JSON", "", "json");
                if (!string.IsNullOrEmpty(path))
                {
                    string streamingAssets = Application.streamingAssetsPath;
                    if (path.StartsWith(streamingAssets))
                    {
                        path = path.Substring(streamingAssets.Length + 1);
                    }
                    _configPath.stringValue = path;
                }
            }
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(4);

            // Language dropdown
            int currentLangIndex = System.Array.IndexOf(LanguageOptions, _defaultLanguage.stringValue);
            if (currentLangIndex < 0) currentLangIndex = 0;

            int selectedIndex = EditorGUILayout.Popup(
                "Default Language",
                currentLangIndex,
                LanguageOptions);

            if (selectedIndex >= 0 && selectedIndex < LanguageOptions.Length)
            {
                _defaultLanguage.stringValue = LanguageOptions[selectedIndex];
            }

            EditorGUILayout.PropertyField(_speakerId, new GUIContent("Speaker ID"));

            // Advanced section
            EditorGUILayout.Space(4);
            _showAdvanced = EditorGUILayout.Foldout(_showAdvanced, "Advanced Settings");
            if (_showAdvanced)
            {
                EditorGUI.indentLevel++;
                EditorGUILayout.PropertyField(_dictDir, new GUIContent("Dict Directory"));
                EditorGUILayout.PropertyField(_provider, new GUIContent("ORT Provider"));
                EditorGUI.indentLevel--;
            }

            EditorGUILayout.Space(8);

            // Validation
            if (string.IsNullOrEmpty(_modelPath.stringValue))
            {
                EditorGUILayout.HelpBox(
                    "Model path is required. Place your .onnx model in StreamingAssets and set the path.",
                    MessageType.Warning);
            }

            // Test synthesis section
            EditorGUILayout.LabelField("Test Synthesis", EditorStyles.boldLabel);
            _testText = EditorGUILayout.TextField("Test Text", _testText);

            if (GUILayout.Button("Synthesize Test Audio"))
            {
                TestSynthesize();
            }

            if (!string.IsNullOrEmpty(_statusMessage))
            {
                EditorGUILayout.HelpBox(_statusMessage, _statusType);
            }

            serializedObject.ApplyModifiedProperties();
        }

        private void TestSynthesize()
        {
            var model = (PiperModel)target;

            if (string.IsNullOrEmpty(model.modelPath))
            {
                _statusMessage = "Model path is not set.";
                _statusType = MessageType.Error;
                return;
            }

            string resolvedPath = model.ResolvedModelPath;
            if (!System.IO.File.Exists(resolvedPath))
            {
                _statusMessage = $"Model file not found: {resolvedPath}";
                _statusType = MessageType.Error;
                return;
            }

            PiperTTS tts = null;
            try
            {
                tts = PiperTTS.Create(model);
                var clip = tts.Synthesize(_testText, model.defaultLanguage);

                if (clip != null)
                {
                    // Play in editor using a temporary AudioSource
                    var go = new GameObject("PiperTTS_Preview");
                    go.hideFlags = HideFlags.HideAndDontSave;
                    var source = go.AddComponent<AudioSource>();
                    source.clip = clip;
                    source.Play();

                    // Schedule cleanup after clip finishes
                    float duration = clip.length + 0.5f;
                    EditorApplication.delayCall += () =>
                    {
                        EditorApplication.delayCall += () =>
                        {
                            if (go != null)
                                Object.DestroyImmediate(go);
                        };
                    };

                    _statusMessage = $"Synthesis succeeded: {clip.length:F2}s, {clip.frequency} Hz, {clip.samples} samples";
                    _statusType = MessageType.Info;
                }
                else
                {
                    _statusMessage = "Synthesis returned empty audio.";
                    _statusType = MessageType.Warning;
                }
            }
            catch (System.Exception ex)
            {
                _statusMessage = $"Synthesis failed: {ex.Message}";
                _statusType = MessageType.Error;
            }
            finally
            {
                tts?.Dispose();
            }
        }
    }
}
