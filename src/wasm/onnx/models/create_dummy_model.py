#!/usr/bin/env python3
"""
Create a dummy ONNX model for testing the Japanese TTS pipeline
"""

import numpy as np
import onnx
from onnx import TensorProto, helper
import json

def create_dummy_japanese_tts_model():
    """Create a simple ONNX model that mimics VITS architecture"""
    
    # Model parameters
    num_phonemes = 41  # Based on config.json
    hidden_size = 128
    num_speakers = 1
    
    # Input: phoneme IDs
    phoneme_input = helper.make_tensor_value_info(
        'phoneme_ids', TensorProto.INT64, ['batch_size', 'sequence_length']
    )
    
    # Input: phoneme lengths
    length_input = helper.make_tensor_value_info(
        'phoneme_lengths', TensorProto.INT64, ['batch_size']
    )
    
    # Input: speaker ID (optional)
    speaker_input = helper.make_tensor_value_info(
        'speaker_id', TensorProto.INT64, ['batch_size']
    )
    
    # Input: scales
    scales_input = helper.make_tensor_value_info(
        'scales', TensorProto.FLOAT, [3]  # noise_scale, length_scale, noise_w
    )
    
    # Output: audio waveform
    audio_output = helper.make_tensor_value_info(
        'audio', TensorProto.FLOAT, ['batch_size', 'audio_length']
    )
    
    # Create dummy weights for embedding
    embedding_weight = np.random.randn(num_phonemes, hidden_size).astype(np.float32)
    embedding_tensor = helper.make_tensor(
        'embedding_weight',
        TensorProto.FLOAT,
        [num_phonemes, hidden_size],
        embedding_weight.flatten().tolist()
    )
    
    # Create a simple graph that:
    # 1. Embeds phonemes
    # 2. Generates fixed-length audio (for testing)
    
    # Embedding lookup
    embed_node = helper.make_node(
        'Gather',
        inputs=['embedding_weight', 'phoneme_ids'],
        outputs=['embedded_phonemes'],
        axis=0
    )
    
    # Flatten embeddings
    flatten_node = helper.make_node(
        'Flatten',
        inputs=['embedded_phonemes'],
        outputs=['flattened_features'],
        axis=1
    )
    
    # Generate dummy audio (simplified - just returns noise shaped by input)
    # In a real model, this would be the decoder network
    
    # Create a fixed output size matrix
    output_projection = np.random.randn(hidden_size * 100, 22050).astype(np.float32) * 0.1
    output_tensor = helper.make_tensor(
        'output_projection',
        TensorProto.FLOAT,
        [hidden_size * 100, 22050],
        output_projection.flatten().tolist()
    )
    
    # MatMul to generate audio
    matmul_node = helper.make_node(
        'MatMul',
        inputs=['flattened_features', 'output_projection'],
        outputs=['raw_audio']
    )
    
    # Tanh activation (to keep audio in reasonable range)
    tanh_node = helper.make_node(
        'Tanh',
        inputs=['raw_audio'],
        outputs=['audio']
    )
    
    # Create the graph
    graph = helper.make_graph(
        [embed_node, flatten_node, matmul_node, tanh_node],
        'japanese_tts_dummy',
        [phoneme_input, length_input, speaker_input, scales_input],
        [audio_output],
        [embedding_tensor, output_tensor]
    )
    
    # Create the model
    model = helper.make_model(
        graph,
        producer_name='piper_tts',
        producer_version='1.0.0',
        doc_string='Dummy Japanese TTS model for testing'
    )
    
    # Add metadata
    model.metadata_props.append(
        helper.make_model_metadataprop('language', 'ja')
    )
    model.metadata_props.append(
        helper.make_model_metadataprop('sample_rate', '22050')
    )
    
    # Set opset version
    model.opset_import[0].version = 13
    
    return model

def main():
    # Create the dummy model
    model = create_dummy_japanese_tts_model()
    
    # Check the model
    onnx.checker.check_model(model)
    
    # Save the model
    output_path = 'ja_JP/ja_JP.onnx'
    onnx.save(model, output_path)
    
    print(f"Dummy model saved to {output_path}")
    
    # Print model info
    print("\nModel inputs:")
    for input in model.graph.input:
        print(f"  - {input.name}: {[dim.dim_value if dim.HasField('dim_value') else 'dynamic' for dim in input.type.tensor_type.shape.dim]}")
    
    print("\nModel outputs:")
    for output in model.graph.output:
        print(f"  - {output.name}: {[dim.dim_value if dim.HasField('dim_value') else 'dynamic' for dim in output.type.tensor_type.shape.dim]}")

if __name__ == '__main__':
    main()