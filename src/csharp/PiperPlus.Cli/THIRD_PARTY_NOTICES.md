# Third-Party Notices — PiperPlus.Cli

PiperPlus.Cli embeds the following data files from
`src/rust/piper-plus-g2p/data/` as resources of `PiperPlus.Cli.dll`.

| Embedded file | License | Source | Purpose |
|---------------|---------|--------|---------|
| `cmudict_data.json` | BSD-style (CMU) | [CMU Pronouncing Dictionary v0.7b](http://www.speech.cs.cmu.edu/cgi-bin/cmudict) | English word → ARPABET lookup |
| `pinyin_single.json` | MIT | [pypinyin](https://github.com/mozillazg/python-pinyin) | Chinese single character → pinyin |
| `pinyin_phrases.json` | MIT | [pypinyin](https://github.com/mozillazg/python-pinyin) | Chinese phrase → pinyin |

The NuGet dependencies (ONNX Runtime, DotNetG2P, System.CommandLine) carry
their own license files in their packages.

### CMU Pronouncing Dictionary License

> The Carnegie Mellon University Pronouncing Dictionary [cmudict.0.7b]
> [...]
> Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without
> modification, are permitted provided that the following conditions
> are met:
>
> 1. Redistributions of source code must retain the above copyright
>    notice, this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright
>    notice, this list of conditions and the following disclaimer in
>    the documentation and/or other materials provided with the
>    distribution.
> 3. The name "Carnegie Mellon University" must not be used to endorse
>    or promote products derived from this software without prior
>    written permission. For permission, please contact
>    <sphinx@cs.cmu.edu>.
> 4. Products derived from this software may not be called "Carnegie
>    Mellon Pronouncing Dictionary" nor may "Carnegie Mellon" appear
>    in their names without prior written permission of Carnegie
>    Mellon University.
> 5. Redistributions of any form whatsoever must retain the following
>    acknowledgment: "This product includes data from the Carnegie
>    Mellon Pronouncing Dictionary, which is freely available at
>    <http://www.speech.cs.cmu.edu/cgi-bin/cmudict>."
>
> THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY "AS IS" AND
> ANY EXPRESSED OR IMPLIED WARRANTIES ARE DISCLAIMED.

### pypinyin License (MIT)

> Copyright (c) 2016 mozillazg, 闲耘 ([hotoo.cn@gmail.com](mailto:hotoo.cn@gmail.com))
>
> Permission is hereby granted, free of charge, to any person obtaining
> a copy of this software and associated documentation files (the
> "Software"), to deal in the Software without restriction, including
> without limitation the rights to use, copy, modify, merge, publish,
> distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to
> the following conditions:
>
> The above copyright notice and this permission notice shall be
> included in all copies or substantial portions of the Software.
