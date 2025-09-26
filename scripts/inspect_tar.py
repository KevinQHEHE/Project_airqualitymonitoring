"""
Utility: inspect a .tar backup archive and print members and collections_metadata.json if present.
Run: python scripts/inspect_tar.py <path-to-tar>
"""
import sys
import tarfile

if len(sys.argv) < 2:
    print("Usage: python scripts/inspect_tar.py <archive.tar>")
    sys.exit(2)

p = sys.argv[1]
try:
    with tarfile.open(p, 'r') as t:
        names = [m.name for m in t.getmembers()]
        print('members:')
        for n in names:
            print(' -', n)
        if 'collections_metadata.json' in names:
            f = t.extractfile('collections_metadata.json')
            print('\ncollections_metadata.json:\n')
            print(f.read().decode('utf-8'))
        else:
            print('\ncollections_metadata.json not found in archive')
except Exception as e:
    print('error:', e)
    sys.exit(1)
