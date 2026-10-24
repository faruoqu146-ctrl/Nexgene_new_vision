"""NexGene backend bootstrap — expands chunked compressed application module."""
from pathlib import Path
import zlib, base64, sys, types

_dir = Path(__file__).resolve().parent
_parts = sorted(_dir.glob("payload_*.txt"))
if not _parts:
    raise RuntimeError("NexGene payload chunks missing (payload_*.txt)")
_b64 = "".join(p.read_text() for p in _parts)
_b64 = "".join(_b64.split())  # tolerate newlines/whitespace in chunks
_CODE = zlib.decompress(base64.b64decode(_b64)).decode("utf-8")
_mod = types.ModuleType(__name__)
_mod.__file__ = __file__
_mod.__package__ = __package__
sys.modules[__name__] = _mod
exec(compile(_CODE, __file__, "exec"), _mod.__dict__)
app = _mod.app
