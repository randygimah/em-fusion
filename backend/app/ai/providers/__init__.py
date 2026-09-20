"""One module per provider, and the only place a provider may be named.

Everything above this package is handed a `HypothesisGenerator` and cannot
tell which one it has. The purity check in `tests/test_ai_service.py` reads
the syntax tree of every module in `app/ai/` and allows a provider library
to be imported only here.
"""
