# Piper Phonemization Library

Converts text to phonemes for [Piper](https://github.com/rhasspy/piper).

When using eSpeak phonemes, requires an [espeak-ng fork](https://github.com/rhasspy/espeak-ng) with `espeak_TextToPhonemesWithTerminator` function.
This function allows for Piper to preserve punctuation and detect sentence boundaries.


## Usage

Pre-compiled releases are [available for download](https://github.com/rhasspy/piper-phonemize/releases/tag/v1.0.0).

The `piper_phonemize` program can be used from the command line:

``` sh
lib/piper_phonemize -l en-us --espeak-data lib/espeak-ng-data/ <<EOF
This is a test.
This is another test!
EOF
{"phoneme_ids":[1,0,41,0,74,0,31,0,3,0,74,0,38,0,3,0,50,0,3,0,32,0,120,0,61,0,31,0,32,0,10,0,2],"phonemes":["ð","ɪ","s"," ","ɪ","z"," ","ɐ"," ","t","ˈ","ɛ","s","t","."],"processed_text":"This is a test.","text":"This is a test."}
{"phoneme_ids":[1,0,41,0,74,0,31,0,3,0,74,0,38,0,3,0,50,0,26,0,120,0,102,0,41,0,60,0,3,0,32,0,120,0,61,0,31,0,32,0,4,0,2],"phonemes":["ð","ɪ","s"," ","ɪ","z"," ","ɐ","n","ˈ","ʌ","ð","ɚ"," ","t","ˈ","ɛ","s","t","!"],"processed_text":"This is another test!","text":"This is another test!"}
```

Arabic diacritization is supported through [libtashkeel](https://github.com/mush42/libtashkeel/) (model included):

``` sh
echo 'مرحبا' | lib/piper_phonemize -l ar --espeak-data lib/espeak-ng-data/ --tashkeel_model etc/libtashkeel_model.ort
{"phoneme_ids":[1,0,25,0,120,0,14,0,30,0,43,0,14,0,15,0,121,0,14,0,26,0,2],"phonemes":["m","ˈ","a","r","ħ","a","b","ˌ","a","n"],"processed_text":"مَرْحَبًا","text":"مرحبا"}

```

See `src/test.cpp` for a C++ example using `libpiper_phonemize`.

### Python

The `piper_phonemize` Python package is built using [pybind11](https://pybind11.readthedocs.io).

See `src/python_test.py` for a Python example.


## Building

Use Docker:

``` sh
docker buildx build . -t piper-phonemize --output 'type=local,dest=dist'
```

Find library and Python wheels in `dist/`

