import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readSpeakerInputContract, createSpeakerFeeds } from "../../src/onnx-input-contract.js";

const ort = {
  Tensor: class {
    constructor(type, data, dims) {
      Object.assign(this, { type, data, dims });
    }
  },
};
function session(dim = 256, maskShape = ["batch", 1]) {
  const inputMetadata = [
    { name: "speaker_embedding", isTensor: true, type: "float32", shape: ["batch", dim] },
  ];
  if (maskShape) {
    inputMetadata.push({
      name: "speaker_embedding_mask",
      isTensor: true,
      type: "int64",
      shape: maskShape,
    });
  }
  return { inputNames: inputMetadata.map((m) => m.name), inputMetadata };
}

describe("ONNX speaker input contract", () => {
  for (const dim of [192, 256, 320]) {
    it(`uses the declared ${dim}-dimensional zero embedding and rank-2 mask`, () => {
      const feeds = createSpeakerFeeds(ort, readSpeakerInputContract(session(dim)));
      assert.deepEqual(feeds.speaker_embedding.dims, [1, dim]);
      assert.equal(feeds.speaker_embedding.data.length, dim);
      assert.ok(feeds.speaker_embedding.data.every((x) => x === 0));
      assert.deepEqual(feeds.speaker_embedding_mask.dims, [1, 1]);
      assert.deepEqual(Array.from(feeds.speaker_embedding_mask.data), [0n]);
    });
  }
  it("passes a supplied embedding unchanged with mask=1", () => {
    const emb = new Float32Array(256).fill(0.1);
    const feeds = createSpeakerFeeds(ort, readSpeakerInputContract(session()), emb);
    assert.strictEqual(feeds.speaker_embedding.data, emb);
    assert.deepEqual(Array.from(feeds.speaker_embedding_mask.data), [1n]);
  });
  it("preserves a declared rank-1 mask", () => {
    const feeds = createSpeakerFeeds(ort, readSpeakerInputContract(session(192, ["batch"])));
    assert.deepEqual(feeds.speaker_embedding_mask.dims, [1]);
  });
  it("does not feed an undeclared mask", () => {
    const feeds = createSpeakerFeeds(ort, readSpeakerInputContract(session(192, null)));
    assert.equal(feeds.speaker_embedding_mask, undefined);
  });
  it("does not add speaker feeds to a model without speaker inputs", () => {
    const contract = readSpeakerInputContract({ inputNames: ["input"] });
    assert.deepEqual(createSpeakerFeeds(ort, contract), {});
    assert.throws(
      () => createSpeakerFeeds(ort, contract, new Float32Array(192)),
      /speaker_embedding.*not.*input/i
    );
  });
  for (const emb of [
    new Float32Array(192),
    new Float32Array(0),
    new Float32Array(256).fill(NaN),
    new Float32Array(256).fill(Infinity),
  ]) {
    it(`rejects invalid embedding length=${emb.length} first=${emb[0]}`, () => {
      assert.throws(
        () => createSpeakerFeeds(ort, readSpeakerInputContract(session()), emb),
        /speaker_embedding/
      );
    });
  }
  it("rejects non-Float32Array input", () => {
    assert.throws(
      () => createSpeakerFeeds(ort, readSpeakerInputContract(session()), [1]),
      TypeError
    );
  });
  it("uses an explicit embedding for a symbolic dimension, and rejects guessing", () => {
    const contract = readSpeakerInputContract(session("embedding_dim"));
    assert.throws(() => createSpeakerFeeds(ort, contract), /speaker_embedding.*dynamic/i);
    assert.deepEqual(
      createSpeakerFeeds(ort, contract, new Float32Array(320)).speaker_embedding.dims,
      [1, 320]
    );
  });
  it("explains missing metadata on older runtimes", () => {
    assert.throws(
      () => readSpeakerInputContract({ inputNames: ["speaker_embedding"] }),
      /inputMetadata.*1\.22/
    );
  });
  it("rejects an input name whose metadata is absent", () => {
    const s = session();
    s.inputMetadata.pop();
    assert.throws(() => readSpeakerInputContract(s), /speaker_embedding_mask.*metadata/i);
  });
  for (const [name, change] of [
    [
      "embedding dtype",
      (s) => {
        s.inputMetadata[0].type = "float64";
      },
    ],
    [
      "embedding rank",
      (s) => {
        s.inputMetadata[0].shape = [256];
      },
    ],
    [
      "zero dimension",
      (s) => {
        s.inputMetadata[0].shape = ["batch", 0];
      },
    ],
    [
      "fixed batch > 1",
      (s) => {
        s.inputMetadata[0].shape = [2, 256];
      },
    ],
    [
      "mask dtype",
      (s) => {
        s.inputMetadata[1].type = "float32";
      },
    ],
    [
      "mask rank",
      (s) => {
        s.inputMetadata[1].shape = [1, 1, 1];
      },
    ],
    [
      "mask width",
      (s) => {
        s.inputMetadata[1].shape = ["batch", 2];
      },
    ],
    [
      "dynamic mask width",
      (s) => {
        s.inputMetadata[1].shape = ["batch", "width"];
      },
    ],
  ]) {
    it(`rejects unsupported ${name}`, () => {
      const s = session();
      change(s);
      assert.throws(() => readSpeakerInputContract(s), /speaker_embedding/);
    });
  }
});
