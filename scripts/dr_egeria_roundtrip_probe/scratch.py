#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the ODPi Egeria project.
"""The scratch Egeria the round-trip probe runs against: `up`, `down`, `status`.

    python scripts/dr_egeria_roundtrip_probe/scratch.py up [--digest sha256:...] [--out DIR]
    python scripts/dr_egeria_roundtrip_probe/scratch.py status
    python scripts/dr_egeria_roundtrip_probe/scratch.py down

`up` copies the base image's own server configuration out of the image, applies the option-A edits
(simple-metadata-store + view-server, no Kafka), REFUSES to start if any copied file still names
`host.docker.internal`, then runs the container on 127.0.0.1:19443 with the scratch label and waits
for both servers to start. `down` removes the container and the scratch configuration (results are
kept) and confirms nothing labelled is left and port 19443 is free.

Never a laz or shared platform: the container, port and label are fixed, and the probe's own guard
checks them again before any request.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_DIGEST = "sha256:757a5df0db06f526cd92565210eed55ab60adc8e7ab6536a402f33efafc7ea9a"
IMAGE_REPO = "odpi/egeria-platform"
CONTAINER = "egeria-scratch-roundtrip"
LABEL = "purpose=roundtrip-probe"
PORT = 19443
SERVERS = ("simple-metadata-store", "view-server")
LAZ_CONTAINER = "quickstart-egeria-main"   # only ever inspected (StartedAt), never touched
FORBIDDEN_HOST = "host.docker.internal"
POINTER = ".current_scratch"

KAFKA_ENDPOINT = "kafka-disabled.invalid:9092"   # never resolves: no event bus at all
EGERIA_ENDPOINT = "https://localhost:7443"       # the container itself


class Refused(SystemExit):
    pass


# ── The edits (pure functions, unit-tested on a copied fixture) ──

def edit_view_server_config(text: str) -> str:
    """Point every view service at simple-metadata-store and drop the Kafka audit-log destination."""
    config = json.loads(text)

    def repoint(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "omagserverName" and value == "active-metadata-store":
                    node[key] = "simple-metadata-store"
                else:
                    repoint(value)
        elif isinstance(node, list):
            for value in node:
                repoint(value)

    repoint(config)
    repo = config.get("repositoryServicesConfig") or {}
    if "auditLogConnections" in repo:
        repo["auditLogConnections"] = [c for c in repo["auditLogConnections"] if "kafka" not in json.dumps(c).lower()]
    return json.dumps(config, indent=2)


def edit_application_properties(text: str) -> str:
    """Start only the two scratch servers, fix the image's placeholder JSON typo, and point the Kafka
    and Egeria endpoint placeholders away from the host."""
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("startup.server.list="):
            line = "startup.server.list=" + ",".join(SERVERS)
        elif stripped.startswith('"kafkaEndpoint"'):
            line = f'    "kafkaEndpoint" : "{KAFKA_ENDPOINT}",\\'
        elif stripped.startswith('"egeriaEndpoint"'):
            line = f'    "egeriaEndpoint" : "{EGERIA_ENDPOINT}",\\'
        elif stripped.startswith('"secretsStoreProvider"') and line.rstrip().endswith('".\\'):
            # the base image's own typo: `".\` where the JSON needs `",\` -- no server starts without the fix
            line = line.rstrip()[:-3] + '",\\'
        out.append(line)
    return "\n".join(out)


def forbidden_references(folder: Path) -> list[str]:
    """Every copied file that still names the host (`host.docker.internal`): any one refuses the start."""
    hits = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        if FORBIDDEN_HOST.encode() in path.read_bytes():
            hits.append(str(path.relative_to(folder)))
    return hits


def apply_edits(folder: Path) -> None:
    vsc = folder / "data" / "servers" / "view-server" / "config" / "view-server.config"
    vsc.write_text(edit_view_server_config(vsc.read_text(encoding="utf-8")), encoding="utf-8")
    props = folder / "application.properties"
    props.write_text(edit_application_properties(props.read_text(encoding="utf-8")), encoding="utf-8")
    hits = forbidden_references(folder)
    if hits:
        raise Refused(f"REFUSED: the scratch configuration still names {FORBIDDEN_HOST} in {hits}; "
                      "the scratch platform must never reach the host")


# ── Docker ──

def docker(*args, check=True) -> str:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"docker {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def laz_started_at() -> str | None:
    """StartedAt of laz's Egeria container, if this host has one (read-only inspect)."""
    proc = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", LAZ_CONTAINER],
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def port_free(port: int = PORT) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def labelled() -> list[str]:
    return docker("ps", "-a", "--filter", f"label={LABEL}", "--format", "{{.Names}}").split()


def up(digest: str, out: Path, timeout: int = 300) -> Path:
    if labelled():
        raise SystemExit(f"a scratch container already exists ({labelled()}); run `down` first")
    if not port_free():
        raise SystemExit(f"port {PORT} is in use; refusing to start")
    image = f"{IMAGE_REPO}@{digest}"
    if not docker("images", "-q", image, check=False):
        print(f"pulling {image}")
        docker("pull", image)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = out / f"scratch-{stamp}"
    folder.mkdir(parents=True)
    cid = docker("create", image)
    try:
        docker("cp", "-q", f"{cid}:/deployments/data", str(folder / "data"))
        docker("cp", "-q", f"{cid}:/deployments/application.properties", str(folder / "application.properties"))
    finally:
        docker("rm", cid)
    apply_edits(folder)  # refuses before anything runs
    (out / POINTER).write_text(str(folder))
    docker("run", "-d", "--name", CONTAINER, "--label", LABEL,
           "--add-host", f"{FORBIDDEN_HOST}:127.0.0.1",   # second guard: the host name resolves to the container
           "-p", f"127.0.0.1:{PORT}:7443",
           "-v", f"{folder / 'data'}:/deployments/data",
           "-v", f"{folder / 'application.properties'}:/deployments/application.properties",
           "-e", "JAVA_OPTS_APPEND=-Xmx3g", image)
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = docker("inspect", "-f", "{{.State.Status}}", CONTAINER, check=False)
        if state != "running":
            raise SystemExit(f"{CONTAINER} is {state}; see `docker logs {CONTAINER}`")
        logs = subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True)
        text = logs.stdout + logs.stderr
        started = [s for s in SERVERS if any("SERVER-OPS-0004" in line and s in line for line in text.splitlines())]
        if len(started) == len(SERVERS):
            print(f"scratch up: {CONTAINER} on https://localhost:{PORT}, servers {', '.join(SERVERS)} started; "
                  f"config {folder}")
            return folder
        time.sleep(5)
    raise SystemExit(f"timed out waiting for {SERVERS} to start; see `docker logs {CONTAINER}`")


def down(out: Path) -> None:
    for name in labelled():
        docker("rm", "-f", name)
    pointer = out / POINTER
    if pointer.exists():
        folder = Path(pointer.read_text().strip())
        if folder.name.startswith("scratch-") and folder.parent == out and folder.exists():
            shutil.rmtree(folder)
        pointer.unlink()
    left = labelled()
    print(f"scratch down: labelled containers left {left or 'none'}; port {PORT} "
          f"{'free' if port_free() else 'STILL IN USE'}")
    if left or not port_free():
        raise SystemExit(1)


def status() -> dict:
    info = {"container": docker("inspect", "-f", "{{.State.Status}} {{.State.StartedAt}}", CONTAINER, check=False)
            or "absent", "labelled": labelled(), "port_free": port_free(), "laz_started_at": laz_started_at()}
    print(json.dumps(info, indent=1))
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("up", "down", "status"))
    ap.add_argument("--digest", default=DEFAULT_DIGEST, help="the platform image digest (default: the laz pin)")
    ap.add_argument("--out", default="~/.re-gate/roundtrip-probe")
    args = ap.parse_args(argv)
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    if args.action == "up":
        up(args.digest, out)
    elif args.action == "down":
        down(out)
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
