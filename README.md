# F1 25 联赛 Discord Bot

F1 25 游戏实时遥测采集 + 赛后动画 GIF 自动生成。

---

## 给录制员：快速开始

> 录制员在比赛时运行本程序，比赛结束后把生成的文件上传到 Discord。

### 方式一：直接下载 exe（推荐，无需安装任何软件）

1. 进入 [Releases](../../releases) 页面，下载最新的 `F1_Recorder.exe`
2. 双击运行，按屏幕提示在 F1 25 游戏内完成 UDP 配置
3. 开始比赛，保持程序在后台运行
4. 比赛结束后按 `Ctrl+C`，程序自动在同目录生成 `race.zip`
5. 将 `race.zip` 上传到 Discord 指定频道

**关于安全性**：本 exe 由 GitHub Actions 从本仓库源码自动构建，构建过程完全公开，点击 [Actions](../../actions) 页面可查看每次构建的详细日志，下载的文件与源码一一对应。

### 方式二：直接用 Python 运行

```bash
git clone https://github.com/zwan2016/f1_leagure_discord_bot.git
cd f1_leagure_discord_bot
pip install -r requirements.txt
python -m udp_capture.capture --db data/race.db
```

### F1 25 游戏内设置

进入 `设置 → 遥测设置`，按下表配置：

| 选项 | 值 |
|------|-----|
| UDP 遥测 | 开启 |
| UDP 格式 | 2025 |
| UDP IP 地址 | `127.0.0.1`（与游戏同一台电脑）或录制员的局域网 IP |
| UDP 端口 | `20777` |
| UDP 发送频率 | 60Hz（推荐） |

---

## 给开发者：项目结构

```
├── recorder_app.py              # Windows exe 入口，含游戏设置引导
├── requirements.txt
├── .env.example                 # Bot 环境变量模板
├── build/
│   └── recorder.spec            # PyInstaller 构建配置
├── .github/workflows/
│   └── build-recorder.yml       # GitHub Actions 自动构建与发布
├── udp_capture/                 # 遥测采集（纯标准库，无第三方依赖）
│   ├── capture.py               # UDP 监听主循环，Ctrl+C 保存 zip
│   ├── recorder.py              # SQLite 写入，含 Flashback 回溯处理
│   └── packets/                 # F1 25 UDP packet 解析
│       ├── header.py            # 通用包头（29 字节）
│       ├── session.py           # Packet ID 1：赛道、圈数、赛事类型
│       ├── lap_data.py          # Packet ID 2：实时位置、圈时、Pit 状态
│       ├── event.py             # Packet ID 3：最快圈、超车、处罚、Flashback
│       ├── participants.py      # Packet ID 4：车手名称、车队
│       └── final_classification.py  # Packet ID 8：最终成绩
├── bot/                         # Discord Bot
│   ├── main.py                  # Bot 入口
│   ├── cogs/race.py             # 接收文件上传 → 解析 → 发 embed + GIF
│   └── utils/db.py              # 异步 SQLite 查询工具
└── visualizer/
    └── race_animation.py        # matplotlib 动画 GIF 生成
```

### 本地构建 exe

```bash
pip install pyinstaller
pyinstaller build/recorder.spec
# 输出：dist/F1_Recorder.exe
```

### 运行 Bot

```bash
cp .env.example .env   # 填入 Discord Token 和频道 ID
python -m bot.main
```

---

## 发布新版本

```bash
git tag v1.0.0
git push --tags
```

GitHub Actions 自动在 Windows 环境构建 exe 并创建 Release，附件可直接下载。
