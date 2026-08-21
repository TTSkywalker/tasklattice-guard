from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict

from ..runtime.contracts import NeMoConfigSnapshot


_TASKLATTICE_COMPILER_VERSION = re.compile(r"^tasklattice-nemo-config-v(\d+)$")


def config_checksum(snapshot: NeMoConfigSnapshot) -> str:
    """Return the immutable artifact identity used when the snapshot was built.

    Runtime profile and Colang 1 result variables were added to the Python
    contract in compiler v6. Deserializing a pre-v6 JSON artifact fills those
    fields with compatibility defaults; excluding them for the legacy hash keeps
    the released checksum stable across a process upgrade.
    """
    payload = asdict(snapshot)
    match = _TASKLATTICE_COMPILER_VERSION.fullmatch(snapshot.compiler_version)
    if match is not None and int(match.group(1)) < 6:
        payload.pop("runtime_profile", None)
        for binding in payload.get("action_bindings", ()):
            if isinstance(binding, dict):
                binding.pop("result_var", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
