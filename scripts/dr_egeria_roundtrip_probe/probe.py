#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright Contributors to the ODPi Egeria project.
"""Dr.Egeria round-trip probe (BRIEF-DR-EGERIA-ROUNDTRIP-PROBE-2026-11-12), phase 1: property styles.

For every Dr.Egeria Create command, set every property-style attribute to a recognisable value, run the
generated document through `dr_egeria --process` against a SCRATCH Egeria, read each element back and
report which values did not come back (DROPPED / CHANGED / DEFAULTED / NOT FOUND ...).

SCRATCH ONLY. The guard refuses to start unless the URL is exactly https://localhost:19443 (or
127.0.0.1) AND Docker shows the container publishing host port 19443 is `egeria-scratch-roundtrip`
labelled `purpose=roundtrip-probe`, AND its platform origin answers. Ports 9443, 8443 and 7443 are
refused on any host. The refusal happens before any request. See README.md.

    uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/probe.py --smoke
    uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/probe.py --run
    uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/probe.py --run --url https://localhost:9443   # refused
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

SCRATCH_URL = "https://localhost:19443"
SCRATCH_HOSTS = {"localhost", "127.0.0.1"}
SCRATCH_PORT = 19443
SCRATCH_CONTAINER = "egeria-scratch-roundtrip"
SCRATCH_LABEL = "purpose=roundtrip-probe"
REFUSED_PORTS = {9443, 8443, 7443}
IMAGE = "odpi/egeria-platform@sha256:757a5df0db06f526cd92565210eed55ab60adc8e7ab6536a402f33efafc7ea9a"
VIEW_SERVER = "view-server"
REPO = Path(__file__).resolve().parents[2]
COMPACT = REPO / "md_processing" / "data" / "compact_commands"

PHASE1_STYLES = {"Simple", "Simple List", "Simple Int", "Simple Float", "Line List", "Bool", "Valid Value",
                 "Enum", "Dictionary", "Named DICT"}
RELATIONSHIP_STYLES = {"Reference Name", "Reference Name List", "GUID", "QN"}
#: Attributes that steer the command rather than carry a property: never set, listed as SKIPPED (control).
CONTROL_ATTRIBUTES = {
    "Merge Update": "steers update behaviour, not a property",
    "Parent Relationship Type Name": "names the parent relationship (phase 2)",
    "Parent at End1": "names the parent relationship's end (phase 2)",
    "Journal Entry": "creates a note-log entry, a separate element (phase 2)",
    "Effective Time": "a request option (the time to query as of), not a property",
    "As Of Time": "a request option, not a property",
    "Display Name": "set by the probe's naming convention and checked as such",
    "Template GUID": "names a template element; needs a real target (phase 2)",
    "Placeholder Property Values": "fills a real template's placeholders (phase 2)",
    "For Lineage": "a request option, not a property",
    "For Duplicate Processing": "a request option, not a property",
    "Request ID": "a request option, not a property",
    "Is Own Anchor": "an anchoring option for the create request, not a property",
    "External Source Name": "provenance option; needs a registered external source (phase 2)",
    "Zone Membership": ("needs a real zone: made-up zones make the element unreadable by the probe user "
                        "(OPEN-METADATA-SECURITY-403-020 on the first runs), phase 2"),
}
#: Attributes whose probe value makes Egeria reject the whole create (found on the first run, 2026-11-12,
#: run-20261112T092519Z). Not sent, so the rest of the command can be diffed; each is reported as a
#: REJECTED row with its cause, and the cause is a finding in its own right.
REJECTED = {
    "Parent Relationship Attributes": (
        "pyegeria-side: sent raw as parentRelationshipProperties with no \"class\"; Egeria 400 "
        "InvalidTypeIdException on every create (108 of 110 failures on the first run)"),
    "Template Properties": (
        "pyegeria-side: sent raw as replacementProperties with no \"class\"; Egeria 400 InvalidTypeIdException"),
    "Generic Initial Classifications": (
        "pyegeria-side: sent raw as replacementClassifications with no \"class\"; Egeria 400 InvalidTypeIdException"),
    "Extended Properties": (
        "input-side: an arbitrary key is not a property of the subtype; Egeria 400 OMRS-REPOSITORY-400-028 "
        "(correct behaviour; needs real subtype property names, phase 2)"),
    "Absolute Uncertainty": (
        "pyegeria-side: Simple Float sent as the string \"7.5\"; Egeria's field is a Long, 400 "
        "'Cannot deserialize value of type java.lang.Long from String'"),
    "Relative Uncertainty": (
        "pyegeria-side: Simple Float sent as the string \"7.5\"; Egeria's field is a Long, 400 "
        "'Cannot deserialize value of type java.lang.Long from String'"),
}
#: Where an attribute is stored when it is not `properties.<camelCase>` -- one row per known place.
LOCATIONS = {
    "Zone Membership": ("header.zoneMembership.classificationProperties.zoneMembership",
                        "zones are the ZoneMembership classification in the element header"),
    "Confidence Classification": ("cls:Confidence", "a governance classification in the header, stored as a level"),
    "Confidentiality Classification": ("cls:Confidentiality", "a governance classification, stored as a level"),
    "Criticality Classification": ("cls:Criticality", "a governance classification, stored as a level"),
    "Impact Classification": ("cls:Impact", "a governance classification, stored as a level"),
    "Retention Classification": ("cls:Retention", "a governance classification, stored as a basis"),
    "Security Tags": ("cls:SecurityTags", "the SecurityTags classification in the header"),
    "Policy Management Point": ("cls:PolicyManagementPoint", "a classification in the header"),
    "Status": ("header.status", "element status is a header field"),
    "Search Keywords": ("rel.searchKeywords.keyword", "keywords are SearchKeyword elements linked to the element"),
}


# ── Guard ──

class Refused(SystemExit):
    pass


def guard(url: str) -> None:
    """Refuse anything but the scratch platform, before any request to it."""
    p = urlparse(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    if port in REFUSED_PORTS:
        raise Refused(f"REFUSED: {url} uses port {port}, a laz/quickstart port; this probe runs only against "
                      f"the scratch platform {SCRATCH_URL}")
    if p.scheme != "https" or p.hostname not in SCRATCH_HOSTS or port != SCRATCH_PORT or p.path not in ("", "/"):
        raise Refused(f"REFUSED: {url} is not the scratch platform {SCRATCH_URL}")
    out = subprocess.run(["docker", "ps", "--filter", f"label={SCRATCH_LABEL}", "--filter", f"publish={SCRATCH_PORT}",
                          "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    if out != [SCRATCH_CONTAINER]:
        raise Refused(f"REFUSED: no running container {SCRATCH_CONTAINER} labelled {SCRATCH_LABEL} publishes port "
                      f"{SCRATCH_PORT} (docker shows {out})")
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    origin = urllib.request.urlopen(f"{url}/open-metadata/platform-services/server-platform/origin",
                                    context=ctx, timeout=10).read().decode()
    if "Egeria OMAG Server Platform" not in origin:
        raise Refused(f"REFUSED: {url} origin is {origin!r}")


def scratch_password(user: str) -> str:
    """The user's password from the scratch container's own (the image's demo) secrets; never printed."""
    if os.environ.get("PROBE_PASSWORD"):
        return os.environ["PROBE_PASSWORD"]
    script = (f"awk '/^      {user}:/{{f=1}} f && /clearPassword:/{{sub(/.*clearPassword: */,\"\"); print; exit}}' "
              "/deployments/secrets/coco-user-directory.omsecrets")
    pw = subprocess.run(["docker", "exec", SCRATCH_CONTAINER, "sh", "-c", script],
                        capture_output=True, text=True).stdout.strip()
    if not pw:
        raise SystemExit(f"no password for {user} in the scratch container's secrets")
    return pw


def probe_env(url: str, user: str, password: str, root: Path) -> dict:
    """A clean environment: nothing EGERIA_*/PYEGERIA_* inherited, the scratch settings set explicitly."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EGERIA_", "PYEGERIA_"))}
    env.update({"EGERIA_PLATFORM_URL": url, "EGERIA_VIEW_SERVER_URL": url, "EGERIA_VIEW_SERVER": VIEW_SERVER,
                "EGERIA_USER": user, "EGERIA_USER_PASSWORD": password, "PYEGERIA_ROOT_PATH": str(root),
                "DR_EGERIA_OUTBOX_PATH": "outbox", "EGERIA_WIDTH": "100000", "PYEGERIA_CONFIG_DIRECTORY": str(root),
                # local (non-Egeria) stores and caches stay inside the run folder, never the user's ~/.pyegeria
                # (the first run wrote a Dashboard Sheet into ~/.pyegeria/dashboard_sheets.json)
                "HOME": str(root / "home"),
                "PYEGERIA_DASHBOARD_SHEETS_STORE": str(root / "home" / ".pyegeria" / "dashboard_sheets.json"),
                "PYEGERIA_USER_REPORT_SPECS_DIR": str(root / "home" / ".pyegeria" / "report_specs")})
    (root / "home" / ".pyegeria").mkdir(parents=True, exist_ok=True)
    return env


def command_error(log_text: str, qn: str) -> str:
    """The Egeria/Dr.Egeria error that follows this command's first request body in the log."""
    at = log_text.find(f'"{qn}"')
    if at < 0:
        return ""
    tail = log_text[at:at + 40000]
    nxt = tail.find("DEBUG CMD:")
    tail = tail[:nxt] if nxt > 0 else tail
    for pattern in (r'"exceptionErrorMessage":"((?:[^"\\]|\\.){0,240})', r"Egeria Message\s*│\s*(.{0,240}?)\s*│",
                    r"(Validation failed:.{0,200})", r"(Execution failed:.{0,200})"):
        m = re.search(pattern, tail)
        if m:
            return m.group(1).strip()
    return ""


# ── Commands and values ──

def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", text.title())


def create_commands():
    """[(family, command, spec)] for every Create command, resolved by key, display name or alternate."""
    from md_processing.md_processing_utils.md_processing_constants import get_command_spec, load_commands
    load_commands()
    out = []
    for f in sorted(COMPACT.glob("*.json")):
        data = json.loads(f.read_text())
        family = data.get("family") or f.stem
        for key, c in (data.get("commands") or {}).items():
            if c.get("verb") != "Create":
                continue
            alts = c.get("alternate_names") or []
            alts = alts if isinstance(alts, list) else alts.split(";")
            spec = None
            for cand in [key, c.get("display_name")] + list(alts):
                if cand and str(cand).strip() and get_command_spec(str(cand).strip()):
                    spec = get_command_spec(str(cand).strip())
                    break
            out.append((family, key, spec))
    return out


def is_date(attr) -> bool:
    return attr.get("style") == "Simple" and bool(re.search(r"(Date|Time|Effective From|Effective To)$", attr["name"]))


def plan(attr, cslug: str):
    """(kind, markdown value, expected) for an attribute, or (SKIP verdict, None, reason)."""
    name, style = attr["name"], attr.get("style") or "Simple"
    if name in CONTROL_ATTRIBUTES:
        return "SKIPPED (control)", None, CONTROL_ATTRIBUTES[name]
    if name in REJECTED:
        return "REJECTED (breaks the create)", None, REJECTED[name]
    if style in RELATIONSHIP_STYLES or attr.get("existing_element"):
        return "SKIPPED (relationship – phase 2)", None, f"style {style}" + (", existing_element" if attr.get("existing_element") else "")
    if style not in PHASE1_STYLES:
        return "SKIPPED (not a phase-1 style)", None, f"style {style}"
    base = f"RTP {cslug} {slug(name)}"
    default = attr.get("default_value")
    if name == "Status":  # the element header status: a real, non-default ElementStatus value
        return "valid", "DRAFT", "DRAFT"
    if name == "Effective From":
        return "date", "2020-01-02", "2020-01-02"
    if name == "Effective To" or is_date(attr):
        return "date", "2031-01-02", "2031-01-02"
    if style == "Simple":
        return "text", base, base
    if style in ("Simple List", "Line List"):
        items = [f"{base}-1", f"{base}-2"]
        return "list", "\n".join(f"- {i}" for i in items) if style == "Simple List" else "\n".join(items), items
    if style == "Simple Int":
        return "int", "7", 7
    if style == "Simple Float":
        return "float", "7.5", 7.5
    if style == "Bool":
        want = not (str(default).strip().lower() in ("true", "yes", "1"))
        return "bool", "true" if want else "false", want
    if style in ("Valid Value", "Enum"):
        vals = [str(v) for v in (attr.get("valid_values") or []) if str(v).strip() and str(v).upper() != "DELETED"]
        # the second value in the list, so a stored value is told apart from the default (brief §2)
        candidates = [v for v in vals if v != str(default)]
        if not candidates:
            return "SKIPPED (no non-default valid value)", None, f"valid values {vals}"
        choice = vals[1] if len(vals) > 1 and vals[1] != str(default) else candidates[0]
        return "valid", choice, choice
    if style in ("Dictionary", "Named DICT"):
        return "dict", f"rtpKey: {base}", {"rtpKey": base}
    return "SKIPPED (not a phase-1 style)", None, f"style {style}"


def build_family_doc(family: str, commands, out_dir: Path, tag: str = ""):
    """The family's Dr.Egeria document and its per-command plan."""
    lines, plans = [f"# RTP round-trip probe: {family}", ""], []
    for _fam, command, spec in commands:
        cslug = slug(command)
        qn = f"RTP::{tag}::{cslug}" if tag else f"RTP::{cslug}"
        display = f"RTP {cslug} DisplayName {tag}".rstrip()
        rows = []
        lines += ["___", "", f"## {command}", "", "### Display Name", display, "", "### Qualified Name", qn, ""]
        for attr in spec.get("Attributes", []):
            if attr["name"] in ("Qualified Name",):
                continue
            kind, md, expected = plan(attr, cslug)
            rows.append({"attribute": attr["name"], "style": attr.get("style"), "kind": kind,
                         "sent": expected if md is not None else None, "reason": expected if md is None else None,
                         "property": attr.get("property_name") or None, "variable": attr.get("variable_name"),
                         "default": attr.get("default_value")})
            if md is not None:
                lines += [f"### {attr['name']}", md, ""]
        plans.append({"family": family, "command": command, "qualified_name": qn, "display_name": display,
                      "rows": rows})
    lines += ["___", ""]
    doc = out_dir / f"{slug(family)}.md"
    doc.write_text("\n".join(lines), encoding="utf-8")
    return doc, plans


# ── Read back and compare ──

def camel(var: str) -> str:
    parts = (var or "").split("_")
    return parts[0] + "".join(p.title() for p in parts[1:]) if parts else ""


def classification(element: dict, name: str):
    """The properties of the header classification called `name` (any slot), or None."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("classificationName") == name:
                return node.get("classificationProperties") or {"present": True}
            for v in node.values():
                hit = walk(v)
                if hit is not None:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = walk(v)
                if hit is not None:
                    return hit
        return None
    return walk(element.get("elementHeader") or {})


def dig(element: dict, path: str):
    if path.startswith("cls:"):
        return classification(element, path[4:])
    if path.startswith("rel."):
        _, rel, key = path.split(".", 2)
        items = element.get(rel) or []
        return [((i.get("relatedElement") or {}).get("properties") or {}).get(key) for i in items] or None
    node = element
    for part in path.split("."):
        node = (element.get("elementHeader") if part == "header" and node is element else
                (node.get(part) if isinstance(node, dict) else None))
        if node is None:
            return None
    return node


def find_value(node, wanted, path=""):
    """Where `wanted` appears anywhere in the element JSON (for NOT FOUND hints)."""
    if isinstance(node, dict):
        for k, v in node.items():
            hit = find_value(v, wanted, f"{path}.{k}" if path else k)
            if hit:
                return hit
    elif isinstance(node, list):
        if wanted in node:
            return path
        for i, v in enumerate(node):
            hit = find_value(v, wanted, f"{path}[{i}]")
            if hit:
                return hit
    elif node == wanted:
        return path
    return None


def norm(kind, value):
    if value is None:
        return None
    if kind == "date":
        return str(value)[:10]
    if kind == "valid":
        return re.sub(r"[^a-z0-9]", "", str(value).lower())
    if kind == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if kind == "bool":
        return value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
    return value


def verdict(row, element):
    kind, sent = row["kind"], row["sent"]
    if row["attribute"] in LOCATIONS:
        path = LOCATIONS[row["attribute"]][0]
        got = dig(element, path)
    else:
        key = row["property"] or camel(row["variable"])
        path = f"properties.{key}"
        got = (element.get("properties") or {}).get(key)
    if got in (None, "", [], {}):
        probe = sent[0] if isinstance(sent, list) else (next(iter(sent.values())) if isinstance(sent, dict) else sent)
        seen = find_value(element, probe) if isinstance(probe, str) else None
        if seen:
            return "NOT FOUND", None, f"not at {path}; seen at {seen}"
        return "DROPPED", None, f"absent at {path}"
    if path.startswith("cls:"):
        stored = {k: v for k, v in got.items() if k not in ("class", "typeName")}
        if row["attribute"] == "Security Tags":
            ok = set(map(str, sent if isinstance(sent, list) else [sent])) <= set(map(str, stored.get("securityLabels") or []))
            return ("MATCH" if ok else "CHANGED"), stored, path
        return "MATCH", stored, f"{path} present (Dr.Egeria sends the valid value as a level number)"
    if norm(kind, got) == norm(kind, sent):
        return "MATCH", got, path
    if row["default"] not in (None, "") and norm(kind, got) == norm(kind, row["default"]):
        return "DEFAULTED", got, path
    return "CHANGED", got, path


# ── Running ──

def run_dr_egeria(doc: Path, env: dict, url: str, user: str, log: Path) -> str:
    cmd = [sys.executable, "-m", "commands.cat.dr_egeria", str(doc), "--process", "--advanced", "--debug",
           "--server", VIEW_SERVER, "--url", url, "--userid", user, "--summary-only"]
    proc = subprocess.run(cmd, env=env, cwd=str(log.parent), capture_output=True, text=True, timeout=3600)
    log.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    return proc.stdout + proc.stderr


def command_segment(log_text: str, display: str) -> str:
    """The log between this command's `DEBUG CMD` marker and the next one (its create and follow-up calls)."""
    at = log_text.find(f"display_name='{display}'")
    if at < 0:
        return ""
    nxt = log_text.find("DEBUG CMD:", at)
    return log_text[at:nxt if nxt > 0 else len(log_text)]


def bodies_for(log_text: str, qn: str, display: str = ""):
    """Request bodies for this command: every body in its log segment (create plus follow-up classify
    calls, which carry a GUID rather than the qualified name), and any body elsewhere carrying the QN."""
    out, dec = [], json.JSONDecoder()
    segment = command_segment(log_text, display) if display else ""
    for text, need_qn in ((segment, False), (log_text, True)):
        for m in re.finditer(r"\[DEBUG\] Body:\s*\n", text):
            try:
                body, _ = dec.raw_decode(text[m.end():].lstrip())
            except ValueError:
                continue
            if (not need_qn or qn in json.dumps(body)) and body not in out:
                out.append(body)
    return out


def summary_row(log_text: str, command: str, display: str):
    """(status, message, guid) from Dr.Egeria's summary table row for this command, or None."""
    for line in log_text.splitlines():
        cells = [c.strip() for c in line.split("│")]
        if len(cells) > 6 and cells[1] == command and display in cells:
            msg = cells[-2] if cells[-1] == "" else cells[-1]
            guid = re.search(r"GUID: ([A-Za-z]*-?[0-9a-f]{8}-[0-9a-f-]{27})", msg)
            return cells[3], msg, guid.group(1) if guid else None
    for line in log_text.splitlines():  # some processors show their own name (e.g. Kafka Server Name), not ours
        cells = [c.strip() for c in line.split("│")]
        if len(cells) > 6 and cells[1] == command and cells[3] in ("SUCCESS", "FAILURE"):
            msg = cells[-2] if cells[-1] == "" else cells[-1]
            guid = re.search(r"GUID: ([A-Za-z]*-?[0-9a-f]{8}-[0-9a-f-]{27})", msg)
            return cells[3], msg, guid.group(1) if guid else None
    return None


def side(row, bodies):
    """pyegeria-side (the value is not in the request body under the expected key) or Egeria-side (it is,
    and did not come back). Key-aware: a value found only under another key is reported with that key."""
    if not bodies:
        return "unknown (no request body captured)"
    text = json.dumps(bodies)
    loc = LOCATIONS.get(row["attribute"], ("",))[0]
    if loc.startswith("cls:"):  # sent as a classify call carrying a level, not the valid-value name
        present = re.search(rf'"class": "{loc[4:]}(Classification)?Properties"', text) is not None
        return "Egeria-side (in the request body)" if present else "pyegeria-side (not in the request body)"
    key = row["property"] or camel(row["variable"])
    sent = row["sent"]
    probe = sent[0] if isinstance(sent, list) else (next(iter(sent.values())) if isinstance(sent, dict) else sent)
    hits = []

    def walk(node, k=None):
        if isinstance(node, dict):
            for kk, vv in node.items():
                walk(vv, kk)
        elif isinstance(node, list):
            for vv in node:
                walk(vv, k)
        elif k is not None and str(node).lower() == str(probe).lower():
            hits.append(k)
        elif k is not None and isinstance(probe, str) and isinstance(node, str) and probe.lower() in node.lower():
            hits.append(k)

    for b in bodies:
        walk(b)
    if isinstance(probe, str):
        # dict values are found under their own key (rtpKey): the attribute's key is the parent
        if isinstance(sent, dict) and "rtpKey" in hits:
            hits = [key] if f'"{key}"' in text else ["(a dictionary under another key)"]
    if key in hits:
        return f"Egeria-side (in the request body as {key})"
    if hits and isinstance(probe, str):  # a bool/number equal to some other field's value proves nothing
        other = sorted(set(hits))
        return f"pyegeria-side? (sent as {', '.join(other)}, not {key}: check the key against the Java bean)"
    return "pyegeria-side (not in the request body)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=SCRATCH_URL)
    ap.add_argument("--user", default="garygeeke")
    ap.add_argument("--out", default="~/.re-gate/roundtrip-probe")
    ap.add_argument("--smoke", action="store_true", help="create one glossary and read it back")
    ap.add_argument("--run", action="store_true", help="the full phase-1 run")
    ap.add_argument("--families", default="", help="comma-separated family filter (default: all)")
    args = ap.parse_args(argv)

    guard(args.url)  # before anything else touches the platform
    from pyegeria import EgeriaTech
    import importlib.metadata as md
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out).expanduser()
    run_dir = out / f"run-{stamp}"
    (run_dir / "docs").mkdir(parents=True, exist_ok=True)
    password = scratch_password(args.user)
    env = probe_env(args.url, args.user, password, run_dir)
    print(f"probe: url={args.url} server={VIEW_SERVER} user={args.user} pyegeria={md.version('pyegeria')} "
          f"run={run_dir}")
    client = EgeriaTech(VIEW_SERVER, args.url, args.user, password)
    client.create_egeria_bearer_token()

    if args.smoke:
        doc = run_dir / "docs" / "smoke.md"
        doc.write_text("## Create Glossary\n\n### Display Name\nRTP Smoke Glossary\n\n### Qualified Name\n"
                       f"RTP::Smoke::{stamp}\n\n### Description\nRTP smoke test\n")
        text = run_dr_egeria(doc, env, args.url, args.user, run_dir / "smoke.log")
        el = client.get_element_by_unique_name(f"RTP::Smoke::{stamp}", output_format="JSON")
        ok = isinstance(el, dict) and (el.get("properties") or {}).get("description") == "RTP smoke test"
        print("smoke:", "PASS" if ok else "FAIL", (el.get("elementHeader", {}).get("guid") if isinstance(el, dict) else el))
        if not ok:
            print(text[-3000:])
        return 0 if ok else 1

    if not args.run:
        ap.error("choose --smoke or --run")
    start = dt.datetime.now(dt.timezone.utc)
    commands = create_commands()
    wanted = {f.strip() for f in args.families.split(",") if f.strip()}
    results, families = [], {}
    for fam, command, spec in commands:
        if wanted and fam not in wanted:
            continue
        if spec is None:
            results.append({"family": fam, "command": command, "attribute": "", "style": "", "sent": None,
                            "read": None, "verdict": "UNRESOLVED", "note": "command name did not resolve"})
            continue
        families.setdefault(fam, []).append((fam, command, spec))
    for fam, cmds in families.items():
        doc, plans = build_family_doc(fam, cmds, run_dir / "docs", stamp)
        log_text = run_dr_egeria(doc, env, args.url, args.user, run_dir / f"{slug(fam)}.log")
        for p in plans:
            row = summary_row(log_text, p["command"], p["display_name"])
            try:
                el = client.get_element_by_unique_name(p["qualified_name"], output_format="JSON")
                if not isinstance(el, dict) and row and row[2]:
                    # some processors derive their own qualified name: read back by the GUID they reported
                    el = client.get_element_by_guid(row[2], output_format="JSON")
            except Exception as exc:  # noqa: BLE001
                el = f"{type(exc).__name__}: {exc}"
            if not isinstance(el, dict):
                err = command_error(log_text, p["qualified_name"]) or ""
                if row:
                    err = f"{row[0]}: {row[1]}" + (f" | {err}" if err else "")
                    if row[0] == "SUCCESS":
                        err = f"created but not readable back: {str(el)[:200]} | {err}"
                err = err or str(el)[:200]
                failed = "AUTH" if re.search(r"not authori[sz]ed|\b403\b|-403-", err, re.I) else "CREATE-FAILED"
                skipped = collections.Counter(r["kind"] for r in p["rows"] if r["kind"].startswith(("SKIPPED", "REJECTED")))
                results.append({"family": fam, "command": p["command"], "attribute": "", "style": "", "sent": None,
                                "read": None, "verdict": failed, "note": err[:300],
                                "skipped": dict(skipped)})
                continue
            bodies = bodies_for(log_text, p["qualified_name"], p["display_name"])
            for row in p["rows"]:
                if row["kind"].startswith(("SKIPPED", "REJECTED")):
                    results.append({"family": fam, "command": p["command"], "attribute": row["attribute"],
                                    "style": row["style"], "sent": None, "read": None, "verdict": row["kind"],
                                    "note": row["reason"]})
                    continue
                v, got, note = verdict(row, el)
                r = {"family": fam, "command": p["command"], "attribute": row["attribute"], "style": row["style"],
                     "sent": row["sent"], "read": got, "verdict": v, "note": note}
                if v in ("DROPPED", "CHANGED", "DEFAULTED"):
                    r["side"] = side(row, bodies)
                results.append(r)
    end = dt.datetime.now(dt.timezone.utc)
    meta = {"image": IMAGE, "option": "A (simple-metadata-store + view-server)", "pyegeria": md.version("pyegeria"),
            "user": args.user, "start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"),
            "commands": sum(len(c) for c in families.values()), "run_dir": str(run_dir)}
    (out / f"RESULTS-{stamp}.json").write_text(json.dumps({"meta": meta, "rows": results}, indent=1, default=str))
    print(f"results: {out / f'RESULTS-{stamp}.json'} ({len(results)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
