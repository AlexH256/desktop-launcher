本文件指导opencode AGENT进行项目编写

```
uv add <PACKAGES> #添加依赖
uv run <FILE> #运行文件
uv run python -m desktop_launcher #运行项目
uv run pytest #运行测试
```

\__main__.py 薄入口
main.py 主逻辑
/core 核心模块

编写过程中：
模块之间使用绝对引用
编写时先设计方案，后分析是否有冗余，然后更新设计，最后写入

项目功能：
在Windows下运行
使用全局快捷键呼出悬浮窗口并聚焦，窗口具有搜索栏，输入关键字，从指定路径下的lnk文件匹配文件名，选中，启动程序
