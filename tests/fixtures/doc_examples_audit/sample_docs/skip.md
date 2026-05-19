# Skip-warranted fixtures

```bash
# doctest:skip
sudo systemctl restart audio
```

```python
# noexec — requires GPU
import torch

assert torch.cuda.is_available()
nvidia-smi
```

```text
output should not run
```
