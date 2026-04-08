// PiperModelImporter.cs — Helper for importing .onnx model files

using UnityEditor;
using UnityEngine;

namespace PiperPlus.Editor
{
    /// <summary>
    /// Provides menu items and helpers for importing piper-plus models into Unity.
    /// </summary>
    public static class PiperModelImporter
    {
        /// <summary>
        /// Create a PiperModel asset from a selected .onnx file.
        /// </summary>
        [MenuItem("Assets/Create/Piper Plus/Model from ONNX", false, 200)]
        private static void CreateModelFromOnnx()
        {
            string onnxPath = EditorUtility.OpenFilePanel(
                "Select ONNX Model",
                Application.streamingAssetsPath,
                "onnx");

            if (string.IsNullOrEmpty(onnxPath))
                return;

            // Derive relative path from StreamingAssets
            string streamingAssets = Application.streamingAssetsPath;
            string relativePath = onnxPath;
            if (onnxPath.StartsWith(streamingAssets))
            {
                relativePath = onnxPath.Substring(streamingAssets.Length + 1);
            }

            // Check for config.json alongside the model
            string configPath = onnxPath + ".json";
            string relativeConfigPath = null;
            if (System.IO.File.Exists(configPath))
            {
                if (configPath.StartsWith(streamingAssets))
                {
                    relativeConfigPath = configPath.Substring(streamingAssets.Length + 1);
                }
                else
                {
                    relativeConfigPath = configPath;
                }
            }

            // Create ScriptableObject asset
            var model = ScriptableObject.CreateInstance<PiperModel>();
            model.modelPath = relativePath;
            model.configPath = relativeConfigPath ?? string.Empty;
            model.defaultLanguage = "ja";
            model.speakerId = 0;

            // Derive asset name from model filename
            string modelName = System.IO.Path.GetFileNameWithoutExtension(onnxPath);
            string assetPath = $"Assets/{modelName}.asset";
            assetPath = AssetDatabase.GenerateUniqueAssetPath(assetPath);

            AssetDatabase.CreateAsset(model, assetPath);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            EditorUtility.FocusProjectWindow();
            Selection.activeObject = model;

            string msg = relativeConfigPath != null
                ? $"Created PiperModel: {assetPath}\nConfig found: {relativeConfigPath}"
                : $"Created PiperModel: {assetPath}\nNo config.json found next to model. Set it manually if needed.";

            EditorUtility.DisplayDialog("Piper Plus", msg, "OK");
        }

        /// <summary>
        /// Validate that StreamingAssets directory exists.
        /// </summary>
        [MenuItem("Piper Plus/Setup StreamingAssets", false, 100)]
        private static void SetupStreamingAssets()
        {
            string path = Application.streamingAssetsPath;
            if (!System.IO.Directory.Exists(path))
            {
                System.IO.Directory.CreateDirectory(path);
                AssetDatabase.Refresh();
                Debug.Log($"[PiperPlus] Created StreamingAssets directory: {path}");
            }
            else
            {
                Debug.Log($"[PiperPlus] StreamingAssets directory already exists: {path}");
            }

            EditorUtility.DisplayDialog(
                "Piper Plus",
                $"StreamingAssets directory is ready.\n\n{path}\n\nPlace your .onnx model and .json config files here.",
                "OK");
        }
    }
}
