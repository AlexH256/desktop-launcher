编译：

```Shell
uv run python -m nuitka --mode=standalone --zig --python-flag=-m --include-package=desktop_launcher --output-dir=dist --remove-output --enable-plugin=pyside6 src/desktop_launcher
```
