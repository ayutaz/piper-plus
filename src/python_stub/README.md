# piper-tts-plus has been renamed to piper-plus

This package has been renamed to **[piper-plus](https://pypi.org/project/piper-plus/)**.

Please update your dependencies:

```bash
pip install piper-plus
```

If you have `piper-tts-plus` in your `requirements.txt` or `pyproject.toml`, replace it with `piper-plus`.

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
