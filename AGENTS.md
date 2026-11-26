# AGENTS.md

## 项目

`ebo-se-http-bridge`：Enabot EBO SE 机器人的 x86 非模拟器局域网 HTTP 桥接、实时抓拍与控制工具。

- 主要技术栈：C（32 位 ARM Android bionic 底层桥接程序）、Python / FastAPI / uvicorn（桥接服务端与命令行客户端）、PowerShell / Bash（启停与部署脚本）、`mediamtx` + `ffmpeg`（HEVC/RTSP/WebRTC/抓拍）。
- 正式代码入口：
  - 桥接核心与服务端：[x86-bridge/ebo_bridge_439.c](x86-bridge/ebo_bridge_439.c)、[x86-bridge/ebo_server_x86.py](x86-bridge/ebo_server_x86.py)、[x86-bridge/start_wsl_bridge.sh](x86-bridge/start_wsl_bridge.sh)
  - 控制与启停脚本：[scripts/ebo_cli.py](scripts/ebo_cli.py)、[scripts/start_bridge.ps1](scripts/start_bridge.ps1)、[scripts/stop_bridge.ps1](scripts/stop_bridge.ps1)

## 环境与命令

已验证运行环境：Windows x86_64 + WSL2（`Ubuntu-22.04`，已安装 `qemu-user`、`ffmpeg`、`gcc-arm-linux-gnueabi`、`fastapi`、`uvicorn`、`paho-mqtt` 及 `/opt/ebo/mediamtx` v1.19.0）。

- 启动桥接服务：`powershell -ExecutionPolicy Bypass -File ./scripts/start_bridge.ps1`
- 停止桥接服务：`powershell -ExecutionPolicy Bypass -File ./scripts/stop_bridge.ps1`
- 查询状态与抓拍：`python ./scripts/ebo_cli.py status`、`python ./scripts/ebo_cli.py snapshot <输出路径.jpg>`
- 控制与会话切换：`python ./scripts/ebo_cli.py move --ly <前后> --rx <转向> --duration <秒>`、`action <动作>`、`release` / `reconnect`
- 正式自动化测试套件尚未建立；实机验证通过上述接口与抓拍核对。

## 目录职责

- `x86-bridge/`：本项目正式桥接源码、预编译 32 位 ARM 桥接程序、Web 面板及 WSL2 运行脚本。
- `scripts/`：启停脚本与命令行控制客户端（均按相对路径自动定位仓库根目录）。
- `apk/`：官方 ROLA 安卓安装包本地归档目录（因单文件约 396 MB 超出 GitHub 100 MB 限制，`apk/*.apk` 已忽略并托管于 GitHub Release，目录内保留 [apk/README.md](apk/README.md) 记录版本与校验值）。
- `doc/dev/`：项目级稳定开发约定、设计原因、取舍及排障经验；整体设计入口见 [doc/dev/design.md](doc/dev/design.md)。
- `doc/user/`：项目级用户使用与操作说明；局域网 API 手册见 [doc/user/x86-lan-api.md](doc/user/x86-lan-api.md)。
- `config/`：配置模板（`*.example*`）与本机私有配置（其余文件已在 `.gitignore` 中忽略，严禁提交）。
- `local/`：本机专有二进制依赖（`local/vendor/`）、历史抓包、DEX 解包及测试抓拍（已在 `.gitignore` 中忽略）。
- `repo/reference/`：外部参考项目（如 `lilium360/ebo-se-lan-bridge`），不作为本项目正式代码依赖。
- `repo/worktree/`：临时 Git worktree，以主仓库根为基准，不嵌套创建。
- `task/<task-name>/`：任务计划、调查、原型实验及验证证据。默认直接放在任务目录；实验文件较多时可建立 `lab/`。
- `test/`：正式测试，按需建立。

正式代码和测试不得依赖 `task/` 或 `repo/` 中的临时内容。实验形成的正式实现与测试应整合到项目源码和测试目录，有长期价值的结论写入所属文档。

## 实现与验证

- 先阅读相关源码、配置与 [doc/dev/design.md](doc/dev/design.md)，沿用现有实现方式。不为假设中的未来需求增加抽象、配置项或兼容路径。
- 原型实验先明确问题和可观察的成功条件，记录实际结果及适用条件。实验通过不代表整合后的功能已验证。
- 涉及机器人移动或回充的实机测试，应先抓拍确认周围环境安全，测试后恢复合理状态（如回到充电座），并在文档中区分已实机验证与未验证项。

<!-- development-doc:start -->
## 开发文档

公共开发资料放根 `doc/dev/`，项目级用户文档放 `doc/user/`，模块资料放 `<module>/doc/`。局部设计按主要维护归属靠近模块，不因有多个调用方就上移到项目级。专题文件用具体主题名；`design.md` 仅用于整体设计及导航，有实际需要时才创建，入口位置为 `doc/dev/design.md` 或模块 `doc/design.md`。

路径以所属项目根为基准；嵌套独立项目以自身目录为根，内部子模块仍用 `<module>/doc/`。源码直接位于项目根时，项目设计仍放 `doc/dev/design.md`。

严格执行上述文档结构，不设置其他目录布局或旧路径兼容入口。

已有文档可随开发、需求纠正和排查结论更新；Agent 也可有节制地按需新建或拆分文档，无需用户点名或再次确认。优先复用已有资料，不按类型清单生成整套文件。初始化只配置 Agent 指令与已有资料导航，不自动补文档或空目录。

按任务读取已有入口与相关资料；入口不存在时直接搜索，不添加悬空链接。设计重点记录原因、取舍和踩坑经验，实现细节查代码与测试。理由未知时不编造，预期与实现不符时指出差异。

只更新受影响的内容和引用；无变化时不改文档。新文件须有实际内容并服务当前任务，遵守用户明确限定的操作范围。

当前已有文档导航：
- [项目总览](README.md)
- [整体设计与排障记录](doc/dev/design.md)
- [x86 局域网桥接与 API 使用手册](doc/user/x86-lan-api.md)
<!-- development-doc:end -->

## 本地配置与保密规则

ROLA 账号登录凭据保存在本机私有文件 `config/config.json` 中（`.gitignore` 已忽略非模板的 `config/*`，严禁提交到版本库）。

### `config/config.json` 文件结构

UTF-8 编码的 JSON 对象，包含两个字符串字段：

```json
{
  "acc": "<ROLA 登录账号>",
  "pass": "<ROLA 登录密码>"
}
```

### 使用与保密要求

1. **按需由脚本直接读取**：需要登录 ROLA（例如通过 ADB 在模拟器或手机端自动输入账号密码）时，在本地脚本内部直接读取 `config/config.json`，解析 `acc` 和 `pass` 后注入目标输入框。
2. **禁止泄露明文密码与密钥**：
   - 不要使用文件读取工具查看 `config/config.json`、`config/captured_creds.json`、`config/bridge.env`、`config/bridge_access.json` 原文并带入对话上下文。
   - 不要在终端标准输出、日志、报错信息、聊天记录或任何文档中打印、回显或复制密码、Token、AuthKey、License 等秘密值。
   - 仅需校验配置完整性时，用脚本解析并只输出字段名、非空状态或长度。
3. **ADB 自动填入注意事项**：通过 `adb shell input text` 填入密码时，应在脚本内以参数列表传递并对 shell 特殊字符正确转义，避免截断、展开或将明文拼接到可见命令日志。
4. **更新凭据方式**：如需修改密码，通过受控密钥输入弹窗或本地受控脚本覆盖写入 `config/config.json`，不要在聊天历史中粘贴明文密码。
5. **其他私有材料位置**：提取的原始机器人凭据在 `config/captured_creds.json`，桥接运行环境变量在 `config/bridge.env`，网页与 RTSP 访问凭据在 `config/bridge_access.json`，专有二进制依赖（4 个 TUTK 动态库、8 个 Android bionic 运行库及 `ioctl9930.bin`）在 `local/vendor/`。

## Git 与本地产物

`/repo/`、`/task/`、`/local/`、`/apk/*.apk` 以及非模板的 `/config/*` 均仅保留在本地，不进入主项目提交。修改范围内的文件时保留无关改动。初始化和实验本身不意味着授权暂存、提交、创建远端仓库或推送。
