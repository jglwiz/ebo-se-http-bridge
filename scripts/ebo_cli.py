"""
Windows/cross-platform CLI & Python client for the local EBO SE HTTP Bridge API.
Reads Basic Auth credentials from config/bridge_access.json (relative to repo root)
without printing secrets.
"""
import argparse, base64, json, os, sys, urllib.request, urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = os.environ.get("EBO_BRIDGE_URL", "http://127.0.0.1:8000")
DEFAULT_ACCESS_JSON = Path(os.environ.get("EBO_ACCESS_JSON", str(REPO_ROOT / "config" / "bridge_access.json")))


def _auth_header(access_path: Path):
    try:
        acc = json.loads(access_path.read_text(encoding="utf-8"))
        u, p = acc.get("web_user", ""), acc.get("web_pass", "")
        if u:
            tok = base64.b64encode(f"{u}:{p}".encode("utf-8")).decode("ascii")
            return {"Authorization": "Basic " + tok}
    except FileNotFoundError:
        pass
    return {}


def request(path, method="GET", body=None, base_url=DEFAULT_URL, access_path=DEFAULT_ACCESS_JSON, timeout=15):
    headers = _auth_header(Path(access_path))
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def main():
    ap = argparse.ArgumentParser(description="Control EBO SE via local x86 HTTP bridge API")
    ap.add_argument("--url", default=DEFAULT_URL, help="Bridge base URL (default: http://127.0.0.1:8000)")
    ap.add_argument("--access", default=str(DEFAULT_ACCESS_JSON), help="Path to bridge_access.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show robot connection, awake state, battery, and frame stats")

    sp_snap = sub.add_parser("snapshot", help="Save a live JPEG snapshot from the robot camera")
    sp_snap.add_argument("output", help="Output .jpg path")

    sp_mv = sub.add_parser("move", help="Move robot for a short duration")
    sp_mv.add_argument("--ly", type=float, default=0.0, help="Forward(+)/Backward(-) speed [-1.0..1.0]")
    sp_mv.add_argument("--rx", type=float, default=0.0, help="Right(+)/Left(-) turn speed [-1.0..1.0]")
    sp_mv.add_argument("--duration", type=float, default=0.4, help="Duration in seconds (0.05..5.0)")

    sub.add_parser("stop", help="Immediately stop robot motors")

    sp_act = sub.add_parser("action", help="Run a robot action or toggle")
    sp_act.add_argument("name", choices=[
        "wake", "sleep", "dock", "undock",
        "eyes_on", "eyes_off", "night_on", "night_off",
        "avoid_on", "avoid_off", "fall_on", "fall_off",
        "patrol_on", "patrol_off",
    ])

    sub.add_parser("release", help="Release robot P2P session so the mobile ROLA app can connect")
    sub.add_parser("reconnect", help="Reconnect bridge to the robot")

    args = ap.parse_args()
    access_path = Path(args.access)
    try:
        if args.cmd == "status":
            _, _, raw = request("/info", base_url=args.url, access_path=access_path)
            print(json.dumps(json.loads(raw.decode("utf-8")), indent=2, ensure_ascii=False))
        elif args.cmd == "snapshot":
            _, _, raw = request("/snapshot.jpg", base_url=args.url, access_path=access_path)
            Path(args.output).write_bytes(raw)
            print(f"Saved snapshot: {args.output} ({len(raw)} bytes)")
        elif args.cmd == "move":
            _, _, raw = request("/move", method="POST",
                                body={"ly": args.ly, "rx": args.rx, "duration": args.duration},
                                base_url=args.url, access_path=access_path)
            print(raw.decode("utf-8"))
        elif args.cmd == "stop":
            _, _, raw = request("/stop", method="POST", base_url=args.url, access_path=access_path)
            print(raw.decode("utf-8"))
        elif args.cmd == "action":
            _, _, raw = request(f"/action/{args.name}", method="POST",
                                base_url=args.url, access_path=access_path)
            print(raw.decode("utf-8"))
        elif args.cmd == "release":
            _, _, raw = request("/connection/stop", method="POST",
                                base_url=args.url, access_path=access_path)
            print(raw.decode("utf-8"))
        elif args.cmd == "reconnect":
            _, _, raw = request("/connection/start", method="POST",
                                base_url=args.url, access_path=access_path)
            print(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
