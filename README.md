# NiemaFS
Niema's Python library for reading data from various file system standards

## Installation
NiemaFS can be installed using `pip`:

```bash
sudo pip install niemafs
```

If you are using a machine on which you lack administrative powers, NiemaFS can be installed locally using `pip`:

```bash
pip install --user niemafs
```

## Usage
The workflow to use each of the NiemaFS classes is as follows:

1. Instantiate the appropriate NiemaFS class by providing a path `path` and a file-like object `file_obj`
2. Iterate over the contents of the NiemaFS object using a for-loop, each iteration of which will yield a `tuple` as follows:
    1. The [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) of the file/folder within the filesystem
    2. The modification timestamp of the file/folder as a [`datetime`](https://docs.python.org/3/library/datetime.html#datetime.datetime)
    3. The contents of the file as [`bytes`](https://docs.python.org/3/library/stdtypes.html#bytes), or `None` for directories

See the [documentation](https://niema.net/NiemaFS) as well as the [example scripts](example) for more information.

### [`DirFS`](https://niema.net/NiemaFS/#niemafs.DirFS) — Directories

```python
from pathlib import Path
target_path = Path('.')

from niemafs import DirFS
fs = DirFS(path=target_path)
for curr_path, curr_timestamp, curr_data in fs:
    if curr_data is None:
        print('DIR', curr_path, curr_timestamp)
    else:
        print('FILE', curr_path, curr_timestamp, len(curr_data))
```

### [`IsoFS`](https://niema.net/NiemaFS/#niemafs.IsoFS) — ISO 9660 Disc Image

```python
from pathlib import Path
target_path = Path('cdrom.iso')

from niemafs import IsoFS
with open(target_path, 'rb') as target_file:
    fs = IsoFS(path=target_path, file_obj=target_file)
    for curr_path, curr_timestamp, curr_data in fs:
        if curr_data is None:
            print('DIR', curr_path, curr_timestamp)
        else:
            print('FILE', curr_path, curr_timestamp, len(curr_data))
```

### [`ZipFS`](https://niema.net/NiemaFS/#niemafs.ZipFS) — ZIP Archive

```python
from pathlib import Path
target_path = Path('archive.zip')

from niemafs import ZipFS
with open(target_path, 'rb') as target_file:
    fs = ZipFS(path=target_path, file_obj=target_file)
    for curr_path, curr_timestamp, curr_data in fs:
        if curr_data is None:
            print('DIR', curr_path, curr_timestamp)
        else:
            print('FILE', curr_path, curr_timestamp, len(curr_data))
```
