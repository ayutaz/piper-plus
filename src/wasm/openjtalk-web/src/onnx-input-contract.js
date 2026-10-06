/** Speaker feeds follow the loaded ONNX graph, including legacy exports. */
export function readSpeakerInputContract(session) {
  const names = new Set(session.inputNames || []);
  const read = (name, type, ranks) => {
    if (!names.has(name)) {
      return null;
    }
    if (!Array.isArray(session.inputMetadata)) {
      throw new Error(
        "ONNX inputMetadata is required for speaker inputs; use onnxruntime-web >=1.22.0."
      );
    }
    const meta = session.inputMetadata.find((m) => m.name === name);
    if (!meta) {
      throw new Error(`${name}: missing ONNX input metadata.`);
    }
    if (
      meta.isTensor === false ||
      meta.type !== type ||
      !Array.isArray(meta.shape) ||
      !ranks.includes(meta.shape.length)
    ) {
      throw new Error(`${name}: expected ${type} tensor of rank ${ranks.join(" or ")}.`);
    }
    const batch = meta.shape[0];
    if (batch !== 1 && typeof batch !== "string") {
      throw new Error(`${name}: only batch size 1 is supported; declared ${batch}.`);
    }
    return { shape: [...meta.shape] };
  };
  const embedding = read("speaker_embedding", "float32", [2]);
  if (embedding) {
    const dim = embedding.shape[1];
    if (typeof dim !== "string" && (!Number.isSafeInteger(dim) || dim <= 0)) {
      throw new Error(`speaker_embedding: invalid declared dimension ${dim}.`);
    }
  }
  const mask = read("speaker_embedding_mask", "int64", [1, 2]);
  if (mask && mask.shape.length === 2 && mask.shape[1] !== 1) {
    throw new Error("speaker_embedding_mask: expected shape [batch, 1].");
  }
  return { embedding, mask };
}

export function createSpeakerFeeds(ort, contract, speakerEmbedding) {
  const provided = speakerEmbedding !== undefined && speakerEmbedding !== null;
  const { embedding, mask } = contract;
  if (provided && !(speakerEmbedding instanceof Float32Array)) {
    throw new TypeError("speaker_embedding must be a Float32Array.");
  }
  if (provided && !embedding) {
    throw new Error("speaker_embedding is not an input of the loaded model.");
  }
  const feeds = {};
  if (embedding) {
    const declared = embedding.shape[1];
    const dynamic = typeof declared === "string";
    if (!provided && dynamic) {
      throw new Error(
        "speaker_embedding has a dynamic dimension; provide an explicit speakerEmbedding."
      );
    }
    const dim = dynamic ? speakerEmbedding.length : declared;
    if (provided && (speakerEmbedding.length === 0 || speakerEmbedding.length !== dim)) {
      throw new Error(`speaker_embedding: expected ${dim} values, got ${speakerEmbedding.length}.`);
    }
    if (provided && !speakerEmbedding.every(Number.isFinite)) {
      throw new Error("speaker_embedding must contain only finite values.");
    }
    feeds.speaker_embedding = new ort.Tensor(
      "float32",
      provided ? speakerEmbedding : new Float32Array(dim),
      [1, dim]
    );
  }
  if (mask) {
    feeds.speaker_embedding_mask = new ort.Tensor(
      "int64",
      new BigInt64Array([provided ? 1n : 0n]),
      mask.shape.length === 1 ? [1] : [1, 1]
    );
  }
  return feeds;
}
