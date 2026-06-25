import os
from pathlib import Path

from src.storage.db import ContentStore

ROOT = Path(__file__).parent.parent

def main():
    store = ContentStore()
    
    # Collect all referenced file paths from database
    referenced = set()
    for item in store.list_all(limit=1000):
        if item.video_path:
            referenced.add(str(ROOT / item.video_path))

    # Find and delete unreferenced files
    deleted = 0
    freed = 0
    for dir_name in ["videos", "thumbnails", "subtitles", "screenshots"]:
        d = ROOT / "output" / dir_name
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file() and str(f) not in referenced:
                sz = f.stat().st_size
                f.unlink()
                deleted += 1
                freed += sz

    print(f"Deleted {deleted} files, freed {freed / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()
