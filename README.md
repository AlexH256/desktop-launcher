编译：

```Shell
uv run python -m nuitka --mode=standalone --zig --python-flag=-m --include-package=desktop_launcher --output-dir=dist --remove-output --enable-plugin=pyside6 --include-data-dir=assets=assets --windows-icon-from-ico=assets/icon.ico --windows-console-mode=disable src/desktop_launcher
```
