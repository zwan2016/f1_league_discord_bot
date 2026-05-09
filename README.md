# F1 25 联赛 Discord Bot

F1 25 游戏实时遥测采集 + 赛后动画 GIF 自动生成。

---

## 给录制员：快速开始

> 录制员在比赛时运行本程序，比赛结束后把生成的文件上传到 Discord。

### 方式一：直接下载 exe（推荐，无需安装 Python）

1. 进入 [Releases](../../releases) 页面，下载最新的 `F1_Recorder.exe`
2. 双击运行，按屏幕提示配置 F1 25 游戏内的 UDP 设置
3. 开始比赛，录制员保持程序运行
4. 比赛结束后按 `Ctrl+C`，程序自动保存 `race.zip` 到 exe 同目录
5. 把 `race.zip` 上传到 Discord 指定频道

**关于 exe 的安全性**：本 exe 由 GitHub Actions 从本仓库源码自动构建，
构建过程完全公开，点击 [Actions](../../actions) 页面可查看每次构建的详细日志。

### 方式二：直接用 Python 运行

```bash
git clone <this-repo>
cd f1_leagure_discord_bot
pip install -r requirements.txt
python -m udp_capture.capture --db data/race.db
```

### F1 25 游戏内设置

`设置 → 遥测设置`：

| 选项 | 值 |
|------|-----|
| UDP 遥测 | 开 |
| UDP 格式 | 2025 |
| UDP IP 地址 | `127.0.0.1`（同一台电脑）或录制员的局域网 IP |
| UDP 端口 | `20777` |
| UDP 发送频率 | 60Hz |

---

## 给开发者：项目结构

```
├── recorder_app.py          # exe 入口点
├── build/
│   └── recorder.spec        # PyInstaller 构建配置
├── .github/workflows/
│   └── build-recorder.yml   # GitHub Actions 自动构建
├── udp_capture/             # 遥测采集（纯标准库，无外部依赖）
│   ├── capture.py           # UDP 监听主循环
│   ├── recorder.py          # SQLite 写入
│   └── packets/             # F1 25 packet 解析（ID 1/2/3/4/8）
├── bot/                     # Discord Bot
│   ├── main.py
│   ├── cogs/race.py         # 文件上传处理 → 生成 GIF → 发结果
│   └── utils/db.py          # 异步 SQLite 查询
└── visualizer/
    └── race_animation.py    # matplotlib 动画 GIF 生成
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

GitHub Actions 自动构建 exe 并创建 Release，附件可直接下载。
