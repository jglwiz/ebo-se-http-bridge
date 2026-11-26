"""
EBO-SE x86/WSL2 bridge supervisor & LAN API.

Extends upstream ebo_server.py with:
  - Optional qemu-arm + PID-namespace execution (EBO_USE_QEMU=1) so the 32-bit ARM
    Android TUTK bridge runs directly on x86_64 Linux/WSL2 with no Android emulator.
  - Live JPEG snapshot endpoint (GET /snapshot.jpg) decoded on demand from the latest
    in-memory HEVC keyframe GOP.
  - Connection mode & robot IP reporting parsed from bridge diagnostics.
"""
import os, re, time, struct, threading, subprocess, secrets, socket, base64, urllib.request, urllib.error, http.cookiejar
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
import uvicorn

EBO_DIR = os.environ.get("EBO_DIR", "/opt/ebo")
PORT = int(os.environ.get("EBO_PORT", "8000"))
BIND_HOST = os.environ.get("EBO_BIND", "0.0.0.0")
USE_QEMU = os.environ.get("EBO_USE_QEMU", "1") == "1"
USE_UNSHARE = os.environ.get("EBO_USE_UNSHARE", "1") == "1"
AUDIO_ON = os.environ.get("EBO_AUDIO", "0") == "1"
AUDIO_FMT = os.environ.get("EBO_AUDIO_FMT", "mulaw")
AUDIO_RATE = os.environ.get("EBO_AUDIO_RATE", "8000")
AUDIO_FILTER = os.environ.get("EBO_AUDIO_FILTER", "none")
RTSP_PATH = "ebo"
STREAM_USER = os.environ.get("EBO_STREAM_USER", "ebo")
STREAM_PASS = os.environ.get("EBO_STREAM_PASS", "")
WEB_USER = os.environ.get("EBO_WEB_USER")
WEB_PASS = os.environ.get("EBO_WEB_PASS")


def _has_param_set(data, codec):
    i, n = 0, len(data)
    while i + 4 < n:
        if data[i] == 0 and data[i+1] == 0 and (data[i+2] == 1 or (data[i+2] == 0 and i+3 < n and data[i+3] == 1)):
            j = i + (3 if data[i+2] == 1 else 4)
            if j < n:
                if codec == 80:
                    t = (data[j] >> 1) & 0x3F
                    if t == 32 or t == 33:
                        return True
                else:
                    if (data[j] & 0x1F) == 7:
                        return True
            i = j
        else:
            i += 1
    return False


def mavlink_crc(data, crc_extra):
    crc = 0xFFFF
    for b in data:
        t = b ^ (crc & 0xFF); t = (t ^ (t << 4)) & 0xFF
        crc = ((crc >> 8) ^ (t << 8) ^ (t << 3) ^ (t >> 4)) & 0xFFFF
    t = crc_extra ^ (crc & 0xFF); t = (t ^ (t << 4)) & 0xFF
    crc = ((crc >> 8) ^ (t << 8) ^ (t << 3) ^ (t >> 4)) & 0xFFFF
    return crc


def _frame(msgid, payload, crc_extra):
    hdr = bytes([len(payload), 0, 0, 0, msgid])
    return bytes([0xfe]) + hdr + payload + struct.pack('<H', mavlink_crc(hdr + payload, crc_extra))


def motor_frame(ly=0.0, rx=0.0, lx=0.0, ry=0.0, buttons=0):
    return _frame(202, struct.pack('<ffff', lx, -ly, rx, ry) + bytes([buttons & 0xFF]), 211)


def param_set_frame(group, key, value, ptype=11):
    pid = f"{group}-{key}".encode()[:32].ljust(32, b'\x00')
    return _frame(229, struct.pack('<f', value) + bytes([255, 3]) + pid + bytes([ptype]), 208)


def command_frame(command):
    return _frame(200, struct.pack('<H', command) + bytes([255, 1]), 196)


CMD_DOCK = 40154

DEVICE_INFO = {
    "name": os.environ.get("EBO_NAME", "EBO-SE"),
    "model": "EBO SE",
    "sn": os.environ.get("EBO_SN", ""),
    "fsn": os.environ.get("EBO_FSN", ""),
    "mcu_version": os.environ.get("EBO_MCU", ""),
    "camera_version": os.environ.get("EBO_CAMFW", ""),
    "uid": os.environ.get("EBO_UID", ""),
    "wifi_ssid": os.environ.get("EBO_SSID", ""),
    "ip": os.environ.get("EBO_ROBOT_IP", ""),
    "mac": os.environ.get("EBO_MAC", ""),
}

PARAM_TOGGLES = {
    "eyes_on": ("display", "enable", 1.0), "eyes_off": ("display", "enable", 0.0),
    "night_on": ("video", "night_vision", 1.0), "night_off": ("video", "night_vision", 0.0),
    "avoid_on": ("control", "auto_avoidance", 1.0), "avoid_off": ("control", "auto_avoidance", 0.0),
    "fall_on": ("control", "fallarrest", 1.0), "fall_off": ("control", "fallarrest", 0.0),
    "patrol_on": ("security_patrol", "enable", 1.0), "patrol_off": ("security_patrol", "enable", 0.0),
    "sleep": ("power", "sleep", 1.0), "wake": ("power", "sleep", 0.0),
}


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"


class Bridge:
    def __init__(self):
        self.started_at = time.time()
        self.frame_count = 0
        self.last_frame = 0.0
        self.audio_codec = None
        self.audio_flags = None
        self.audio_count = 0
        self.connected = False
        self.connection_mode = None
        self.robot_ip = DEVICE_INFO.get("ip") or None
        self.codec_name = None
        self.codec_id = None
        self.battery = -1
        self.charge = -1
        self.on_status = None
        self._gop_lock = threading.Lock()
        self._gop_buf = bytearray()
        self._gop_codec = 80
        self._ctrl_r, self._ctrl_w = os.pipe()
        self._a_r, self._a_w = os.pipe()
        os.set_inheritable(self._a_r, True)
        os.set_blocking(self._a_w, False)
        self._a_buf = bytearray()
        self._a_lock = threading.Lock()
        self._running = True
        self._ff_primed = False
        self.paused = False
        self._start_mediamtx()
        time.sleep(0.6)
        self._start_ffmpeg()
        self._start_bridge()
        threading.Thread(target=self._read_frames, daemon=True).start()
        threading.Thread(target=self._log_stderr, daemon=True).start()
        if AUDIO_ON:
            threading.Thread(target=self._audio_feeder, daemon=True).start()

    def _audio_feeder(self):
        rate = int(AUDIO_RATE); chunk = max(80, rate // 50); interval = chunk / rate
        silence = (b"\xff" if AUDIO_FMT == "mulaw" else b"\xd5") * chunk
        next_t = time.monotonic()
        while self._running:
            next_t += interval
            with self._a_lock:
                if len(self._a_buf) >= chunk:
                    out = bytes(self._a_buf[:chunk]); del self._a_buf[:chunk]
                elif self._a_buf:
                    out = bytes(self._a_buf) + silence[len(self._a_buf):]; self._a_buf.clear()
                else:
                    out = silence
            try: os.write(self._a_w, out)
            except Exception: pass
            d = next_t - time.monotonic()
            if d > 0: time.sleep(d)
            else: next_t = time.monotonic()

    def is_awake(self):
        return (time.time() - self.last_frame) < 6.0

    def _start_mediamtx(self):
        self.mtx = subprocess.Popen(
            [os.path.join(EBO_DIR, "mediamtx"), os.path.join(EBO_DIR, "mediamtx.yml")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print("[supervisor] mediamtx pid", self.mtx.pid, flush=True)

    def _start_ffmpeg(self):
        auth = f"{STREAM_USER}:{STREAM_PASS}@" if STREAM_PASS else ""
        url = f"rtsp://{auth}127.0.0.1:8554/{RTSP_PATH}"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning",
               "-fflags", "nobuffer", "-flags", "low_delay",
               "-analyzeduration", "500000", "-probesize", "1000000",
               "-thread_queue_size", "256", "-f", "hevc", "-i", "pipe:0"]
        pass_fds = ()
        if AUDIO_ON:
            if AUDIO_FILTER and AUDIO_FILTER.lower() != "none":
                aout = ["-af", AUDIO_FILTER, "-c:a", "libopus", "-application", "voip",
                        "-b:a", "24k", "-ar", "48000", "-ac", "1"]
            else:
                aout = ["-c:a", "copy"]
            cmd += ["-use_wallclock_as_timestamps", "1", "-thread_queue_size", "256",
                    "-f", AUDIO_FMT, "-ar", AUDIO_RATE, "-ac", "1", "-i", f"pipe:{self._a_r}",
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy"] + aout + ["-max_interleave_delta", "0"]
            pass_fds = (self._a_r,)
        else:
            cmd += ["-c:v", "copy", "-an"]
        cmd += ["-f", "rtsp", "-rtsp_transport", "tcp", url]
        self.ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, pass_fds=pass_fds)
        print("[supervisor] ffmpeg pid", self.ff.pid, flush=True)

    def _restart_ffmpeg(self):
        try: self.ff.stdin.close()
        except Exception: pass
        try: self.ff.kill()
        except Exception: pass
        self._ff_primed = False
        self._start_ffmpeg()
        print("[supervisor] ffmpeg restarted", flush=True)

    def _start_bridge(self):
        linker = os.path.join(EBO_DIR, "bionic", "linker")
        bridge_bin = os.path.abspath(os.path.join(EBO_DIR, "ebo_bridge"))
        env = dict(os.environ)
        env["EBO_LIB_DIR"] = os.path.join(EBO_DIR, "lib")
        env["EBO_IOCTL9930"] = os.path.join(EBO_DIR, "ioctl9930.bin")
        env["LD_LIBRARY_PATH"] = os.path.join(EBO_DIR, "bionic") + ":" + os.path.join(EBO_DIR, "lib")
        argv = []
        if USE_UNSHARE:
            argv += ["unshare", "--pid", "--fork", "--mount-proc"]
        if USE_QEMU:
            argv += ["qemu-arm"]
        argv += [linker, bridge_bin]
        self.proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            pass_fds=(self._ctrl_r,),
            preexec_fn=lambda: os.dup2(self._ctrl_r, 3),
        )
        print("[supervisor] bridge pid", self.proc.pid, "cmd:", " ".join(argv), flush=True)

    def pause_bridge(self):
        if self.paused:
            return
        self.paused = True
        self.connected = False
        print("[supervisor] pausing bridge (releasing robot for the app)", flush=True)
        try: self.proc.terminate()
        except Exception: pass
        try: self.proc.wait(timeout=3)
        except Exception:
            try: self.proc.kill()
            except Exception: pass

    def resume_bridge(self):
        if not self.paused:
            return
        self.paused = False
        self._ff_primed = False
        print("[supervisor] resuming bridge", flush=True)
        self._start_bridge()
        threading.Thread(target=self._read_frames, daemon=True).start()
        threading.Thread(target=self._log_stderr, daemon=True).start()

    def _log_stderr(self):
        for line in iter(self.proc.stderr.readline, b""):
            s = line.decode(errors="replace").rstrip()
            print("[bridge]", s, flush=True)
            if "connected SID=" in s:
                self.connected = True
            m = re.search(r"session mode=(\S+)(?: ip=(\S+))?", s)
            if m:
                self.connection_mode = m.group(1)
                if m.group(2):
                    self.robot_ip = m.group(2)

    def _read_frames(self):
        f = self.proc.stdout
        while self._running:
            hdr = f.read(5)
            if len(hdr) < 5:
                break
            n = struct.unpack("<I", hdr[:4])[0]; codec = hdr[4]
            data = f.read(n)
            if len(data) < n:
                break
            if codec == 0xFF:
                self._parse_status(data)
                continue
            if codec == 0xA0:
                if len(data) >= 2:
                    self.audio_codec, self.audio_flags = data[0], data[1]
                    self.audio_count += 1
                    if AUDIO_ON and len(data) > 2:
                        with self._a_lock:
                            self._a_buf += data[2:]
                            if len(self._a_buf) > 1600:
                                del self._a_buf[:len(self._a_buf) - 1600]
                continue
            self.frame_count += 1
            self.last_frame = time.time()
            self.codec_id = codec
            self.codec_name = "hevc" if codec == 80 else ("h264" if codec == 78 else f"codec{codec}")
            is_key = _has_param_set(data, codec)
            with self._gop_lock:
                if is_key:
                    self._gop_buf = bytearray(data)
                    self._gop_codec = codec
                elif self._gop_buf and len(self._gop_buf) < 4 * 1024 * 1024:
                    self._gop_buf += data
            if not self._ff_primed:
                if not is_key:
                    continue
                self._ff_primed = True
            try:
                self.ff.stdin.write(data); self.ff.stdin.flush()
            except Exception:
                self._restart_ffmpeg()

    def get_snapshot_jpeg(self) -> bytes:
        with self._gop_lock:
            buf = bytes(self._gop_buf)
            codec = self._gop_codec
        if not buf:
            raise RuntimeError("No video keyframe received yet (robot may be sleeping or connecting)")
        fmt = "hevc" if codec == 80 else "h264"
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", fmt, "-i", "pipe:0",
             "-sseof", "-0.1", "-frames:v", "1", "-q:v", "3", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
            input=buf, capture_output=True, timeout=8
        )
        if p.returncode != 0 or not p.stdout:
            # Fallback without -sseof (single keyframe)
            p = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", fmt, "-i", "pipe:0",
                 "-frames:v", "1", "-q:v", "3", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"],
                input=buf, capture_output=True, timeout=8
            )
        if p.returncode != 0 or not p.stdout:
            raise RuntimeError("Snapshot decode failed: " + p.stderr.decode(errors="replace"))
        return p.stdout

    def _parse_status(self, u):
        i = 0
        while i + 8 <= len(u):
            if u[i] == 0xfe:
                plen = u[i+1]; msgid = u[i+5] if i+5 < len(u) else -1
                if msgid == 207 and i + 24 <= len(u):
                    bp = u[i+22]; cs = u[i+23]
                    if bp != self.battery or cs != self.charge:
                        self.battery = bp; self.charge = cs
                        if self.on_status:
                            try: self.on_status(bp, cs)
                            except Exception: pass
                i += 8 + plen + 2 if plen else i + 1
            else:
                i += 1

    def send_rdt(self, mavlink: bytes):
        os.write(self._ctrl_w, struct.pack("<I", 1 + len(mavlink)) + b"\x00" + mavlink)

    def send_ioctl(self, io_type: int, data: bytes = b""):
        payload = b"\x01" + struct.pack("<H", io_type) + data
        os.write(self._ctrl_w, struct.pack("<I", len(payload)) + payload)


def do_action(name: str) -> bool:
    if name == "dock":
        for _ in range(5): bridge.send_rdt(command_frame(CMD_DOCK)); time.sleep(0.15)
    elif name == "undock":
        for _ in range(6): bridge.send_rdt(motor_frame(ly=0.5)); time.sleep(0.05)
        bridge.send_rdt(motor_frame())
    elif name in PARAM_TOGGLES:
        g, k, v = PARAM_TOGGLES[name]; bridge.send_rdt(param_set_frame(g, k, v))
    else:
        return False
    return True


def do_move(ly: float, rx: float, duration: float = 0.4):
    duration = max(0.05, min(float(duration), 5.0))
    ly = max(-1.0, min(1.0, float(ly)))
    rx = max(-1.0, min(1.0, float(rx)))
    n = max(1, int(duration * 20))
    for _ in range(n):
        bridge.send_rdt(motor_frame(ly=ly, rx=rx)); time.sleep(0.05)
    bridge.send_rdt(motor_frame())


bridge = None
_basic = HTTPBasic(auto_error=False)


def require_auth(request: Request, cred: HTTPBasicCredentials = Depends(_basic)):
    if request.url.path == "/sleep.svg":
        return
    if not WEB_USER:
        return
    ok = cred and secrets.compare_digest(cred.username, WEB_USER) and secrets.compare_digest(cred.password, WEB_PASS or "")
    if not ok:
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})


app = FastAPI(title="EBO SE LAN Bridge API", dependencies=[Depends(require_auth)])


@app.get("/", response_class=HTMLResponse)
def index():
    p = Path(__file__).parent / "ebo.html"
    if not p.exists():
        return "<h1>EBO-SE</h1>"
    html = p.read_text(encoding="utf-8")
    return html.replace("EBO-531", DEVICE_INFO["name"])


@app.get("/sleep.svg")
def sleep_image():
    p = Path(__file__).parent / "sleep.svg"
    if not p.exists():
        raise HTTPException(status_code=404)
    return Response(content=p.read_text(encoding="utf-8"), media_type="image/svg+xml")


@app.get("/snapshot.jpg")
async def snapshot():
    if not bridge or not bridge.connected:
        raise HTTPException(status_code=503, detail="Bridge not connected")
    try:
        jpg = await run_in_threadpool(bridge.get_snapshot_jpeg)
        return Response(content=jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


_WHEP_UP = f"http://127.0.0.1:8889/{RTSP_PATH}/whep"


def _whep_proxy(offer: bytes) -> Response:
    headers = {"Content-Type": "application/sdp"}
    if STREAM_PASS:
        tok = base64.b64encode(f"{STREAM_USER}:{STREAM_PASS}".encode()).decode()
        headers["Authorization"] = "Basic " + tok
    req = urllib.request.Request(_WHEP_UP, data=offer, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return Response(content=r.read(), media_type=r.headers.get("Content-Type", "application/sdp"))
    except urllib.error.HTTPError as e:
        return Response(content=e.read(), status_code=e.code, media_type="application/sdp")


@app.post("/whep")
async def whep(request: Request):
    offer = await request.body()
    return await run_in_threadpool(_whep_proxy, offer)


def _hls_open(path: str, query: str):
    url = f"http://127.0.0.1:8888/{path}" + (("?" + query) if query else "")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req = urllib.request.Request(url)
    if STREAM_PASS:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{STREAM_USER}:{STREAM_PASS}".encode()).decode())
    return opener.open(req, timeout=20)


@app.get("/hls/{path:path}")
async def hls(path: str, request: Request):
    try:
        r = await run_in_threadpool(_hls_open, path, request.url.query)
    except urllib.error.HTTPError as e:
        return Response(content=e.read(), status_code=e.code,
                        media_type=e.headers.get("Content-Type", "application/json"))
    except Exception:
        return Response(content=b"", status_code=502)
    def gen():
        try:
            while True:
                chunk = r.read(65536)
                if not chunk: break
                yield chunk
        finally:
            r.close()
    return StreamingResponse(gen(), media_type=r.headers.get("Content-Type", "application/octet-stream"))


@app.get("/info")
def info():
    ip = lan_ip()
    return JSONResponse({
        "name": DEVICE_INFO["name"],
        "connected": bridge.connected if bridge else False,
        "connection_mode": bridge.connection_mode if bridge else None,
        "robot_ip": bridge.robot_ip if bridge else None,
        "paused": bridge.paused if bridge else False,
        "awake": bridge.is_awake() if bridge else False,
        "codec": bridge.codec_name if bridge else None,
        "frames_received": bridge.frame_count if bridge else 0,
        "audio": ({"codec": f"0x{bridge.audio_codec:02x}", "flags": f"0x{bridge.audio_flags:02x}",
                   "count": bridge.audio_count} if bridge and bridge.audio_codec is not None else None),
        "battery": bridge.battery if bridge else -1,
        "charge": bridge.charge if bridge else -1,
        "uptime_sec": round(time.time() - bridge.started_at, 1) if bridge else 0.0,
        "rtsp": f"rtsp://{ip}:8554/{RTSP_PATH}",
    })


class Move(BaseModel):
    ly: float = 0.0
    rx: float = 0.0
    duration: float = 0.4


@app.post("/move")
def move(m: Move):
    do_move(m.ly, m.rx, m.duration); return {"ok": True}


_last_drive = 0.0


@app.post("/drive")
def drive(m: Move):
    global _last_drive
    bridge.send_rdt(motor_frame(ly=m.ly, rx=m.rx))
    _last_drive = time.time()
    return {"ok": True}


def _drive_watchdog():
    global _last_drive
    while True:
        time.sleep(0.1)
        if _last_drive and (time.time() - _last_drive) > 0.35:
            _last_drive = 0.0
            try: bridge.send_rdt(motor_frame())
            except Exception: pass


@app.post("/stop")
def stop():
    global _last_drive
    _last_drive = 0.0
    for _ in range(3): bridge.send_rdt(motor_frame()); time.sleep(0.02)
    return {"ok": True}


@app.post("/action/{name}")
def action(name: str):
    return {"ok": True, "action": name} if do_action(name) else {"ok": False, "err": "unknown"}


@app.post("/connection/{state}")
def connection(state: str):
    if state == "stop":
        bridge.pause_bridge()
    elif state == "start":
        bridge.resume_bridge()
    else:
        return {"ok": False, "err": "unknown"}
    return {"ok": True, "paused": bridge.paused}


if __name__ == "__main__":
    bridge = Bridge()
    threading.Thread(target=_drive_watchdog, daemon=True).start()
    mqtt_host = os.environ.get("EBO_MQTT_HOST")
    if mqtt_host:
        try:
            from ebo_mqtt import EBOMqtt
            di = dict(DEVICE_INFO); di["ip_pi"] = lan_ip()
            EBOMqtt(bridge, do_action, do_move, di, mqtt_host,
                    int(os.environ.get("EBO_MQTT_PORT", "1883")),
                    os.environ.get("EBO_MQTT_USER") or None, os.environ.get("EBO_MQTT_PASS") or None)
            print(f"[supervisor] MQTT -> {mqtt_host}", flush=True)
        except Exception as e:
            print("[supervisor] MQTT error:", e, flush=True)
    uvicorn.run(app, host=BIND_HOST, port=PORT, log_level="warning")
