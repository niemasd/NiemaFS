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

```python
for curr_path, curr_timestamp, curr_data in fs:
    if curr_data is None:
        print('DIR', curr_path, curr_timestamp)
    else:
        print('FILE', curr_path, curr_timestamp, len(curr_data))
```

See the [documentation](https://niema.net/NiemaFS) as well as the [example scripts](scripts) for more information. This repository also contains [example files](example) to test the NiemaFS classes.

### [`DirFS`](https://niema.net/NiemaFS/#niemafs.DirFS) — Directories

```python
from niemafs import DirFS
fs = DirFS(path=target_path)
```

### [`GcmFS`](https://niema.net/NiemaFS/#niemafs.GcmFS) — Nintendo GameCube mini-DVD
Note that the Nintendo GameCube GCM file system does not contain file/folder timestamps. As a result, iterating over a `GcmFS` object will yield `None` for the timestamps.

```python
from niemafs import GcmFS
with open(target_path, 'rb') as target_file:
    fs = GcmFS(path=target_path, file_obj=target_file)
```

### [`IsoFS`](https://niema.net/NiemaFS/#niemafs.IsoFS) — ISO 9660 Disc Image

```python
from niemafs import IsoFS
with open(target_path, 'rb') as target_file:
    fs = IsoFS(path=target_path, file_obj=target_file)
```

### [`TarFS`](https://niema.net/NiemaFS/#niemafs.TarFS) — TAR Archive

```python
from niemafs import TarFS
with open(target_path, 'rb') as target_file:
    fs = TarFS(path=target_path, file_obj=target_file)
```

### [`WiiFS`](https://niema.net/NiemaFS/#niemafs.WiiFS) — Nintendo Wii DVD
Note that, due to the need to decrypt the filesystem, this is extremely memory-intensive (each partition is loaded into memory to process in parallel for speed).

```python
from niemafs import WiiFS
with open(target_path, 'rb') as target_file:
    fs = WiiFS(path=target_path, file_obj=target_file)
```

### [`ZipFS`](https://niema.net/NiemaFS/#niemafs.ZipFS) — ZIP Archive

```python
from niemafs import ZipFS
with open(target_path, 'rb') as target_file:
    fs = ZipFS(path=target_path, file_obj=target_file)
```
