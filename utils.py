from pathlib import Path
from dataclasses import dataclass

@dataclass
class Result:
    success: bool
    message: str = ""

def all_unique(folder: Path, fn_pattern: str = "") -> bool:
    """
    Check if all files in a folder are unique in terms of content.
    Load each file and compute its hash. If the hash is already in the set, return False.
    fn_pattern: filter files by a pattern in filename
    """
    hashes = set()
    for fn in folder.glob(fn_pattern):
        with open(fn, "rb") as f:
            content = f.read()
        h = hash(content)
        if h in hashes:
            return False
        hashes.add(h)
    return True

