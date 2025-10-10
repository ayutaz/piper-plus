"""ONNX-based models for Japanese phonemization disambiguation.

This module contains ML models for disambiguating Japanese readings,
particularly for the character "何" (nani/nan).

Original source: kabosu-core (https://github.com/q9uri/kabosu-core)
License: MIT (see COPYING file)
"""

from .nani_predict import predict

__all__ = ["predict"]
