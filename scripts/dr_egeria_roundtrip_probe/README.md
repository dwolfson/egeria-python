# Dr.Egeria round-trip probe

Writes a recognisable value into every property-style attribute of every Dr.Egeria Create command,
runs the documents through `dr_egeria --process`, reads each element back and reports what didn't come
back (BRIEF-DR-EGERIA-ROUNDTRIP-PROBE-2026-11-12, phase 1).

## Scratch only

**This probe never runs against a real Egeria (laz or any shared platform).** `probe.py` refuses to
start, before any request, unless all of these hold:

- the URL is exactly `https://localhost:19443` (or `https://127.0.0.1:19443`);
- Docker shows the container publishing host port 19443 is `egeria-scratch-roundtrip`, labelled
  `purpose=roundtrip-probe`;
- that platform's origin answers "Egeria OMAG Server Platform".

Ports 9443, 8443 and 7443 are refused on any host. Its environment is rebuilt: no inherited `EGERIA_*` or
`PYEGERIA_*` variable, no `.env`, no `config.json`, and `HOME` (with the Dashboard Sheet store and the user
report-specs folder) inside the run folder, so Dr.Egeria's local stores never touch the real `~/.pyegeria`.

## Scratch platform (option A)

Base image `odpi/egeria-platform@sha256:757a5df0…`, servers `simple-metadata-store` (in-memory, no Kafka)
and `view-server` only. Copy the image's `/deployments/data` and `application.properties` to a scratch
folder, then in the copies:

1. `view-server.config`: every `"omagserverName":"active-metadata-store"` → `"simple-metadata-store"` (40).
2. `application.properties`: `startup.server.list=simple-metadata-store,view-server`.
3. `application.properties`: the image's placeholder JSON has a typo (`YAMLSecretsStoreProvider".\` should be
   `",\`); without the fix no server starts.
4. **Never let it reach the host.** The image's placeholders point at `host.docker.internal:9192` (Kafka) and
   `https://host.docker.internal:7443`, which on a laptop running laz are laz's shared Kafka and a host port.
   Set `kafkaEndpoint` to `kafka-disabled.invalid:9092` and `egeriaEndpoint` to `https://localhost:7443` (the
   container itself), remove the Kafka audit-log destination from `view-server.config`, and start the
   container with `--add-host host.docker.internal:127.0.0.1`.

```bash
docker run -d --name egeria-scratch-roundtrip --label purpose=roundtrip-probe \
  --add-host host.docker.internal:127.0.0.1 -p 127.0.0.1:19443:7443 \
  -v <scratch>/data:/deployments/data -v <scratch>/application.properties:/deployments/application.properties \
  -e JAVA_OPTS_APPEND="-Xmx3g" odpi/egeria-platform@sha256:757a5df0db06f526cd92565210eed55ab60adc8e7ab6536a402f33efafc7ea9a
```

The user is one of the image's demo users (default `garygeeke`). Its password is read from the scratch
container's own secrets and never printed.

## Running

```bash
uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/probe.py --smoke      # one glossary, read back
uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/probe.py --run        # every Create command
uv run -p 3.13 python scripts/dr_egeria_roundtrip_probe/report.py ~/.re-gate/roundtrip-probe/RESULTS-<UTC>.json \
    [--extra-header triage.md]
```

Outputs, under `~/.re-gate/roundtrip-probe/`: `RESULTS-<UTC>.json` and `.md`, and `run-<UTC>/` with the
generated document per family, each `dr_egeria --process --advanced --debug` log, and the processed output.

## Verdicts

`MATCH`, `DROPPED` (sent, absent on read-back), `CHANGED` (present, different), `DEFAULTED` (equals the default,
not what was sent), `NOT FOUND` (not at the expected place but seen elsewhere in the element: a mapping-table
gap), `SKIPPED (relationship – phase 2)`, `SKIPPED (control)`, `SKIPPED (not a phase-1 style)`,
`REJECTED (breaks the create)` (attributes whose probe value makes Egeria reject the whole create; listed with
the cause in `REJECTED` in `probe.py`), `CREATE-FAILED`, `AUTH`, `UNRESOLVED`. Each DROPPED/CHANGED/DEFAULTED row says whether the value was in the
request body Dr.Egeria sent under the expected key (Egeria-side), not at all (pyegeria-side), or only under
another key (`pyegeria-side?`: check the key against the Java bean), from the `--debug` log.

Every run uses `RTP::<UTC>::<Command>` names, so a re-run on the same platform creates rather than updates.

## Teardown

```bash
docker rm -f egeria-scratch-roundtrip
rm -rf <scratch>/data
docker ps -a --filter label=purpose=roundtrip-probe     # empty
lsof -iTCP:19443 -sTCP:LISTEN                           # nothing
```

The repository is in memory, so nothing persists.
