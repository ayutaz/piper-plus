# V3 Implementation Plan - Advanced Accuracy Improvements

## Overview
V3 branch focuses on implementing the three remaining high-impact features that will bring piper-plus to state-of-the-art quality levels.

## Implementation Schedule

### Phase 1: WavLM Discriminator (Days 1-7)

#### Day 1-2: Research and Design
- [ ] Study WavLM architecture and integration patterns from StyleTTS2
- [ ] Design integration approach with existing Multi-Period Discriminator
- [ ] Plan memory-efficient implementation strategy

#### Day 3-4: Core Implementation
- [ ] Create `wavlm_discriminator.py`
- [ ] Implement WavLM feature extraction
- [ ] Add discriminator head for multi-scale discrimination
- [ ] Implement gradient management (frozen layers)

#### Day 5-6: Integration
- [ ] Integrate with `lightning.py` training loop
- [ ] Add configuration flags
- [ ] Implement mixed discriminator loss
- [ ] Add memory optimization options

#### Day 7: Testing
- [ ] Unit tests
- [ ] Memory usage verification
- [ ] Training stability checks

### Phase 2: Japanese BERT Embeddings (Days 8-11)

#### Day 8: Design
- [ ] Select optimal Japanese BERT model (tohoku-bert vs waseda-roberta)
- [ ] Design phoneme-BERT alignment strategy
- [ ] Plan ONNX export approach

#### Day 9-10: Implementation
- [ ] Create `bert_encoder.py`
- [ ] Implement token-to-phoneme alignment
- [ ] Add contextual embedding extraction
- [ ] Integrate with text encoder

#### Day 11: ONNX Compatibility
- [ ] Implement pre-computation strategy for inference
- [ ] Test ONNX export
- [ ] Optimize memory usage

### Phase 3: Conditional Flow Matching (Days 12-21)

#### Day 12-14: Research and Design
- [ ] Study Matcha-TTS implementation
- [ ] Design replacement strategy for normalizing flows
- [ ] Plan backward compatibility approach

#### Day 15-17: Core Implementation
- [ ] Create `flow_matching.py`
- [ ] Implement ODE-based flow
- [ ] Add velocity field predictor
- [ ] Implement efficient sampling

#### Day 18-19: Integration
- [ ] Replace existing flow in VITS
- [ ] Update training objectives
- [ ] Add configuration options
- [ ] Ensure backward compatibility

#### Day 20-21: Optimization
- [ ] Performance tuning
- [ ] Memory optimization
- [ ] Extensive testing

## Technical Details

### 1. WavLM Discriminator

```python
# src/python/piper_train/vits/wavlm_discriminator.py

import torch
import torch.nn as nn
from transformers import WavLMModel, WavLMConfig

class WavLMDiscriminator(nn.Module):
    def __init__(
        self,
        pretrained_model: str = "microsoft/wavlm-base",
        freeze_feature_extractor: bool = True,
        freeze_encoder_layers: int = 10,
        hidden_size: int = 768,
        num_heads: int = 4
    ):
        super().__init__()
        
        # Load pretrained WavLM
        self.wavlm = WavLMModel.from_pretrained(pretrained_model)
        
        # Freeze layers for feature extraction
        if freeze_feature_extractor:
            for param in self.wavlm.feature_extractor.parameters():
                param.requires_grad = False
                
        # Freeze encoder layers
        for i in range(freeze_encoder_layers):
            for param in self.wavlm.encoder.layers[i].parameters():
                param.requires_grad = False
        
        # Multi-scale discriminator heads
        self.discriminators = nn.ModuleList([
            DiscriminatorHead(hidden_size, 256),  # Frame-level
            DiscriminatorHead(hidden_size, 512),  # Segment-level
            DiscriminatorHead(hidden_size, 1024)  # Utterance-level
        ])
        
    def forward(self, y, y_hat):
        # Extract features
        y_features = self.wavlm(y, output_hidden_states=True)
        y_hat_features = self.wavlm(y_hat, output_hidden_states=True)
        
        # Use multiple layers
        y_hiddens = torch.stack(y_features.hidden_states[-4:], dim=1)
        y_hat_hiddens = torch.stack(y_hat_features.hidden_states[-4:], dim=1)
        
        # Discriminate at multiple scales
        outputs = []
        feature_maps = []
        
        for disc in self.discriminators:
            y_d, y_fm = disc(y_hiddens)
            y_hat_d, y_hat_fm = disc(y_hat_hiddens)
            outputs.append((y_d, y_hat_d))
            feature_maps.append((y_fm, y_hat_fm))
            
        return outputs, feature_maps
```

### 2. Japanese BERT Integration

```python
# src/python/piper_train/vits/bert_encoder.py

from transformers import AutoModel, AutoTokenizer
import torch
import torch.nn as nn

class JapaneseBERTEncoder(nn.Module):
    def __init__(
        self,
        model_name: str = "cl-tohoku/bert-base-japanese-v3",
        hidden_channels: int = 192,
        freeze_layers: int = 8
    ):
        super().__init__()
        
        # Load BERT
        self.bert = AutoModel.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Freeze lower layers
        for i in range(freeze_layers):
            for param in self.bert.encoder.layer[i].parameters():
                param.requires_grad = False
        
        # Projection layer
        self.projection = nn.Linear(768, hidden_channels)
        
        # Alignment network
        self.aligner = PhonemeAligner(hidden_channels)
        
    def forward(self, texts, phoneme_ids, phoneme_lengths):
        # Tokenize texts
        inputs = self.tokenizer(
            texts, 
            return_tensors="pt",
            padding=True,
            truncation=True
        )
        
        # Get BERT embeddings
        outputs = self.bert(**inputs)
        bert_features = outputs.last_hidden_state
        
        # Project to VITS dimension
        bert_features = self.projection(bert_features)
        
        # Align to phonemes
        aligned_features = self.aligner(
            bert_features, 
            phoneme_ids, 
            phoneme_lengths
        )
        
        return aligned_features
```

### 3. Conditional Flow Matching

```python
# src/python/piper_train/vits/flow_matching.py

import torch
import torch.nn as nn
from torchdiffeq import odeint

class ConditionalFlowMatching(nn.Module):
    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        n_layers: int,
        gin_channels: int = 0
    ):
        super().__init__()
        
        # Velocity field predictor
        self.velocity_net = VelocityNet(
            channels, 
            hidden_channels,
            kernel_size,
            n_layers
        )
        
        # Time embedding
        self.time_embedding = nn.Sequential(
            nn.Linear(1, hidden_channels),
            nn.SiLU(),
            nn.Linear(hidden_channels, hidden_channels)
        )
        
        # Conditional projection
        if gin_channels > 0:
            self.cond_layer = nn.Conv1d(gin_channels, hidden_channels, 1)
            
    def forward(self, x, x_mask, g=None, reverse=False):
        if not reverse:
            # Training: compute loss
            t = torch.rand(x.shape[0], 1, 1).to(x.device)
            t_emb = self.time_embedding(t)
            
            # Sample noise
            z = torch.randn_like(x)
            
            # Interpolate
            x_t = t * x + (1 - t) * z
            
            # Predict velocity
            v_pred = self.velocity_net(x_t, t_emb, x_mask, g)
            
            # Target velocity
            v_target = x - z
            
            # Loss
            loss = ((v_pred - v_target) ** 2 * x_mask).sum() / x_mask.sum()
            
            return z, loss
        else:
            # Inference: solve ODE
            def ode_func(t, x_t):
                t_emb = self.time_embedding(t.view(1, 1, 1))
                return self.velocity_net(x_t, t_emb, x_mask, g)
            
            # Solve from noise to data
            z = x
            x = odeint(ode_func, z, torch.linspace(0, 1, 10).to(z.device))[-1]
            
            return x
```

## Integration Points

### Training Loop Updates
```python
# In lightning.py

if self.hparams.use_wavlm_discriminator:
    # WavLM discriminator loss
    wavlm_outputs, wavlm_fmaps = self.wavlm_discriminator(y, y_hat)
    loss_wavlm = wavlm_discriminator_loss(wavlm_outputs)
    loss_fm_wavlm = feature_loss(wavlm_fmaps)
    
    # Weight the losses
    loss_gen_all += self.hparams.c_wavlm * (loss_wavlm + loss_fm_wavlm)

if self.hparams.use_bert_encoder:
    # Add BERT features to text encoding
    bert_features = self.bert_encoder(
        batch.texts, 
        x, 
        x_lengths
    )
    x = x + bert_features * self.hparams.bert_weight
```

## Risk Mitigation

### Memory Management
- Gradient checkpointing for WavLM
- Mixed precision training
- Optional CPU offloading for BERT

### Backward Compatibility
- Feature flags for all new components
- Fallback to original implementations
- Checkpoint conversion utilities

### Performance Optimization
- Cached BERT embeddings for common phrases
- Efficient ODE solvers for flow matching
- Multi-GPU support optimizations

## Success Metrics

### Quality Targets
- WavLM: MOS improvement +0.15-0.25
- BERT: MOS improvement +0.06-0.10  
- Flow Matching: MOS improvement +0.10-0.15
- Total v3 improvement: +0.31-0.50

### Performance Targets
- Training time increase: <2x
- Inference time increase: <1.5x (with optimizations)
- Memory usage increase: <2GB (training)

## Testing Strategy

### Unit Tests
- Individual component tests
- Integration tests
- Memory leak tests

### Quality Tests
- A/B testing with v2 models
- MOS evaluation on test set
- Perceptual quality metrics

### Performance Tests
- Training speed benchmarks
- Inference latency tests
- Memory usage profiling

## Rollout Plan

1. **Alpha Release**: After each component implementation
2. **Beta Release**: After all components integrated
3. **Stable Release**: After 1 week of testing

## Documentation Updates

- [ ] Update accuracy-improvements-ja.md
- [ ] Create v3-features.md
- [ ] Update training guide
- [ ] Add migration guide from v2

This plan ensures systematic implementation of the remaining features while maintaining code quality and backward compatibility.