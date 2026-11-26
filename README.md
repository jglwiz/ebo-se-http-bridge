# ebo-se-http-bridge

直接运行在 **x86_64 电脑（Windows WSL2 或 Linux）** 上的 **Enabot EBO SE** 局域网 HTTP 桥接与控制工具，无需手机 App、无需常驻安卓模拟器，将机器人能力封装为标准本地 HTTP 控制 API、实时 JPEG 抓拍、网页遥控面板及 RTSP/WebRTC 视频流，便于脚本自动化与 AI Agent / ChatGPT 接入。

## 主要特性

- **免手机、免安卓模拟器运行**：在 WSL2 / Linux 中通过单进程 `qemu-arm` + 独立 PID 命名空间加载 32 位 ARM Android 桥接进程，资源占用极低。
- **兼容新版 TUTK SDK 4.3.9.1**：自建双版本兼容桥接程序 [ebo_bridge_439.c](x86-bridge/ebo_bridge_439.c)，自动适配 ROLA 2.2.1（SDK 4.3.9.1）与早期 SDK 4.3.6.x 的连接结构体。
- **HTTP 控制 API 与按需抓拍**：提供状态查询（在线/唤醒/电量/充电）、实时 JPEG 抓拍（`GET /snapshot.jpg`）、移动/连续遥杆/急停、回充/功能开关及单会话释放与重连接口，自带 OpenAPI 文档（`/docs`）。
- **网页遥控面板与实时流**：内置暗色网页遥控面板（摇杆、方向键、键盘控制、释放给手机 App 按钮）与 `mediamtx` RTSP/WebRTC/HLS 零重编码透传流。
- **跨平台命令行客户端**：[scripts/ebo_cli.py](scripts/ebo_cli.py) 开箱即用，配合 Windows 启停脚本一键管理。

## 快速开始

1. 准备本地运行依赖与设备凭据（不随代码库分发，需从用户自有设备提取）：
   - 复制 [config/bridge.env.example](config/bridge.env.example) 为 `config/bridge.env` 并填入 5 项机器人凭据与访问密码。
   - 复制 [config/bridge_access.example.json](config/bridge_access.example.json) 为 `config/bridge_access.json`。
   - 将提取的 4 个 32 位 ARM TUTK 动态库、8 个 32 位 ARM Android bionic 运行库和开流载荷放入 `local/vendor/`。
2. 启动桥接服务（Windows PowerShell）：
   - 启动：`powershell -ExecutionPolicy Bypass -File ./scripts/start_bridge.ps1`
   - 停止：`powershell -ExecutionPolicy Bypass -File ./scripts/stop_bridge.ps1`
3. 使用浏览器打开 `http://127.0.0.1:8000/`，或通过命令行控制：
   - 查询状态：`python ./scripts/ebo_cli.py status`
   - 实时抓拍：`python ./scripts/ebo_cli.py snapshot ./now.jpg`
   - 移动与回充：`python ./scripts/ebo_cli.py move --ly 0.4 --rx 0 --duration 0.3` / `action dock`

完整接口清单、前提依赖与实机验证记录见 [x86 局域网桥接与 API 使用手册](doc/user/x86-lan-api.md)。

## 文档与代码导航

- [x86 局域网桥接与 API 使用手册](doc/user/x86-lan-api.md)：环境准备、启停步骤、HTTP/RTSP 接口与命令行示例。
- [整体设计与排障记录](doc/dev/design.md)：架构图、平台选型取舍、TUTK 4.3.9.1 与 bionic 排障经验。
- [Agent 协作与保密约定](AGENTS.md)：目录职责、文档约定与本地凭据保密规范。
- [官方 ROLA 安装包说明](apk/README.md)：归档版本信息、SHA-256 校验与 Release 标签说明。
- [桥接核心源码](x86-bridge/ebo_bridge_439.c) · [增强服务端](x86-bridge/ebo_server_x86.py) · [命令行客户端](scripts/ebo_cli.py)

## 致谢与许可

- 本项目基于 [lilium360/ebo-se-lan-bridge](https://github.com/lilium360/ebo-se-lan-bridge)（MIT License）的桥接与网页架构扩展改造，针对 TUTK SDK 4.3.9.1、x86 WSL2 非模拟器运行及按需 JPEG 抓拍做了适配与增强。
- 本项目原创及改写代码采用 [MIT License](LICENSE) 开源。本项目与 Enabot 或 ThroughTek 无关；代码仓库不包含任何专有 SDK 动态库或用户凭据，请确保仅用于自有硬件的个人研究与互操作。
