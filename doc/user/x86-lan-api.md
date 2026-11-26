# EBO SE x86 非模拟器局域网桥接与 API 使用手册

验证日期：2026-11-26。适用设备：Enabot EBO SE，运行主机：Windows x86_64（WSL2 `Ubuntu-22.04`）或 x86_64 Linux。技术选型、协议适配细节与踩坑记录见 [整体设计与排障记录](../dev/design.md)。

## 运行前提与本地文件

启动前需确保以下本地私有材料已就位（均已被 `.gitignore` 忽略，不提交版本库）：

- `config/config.json`：可选，仅自动登录 ROLA 提取凭据时使用，日常运行无需读取。
- `config/captured_creds.json`：可选，从 ROLA 动态捕获的原始机器人连接凭据备份。
- `config/bridge.env`：五项机器人连接凭据与桥接服务环境变量（模板见 [config/bridge.env.example](../../config/bridge.env.example)）。
- `config/bridge_access.json`：网页控制台与 RTSP 流访问凭据（模板见 [config/bridge_access.example.json](../../config/bridge_access.example.json)）。
- `local/vendor/lib/`：4 个 32 位 ARM TUTK 4.3.9.1 动态库（`libTUTKGlobalAPIs.so`、`libIOTCAPIs.so`、`libRDTAPIs.so`、`libAVAPIs.so`）。
- `local/vendor/bionic/`：8 个 32 位 ARM Android bionic 运行库及链接器（`linker`、`libc.so`、`libm.so`、`libdl.so`、`libc++.so`、`liblog.so`、`libstdc++.so`、`libnetd_client.so`）。
- `local/vendor/ioctl9930.bin`：1016 字节机器人开流控制载荷。
- `apk/rola-2.2.1-com.enabot.ebo.intl.apk`：可选，官方 ROLA 2.2.1 原始安装包归档（日常运行不依赖；校验信息见 [apk/README.md](../../apk/README.md)）。

WSL2（默认 `Ubuntu-22.04`，可通过 `-Distro` 参数切换）需安装以下依赖：

```bash
sudo apt-get update && sudo apt-get install -y --no-install-recommends qemu-user ffmpeg python3-pip
sudo pip3 install fastapi "uvicorn[standard]" paho-mqtt
sudo mkdir -p /opt/ebo
curl -fsSL "https://github.com/bluenviron/mediamtx/releases/download/v1.19.0/mediamtx_v1.19.0_linux_amd64.tar.gz" | sudo tar -xz -C /opt/ebo mediamtx
sudo chmod +x /opt/ebo/mediamtx
```

## 启动与停止

在仓库根目录下的 Windows PowerShell 中执行：

```powershell
# 启动后台桥接服务并检查状态（默认 WSL 发行版为 Ubuntu-22.04）
powershell -ExecutionPolicy Bypass -File ./scripts/start_bridge.ps1

# 如使用其他 WSL 发行版名称，可显式指定
powershell -ExecutionPolicy Bypass -File ./scripts/start_bridge.ps1 -Distro Ubuntu

# 停止桥接服务并释放机器人会话
powershell -ExecutionPolicy Bypass -File ./scripts/stop_bridge.ps1
```

## 接口与常用操作

服务启动后在本机暴露以下入口（需使用 `config/bridge_access.json` 中的 Basic 认证账号密码，`/sleep.svg` 除外）：

- **网页遥控面板**：`http://127.0.0.1:8000/`（实时画面、虚拟摇杆、方向键、键盘方向控制、回充/唤醒/休眠/功能开关与“释放给官方 App”按钮）
- **交互式 API 文档**：`http://127.0.0.1:8000/docs`
- **状态查询**：`GET /info`（在线状态、唤醒状态、帧数、电量、充电状态、RTSP 地址）
- **实时抓拍**：`GET /snapshot.jpg`（直接从最新 HEVC 关键帧实时解码 848×480 JPEG）
- **移动与急停**：`POST /move`、`POST /drive`、`POST /stop`
- **动作与开关**：`POST /action/{name}`（支持 `wake`、`sleep`、`dock`、`undock`、`eyes_on`/`eyes_off`、`night_on`/`night_off`、`avoid_on`/`avoid_off`、`fall_on`/`fall_off`、`patrol_on`/`patrol_off`）
- **会话释放与重连**：`POST /connection/stop`（释放单会话给手机 ROLA App）、`POST /connection/start`（重新接管）
- **RTSP 视频流**：`rtsp://<流账号>:<流密码>@127.0.0.1:8554/ebo`

命令行控制客户端（[scripts/ebo_cli.py](../../scripts/ebo_cli.py)，自动读取 `config/bridge_access.json`）：

```powershell
# 查询状态与实时抓拍
python ./scripts/ebo_cli.py status
python ./scripts/ebo_cli.py snapshot ./now.jpg

# 短时移动、急停与自动回充
python ./scripts/ebo_cli.py move --ly 0.4 --rx 0 --duration 0.3
python ./scripts/ebo_cli.py stop
python ./scripts/ebo_cli.py action dock

# 释放给手机 ROLA 应用 / 重新接管
python ./scripts/ebo_cli.py release
python ./scripts/ebo_cli.py reconnect
```

## 2026-11-26 实机验证范围与限制

- **已端到端验证**：桥接建连、实时 HEVC 848×480 视频与 RTSP 转发、网页遥控面板 HTTP 200、实时 JPEG 抓拍、电量与充电状态读取、转向移动控制及自动回充回座。
- **未逐项验证 / 注意事项**：
  - 机器人仅允许单个客户端连接；桥接在线时手机端 ROLA 无法同时查看，需先释放会话。
  - 眼灯、巡逻、休眠唤醒、避障与防跌落开关尚未逐一实机核验；白天室内测试夜视开关时画面保持彩色，未见黑白切换。

返回 [项目总览](../../README.md) · 查看 [整体设计与排障记录](../dev/design.md)。
