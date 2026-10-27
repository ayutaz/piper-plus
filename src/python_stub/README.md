# piper-tts-plus has been renamed to piper-plus

This package has been renamed to **[piper-plus](https://pypi.org/project/piper-plus/)**.

Please update your dependencies. Since piper-plus 2.0.2 the ONNX Runtime
provider is chosen with an extra; install exactly one of them:

```bash
# CPU
pip install "piper-plus[cpu]"
# or NVIDIA GPU (CUDA 12 / cuDNN required)
pip install "piper-plus[gpu]"
```

If you have `piper-tts-plus` in your `requirements.txt` or `pyproject.toml`,
replace it with `piper-plus[cpu]` or `piper-plus[gpu]`.

`piper-tts-plus` passes the same extras on to piper-plus, so an existing
dependency keeps working once it names a provider:

```bash
pip install "piper-tts-plus[cpu]"
```

A bare `piper-tts-plus` (or `piper-plus`) installs no ONNX Runtime; importing
`piper_plus.voice` then raises an `ImportError` that asks for one of the extras.

All future releases will be published under the new name.

## Breaking change in piper-plus >= 2.0

Starting with **piper-plus 2.0**, the Python import name and CLI command were
renamed from `piper` to `piper_plus` (a clean break — no compatibility shim is
shipped). The `piper/` module is no longer bundled, so `import piper` will fail.

- Replace `import piper` / `from piper.X import ...` with
  `import piper_plus` / `from piper_plus.X import ...`.
- Replace the `piper` command with `piper-plus`
  (and `python -m piper[.http_server]` with `python -m piper_plus[...]`).
- To stay on the 1.x line instead, pin `piper-plus<2`.

This rename lets piper-plus co-exist with the upstream `piper-tts` package in the
same environment: `import piper` resolves to upstream rhasspy/piper, while
`import piper_plus` resolves to this fork.

- [PyPI (piper-plus)](https://pypi.org/project/piper-plus/)
- [GitHub](https://github.com/ayutaz/piper-plus)
