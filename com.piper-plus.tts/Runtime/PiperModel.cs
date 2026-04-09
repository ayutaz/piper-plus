// PiperModel.cs — ScriptableObject for piper-plus model configuration

using UnityEngine;

namespace PiperPlus
{
    /// <summary>
    /// ScriptableObject that holds references to a piper-plus ONNX model and its config.
    /// Create via Assets > Create > Piper Plus > Model in the Unity editor.
    /// </summary>
    [CreateAssetMenu(fileName = "PiperModel", menuName = "Piper Plus/Model")]
    public class PiperModel : ScriptableObject
    {
        [Tooltip("Path to the .onnx model file. Can be absolute or relative to StreamingAssets.")]
        public string modelPath;

        [Tooltip("Path to the .json config file. Leave empty to use model_path + '.json'.")]
        public string configPath;

        [Tooltip("Default language code for synthesis (e.g., 'ja', 'en', 'zh').")]
        public string defaultLanguage = "ja";

        [Tooltip("Default speaker ID for multi-speaker models.")]
        public int speakerId;

        [Tooltip("Optional path to OpenJTalk dictionary directory. Leave empty for auto-detect.")]
        public string dictDir;

        [Tooltip("ONNX Runtime execution provider. Leave empty for CPU.")]
        public string provider;

        /// <summary>
        /// Resolve model path, checking StreamingAssets if the path is relative.
        /// </summary>
        public string ResolvedModelPath
        {
            get
            {
                if (string.IsNullOrEmpty(modelPath))
                    return string.Empty;

                if (System.IO.Path.IsPathRooted(modelPath))
                    return modelPath;

                return System.IO.Path.Combine(Application.streamingAssetsPath, modelPath);
            }
        }

        /// <summary>
        /// Resolve config path, checking StreamingAssets if the path is relative.
        /// Returns null if configPath is empty (native library auto-resolves).
        /// </summary>
        public string ResolvedConfigPath
        {
            get
            {
                if (string.IsNullOrEmpty(configPath))
                    return null;

                if (System.IO.Path.IsPathRooted(configPath))
                    return configPath;

                return System.IO.Path.Combine(Application.streamingAssetsPath, configPath);
            }
        }
    }
}
