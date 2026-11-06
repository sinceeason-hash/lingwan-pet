# 凌丸 · 桌面桌宠

一个基于 **PySide6 / Qt** 的 Windows 桌面宠物。透明无边框窗口、常驻桌面置顶，会跳、会走、会跟着鼠标跑，还能聊天、涨好感度。

形象不是写死的——图片拖进去就能换，软件里还内置了抠图工具和文案编辑器，不用改一行代码。

<img src="assets/character.png" width="240" alt="凌丸形象">

## 功能

**桌面表现**
- 透明背景无边框窗口，可拖动、可置顶、滚轮缩放
- 点击互动：跳跃 / 压扁 / 摇摆；摸头、喂食有专属动画与台灯效果
- 自动走路、睡觉、鼠标跟随；气泡台词随场景变化（中文字体渲染，支持系统缩放）
- 位置、大小、置顶状态、好感度自动保存，重启延续

**好感度系统**
- 互动涨分：摸头 +2、喂食 +3、点击 +1、聊天每条 +2、走路/跟随陪伴每满 1 分钟 +1
- 冷落提醒：30 分钟无互动弹「想你了」提醒窗，撒娇处理 +2；放着不管（或点“等会儿再说”）90 秒后掉 5 点
- 桌宠脚下常驻爱心进度条，颜色随心情变化；菜单显示数值与等级（快生气了 → 死心塌地）

**三个内置工具窗口（右键菜单直达）**
- **更换形象**：选图 → 自动去背 → 预览 → 一键应用（自动生成 12 帧跑动动画与图标，旧形象自动备份）
- **图片透明化**：容差滑杆自动去背景 + 橡皮擦手动修边（右键恢复擦除、Ctrl+Z 撤销），可存透明 PNG 或直接应用
- **编辑文案**：气泡台词（15 个场景）与聊天回复规则可视化编辑，保存即时生效、重启保留

## 环境

Windows 10 / 11 64 位，Python 3.10–3.13（64 位）。首次安装依赖需联网，之后运行与聊天完全离线。

## 快速开始

```powershell
git clone <本仓库地址>
cd <仓库目录>

powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

Python 不在环境变量中时指定解释器；依赖下载慢可换清华镜像：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -PythonExe 'C:\Python312\python.exe'
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -IndexUrl https://pypi.tuna.tsinghua.edu.cn/simple
```

打包成免安装单文件 EXE（产物在 `delivery/`）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

> 打包走官方 PyPI 源时 PyInstaller 才装得上（清华镜像缺包）。

## 换形象

三种方式，都不需要改代码：

1. 把图片**拖到**项目根目录的 `一键换形象.bat` 图标上
2. 双击 `一键换形象.bat`，在弹窗里选图
3. 软件里右键 → **更换形象**（推荐，有预览）

命令行等价用法（背景去不干净时调大容差，默认 30）：

```powershell
.\.venv\Scripts\python.exe tools\swap_character.py 图片路径 --tol 60
```

透明背景 PNG 会直接使用；普通照片自动去除与边缘相连的纯色/渐变背景。复杂背景照片（如实拍室内照）建议先用 AI 抠图工具处理成透明 PNG 再导入。

## 打包第二个形象的独立软件

程序支持从内嵌的 `assets/app.json` 读取应用名，因此可以做出「同代码、不同形象」的多个桌宠，各自独立运行、独立保存好感度：

```text
build_variant/
├─ app.json          # {"name": "凌丸兔耳版"}
└─ assets/           # 该版本的 character.png / run_*.png / pet.ico
```

打包时把这些素材按 `assets` 目录塞进 EXE 即可：

```powershell
python -m PyInstaller --onefile --windowed --name "凌丸兔耳版" `
  --add-data "build_variant/assets/character.png;assets" `
  --add-data "build_variant/assets/run_*.png;assets" `
  --add-data "build_variant/assets/pet.ico;assets" `
  --add-data "build_variant/app.json;assets" `
  pet.py
```

注意 `--add-data` 只指定目标目录、不重命名文件，所以配置文件名必须本身就是 `app.json`，否则应用名覆盖失效，会和主程序撞单实例锁而静默退出。

## 项目结构

```text
pet.py                    主程序：窗口、绘制、动画、交互、菜单、气泡、好感度、设置保存
pet_gui.py                三个工具窗口（更换形象 / 图片透明化 / 编辑文案）
pet_assets.py             素材生成核心：抠图、裁剪缩放、跑动帧、图标（纯 Pillow）
tools/swap_character.py   命令行一键换形象
tools/acceptance.py       交互与窗口验收（--self-test 调用）
tools/verify_release.py   EXE 启动、重复启动、退出与打包资源检查
tools/prepare_assets.py   最初版本的轮廓抠图（针对首张照片手工描边，已不推荐）
assets/character.png      主形象（透明 PNG）
assets/run_00..11.png     12 帧跑动摆姿
assets/pet.ico|icon.png   应用图标
setup.ps1 / run.ps1 / build.ps1   安装 / 运行 / 打包
一键换形象.bat             双击或拖图换形象
```

## 自定义

| 想改什么 | 改哪里 |
| --- | --- |
| 气泡台词、聊天回复 | 右键 → 编辑文案（存 `custom_texts.json`），或改 `pet.py` 的 `DIALOGUES` / `CHAT_RULES` |
| 好感度规则（时间、分值） | `pet.py` 顶部 `NEGLECT_MINUTES` / `DECAY_DELAY_SECONDS` / `DECAY_AMOUNT` 与 `add_affection()` 调用处 |
| 默认尺寸 | `Pet` 初始化的 `pet_height`，或右键菜单「调整大小」 |
| 气泡配色、聊天样式 | `STYLE` 与 `Bubble.paintEvent()` |
| 应用名 | `pet.py` 的 `APP_NAME`（会被 `assets/app.json` 覆盖） |

运行数据保存在 `%LOCALAPPDATA%\PhotoPet\<应用名>\`：`settings.json`（位置/大小/置顶/好感度）、`custom_texts.json`（自定义文案）、`error.log`（异常日志）。

> 启动没反应时可先删掉该目录下的 `instance.lock`（上次进程被强杀会留下残留锁）。

## 验证

```powershell
.\.venv\Scripts\python.exe pet.py --self-test .\validation\source
```

验收会短暂显示并移动测试桌宠，结束后自动关闭，结果与真实窗口截图写入 `validation/`。

## 说明

- 桌宠为半身形象：跑动通过转向、弹跳与下半身摆动表现；全身站姿图效果更好
- 聊天是本地规则匹配，不联网、不调用任何 API
- `tools/prepare_assets.py` 的轮廓对应最初那张照片，换图请用 `swap_character.py`

## License

MIT
