using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

[Collection("EnvVars")]
public sealed class CacheStorageTests
{
    // Deterministic 192-dimension graph from build_embedding_fixture.py.
    // Embedded so the real ONNX regression cannot silently skip a missing fixture.
    private const string ModelBase64 = "CAg6hRMKQwoRc3BlYWtlcl9lbWJlZGRpbmcSBG1lYW4iClJlZHVjZU1lYW4qCwoEYXhlc0ABoAEHKg8KCGtlZXBkaW1zGAGgAQIKKAoEbWVhbgoEYXhlcxIPZW1iZWRkaW5nX2F1ZGlvIglVbnNxdWVlemUKJgoEd2F2ZQoPZW1iZWRkaW5nX2F1ZGlvEgh1bm1hc2tlZCIDQWRkChwKCHVubWFza2VkEgZvdXRwdXQiCElkZW50aXR5EhNlbWJlZGRpbmctZGltZW5zaW9uKg0IARAHOgECQgRheGVzKpIQCAEIAQiABBABIoAQAAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL8AAAA/AAAAvwAAAD8AAAC/AAAAPwAAAL9CBHdhdmVaHQoFaW5wdXQSFAoSCAcSDgoCCAEKCBIGbGVuZ3RoWhsKDWlucHV0X2xlbmd0aHMSCgoICAcSBAoCCAFaFAoGc2NhbGVzEgoKCAgBEgQKAggDWiQKEXNwZWFrZXJfZW1iZWRkaW5nEg8KDQgBEgkKAggBCgMIwAFiHQoGb3V0cHV0EhMKEQgBEg0KAggBCgIIAQoDCIAEQgQKABAN";

    [Fact]
    public void Create_ReadOnlyModelDirectory_StillRunsInference()
    {
        if (OperatingSystem.IsWindows())
        {
            Assert.Skip("Unix directory permissions are tested on Linux and macOS.");
            return;
        }

        string directory = NewModelDirectory();
        UnixFileMode originalMode = File.GetUnixFileMode(directory);
        try
        {
            File.SetUnixFileMode(directory, UnixFileMode.UserRead | UnixFileMode.UserExecute);
            Assert.Throws<UnauthorizedAccessException>(
                () => File.WriteAllText(Path.Join(directory, "permission-probe"), "blocked"));
            using InferenceSession session = SessionFactory.Create(Path.Join(directory, "model.onnx"));
            AssertRunsInference(session);
            Assert.False(File.Exists(Path.Join(directory, "model.cpu.opt.onnx")));
            Assert.Empty(Directory.GetFiles(directory, "*.tmp"));
        }
        finally
        {
            File.SetUnixFileMode(directory, originalMode);
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void Create_WritableModelDirectory_PublishesUsableCache()
    {
        string directory = NewModelDirectory();
        try
        {
            string model = Path.Join(directory, "model.onnx");
            using (InferenceSession session = SessionFactory.Create(model))
            {
                AssertRunsInference(session);
            }

            Assert.True(File.Exists(Path.Join(directory, "model.cpu.opt.onnx")));
            Assert.True(File.Exists(Path.Join(directory, "model.cpu.opt.onnx.ok")));
            Assert.Empty(Directory.GetFiles(directory, "*.tmp"));
            using InferenceSession cached = SessionFactory.Create(model);
            AssertRunsInference(cached);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [Fact]
    public void Create_InvalidModel_StillFails()
    {
        string directory = NewModelDirectory();
        try
        {
            string model = Path.Join(directory, "model.onnx");
            File.WriteAllText(model, "invalid ONNX model");
            Assert.Throws<OnnxRuntimeException>(() => SessionFactory.Create(model));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private static string NewModelDirectory()
    {
        string directory = Path.Join(Path.GetTempPath(), "piper-cache-storage-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        File.WriteAllBytes(Path.Join(directory, "model.onnx"), Convert.FromBase64String(ModelBase64));
        return directory;
    }

    private static void AssertRunsInference(InferenceSession session)
    {
        using var input = OrtValue.CreateTensorValueFromMemory(new long[] { 1, 2 }, new long[] { 1, 2 });
        using var lengths = OrtValue.CreateTensorValueFromMemory(new long[] { 2 }, new long[] { 1 });
        using var scales = OrtValue.CreateTensorValueFromMemory(new float[] { 0.4f, 1.0f, 0.5f }, new long[] { 3 });
        using var embedding = OrtValue.CreateTensorValueFromMemory(new float[192], new long[] { 1, 192 });
        using var options = new RunOptions();
        using var results = session.Run(
            options,
            new[] { "input", "input_lengths", "scales", "speaker_embedding" },
            new[] { input, lengths, scales, embedding },
            session.OutputNames);
        float[] samples = results[0].GetTensorDataAsSpan<float>().ToArray();
        Assert.Equal(512, samples.Length);
        Assert.Contains(0.5f, samples);
        Assert.Contains(-0.5f, samples);
    }
}
