# Edge 75/25 deployment gate (dev and PoC)

This opt-in configuration uses the **Batch saved in dashboard-web** as the
source of breed, sex, and start date. The Batch must be active and bound in the
web UI to the **same Cloud device ID and station ID** sent by IoT. A device's
display serial number is not its Cloud ID. One active binding must resolve.

The local trial model supports Arbor Acres Plus, sexes `male`, `female`, or
`as_hatched`, and age 1–56 days. It uses 75% approved growth standard plus 25%
visual geometry proxy. It does not classify image pixels. Deploying the image
alone does not activate it.

## Prerequisites on each host

1. Deploy the Edge and Cloud services normally. `edge-policy-sync` must reach
   the Cloud BFF and its Batch context API. Provide a valid JWT with
   `edge_service` role and matching `tenant_id`, `site_id`, `farm_id`, and
   `barn_id` claims. Do not put the token in this repository.
2. In dashboard-web, create/update an active Batch with `breedCode`, `sex`, and
   `startDate`, then bind the station/device to that Batch. Record the **IDs**
   returned by the web API, not their display names.
   On the IoT host, add `iot-web-batch-identity.compose.yml` **after** its
   existing Compose files, set `WEB_BATCH_DEVICE_ID` and
   `WEB_BATCH_STATION_ID` to those Cloud IDs, and recreate only
   `weight-vision-service`. Its normal `wv-001/st-01` display IDs cannot
   resolve the UUID binding saved by this web Batch.
3. Transfer `edge-hybrid75-config-20261009.zip` and
   `edge-hybrid75-images-20261009.tar` into the PoC `edge-layer` directory.
   The zip contains the Edge and IoT overrides, source patch, verifier, and
   checksum. The tar is
   1,016,557,568 bytes and its SHA-256 is
   `CF1D2ABB85C2E8B7CE9EAB52DF5F12936E262F15F3D98BF6823288FB2FB7BB4D`.
   The source patch matters because `docker-compose.dev.yml` mounts the Edge
   source directories over the image contents.
   The tar contains only the two changed Edge images. Existing Cloud, IoT,
   other Edge, and infrastructure images must already be present on PoC or
   transferred separately for a fresh offline installation.

## Ubuntu PoC commands

Run from `edge-layer` after setting values for the actual PoC site:

```bash
# Place the transferred zip and tar in the current edge-layer directory first.
unzip -o edge-hybrid75-config-20261009.zip
sha256sum -c edge-hybrid75-images-20261009.tar.sha256
python3 apply_edge_hybrid75_source.py .
docker load -i edge-hybrid75-images-20261009.tar
EDGE_PROJECT=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' farmiq-edge-vision-inference)
docker tag edge-layer-edge-vision-inference:hybrid75-20261009 "$EDGE_PROJECT-edge-vision-inference:latest"
docker tag edge-layer-edge-weighvision-session:hybrid75-20261009 "$EDGE_PROJECT-edge-weighvision-session:latest"

export EDGE_BFF_BASE_URL='https://<cloud-bff-host>'
export EDGE_CONTEXTS='[{"tenantId":"t-001","farmId":"f-001","barnId":"b-001","siteId":"<actual-site-id>"}]'
read -rsp 'Scoped edge_service JWT: ' EDGE_CLOUD_TOKEN; echo
export EDGE_CLOUD_TOKEN

docker compose -p "$EDGE_PROJECT" -f docker-compose.yml -f docker-compose.dev.yml \
  -f edge-hybrid75.compose.yml config --quiet
docker compose -p "$EDGE_PROJECT" -f docker-compose.yml -f docker-compose.dev.yml \
  -f edge-hybrid75.compose.yml up -d --no-deps --no-build \
  edge-policy-sync edge-weighvision-session edge-media-store edge-vision-inference

python3 scripts/verify_edge_hybrid75.py \
  --tenant t-001 --farm f-001 --barn b-001 --site '<actual-site-id>' \
  --device '<Cloud-device-UUID>' --station '<Cloud-station-UUID>'
```

Wait for a `preflight: PASS`. It verifies the deployed flags, package hashes,
Cloud Batch data, exact device/station binding, and Edge resolver cache.
If it fails, resolve the reported issue before testing a capture.

After one **new real capture** from that bound device/station, run:

```bash
python3 scripts/verify_edge_hybrid75.py \
  --tenant t-001 --farm f-001 --barn b-001 --site '<actual-site-id>' \
  --device '<Cloud-device-UUID>' --station '<Cloud-station-UUID>' \
  --session '<new-session-id>'
```

Only `end_to_end: PASS` confirms that this host created a session with the
web Batch provenance and persisted a non-stub `hybrid-trial-75s25v-v1` result
whose 75/25 formula is correct. Repeat this gate independently on dev and PoC.

On the IoT host, first inspect the current Compose file list so the existing
network overrides are retained:

```bash
docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' iot-layer-weight-vision-service-1
export WEB_BATCH_DEVICE_ID='<Cloud-device-UUID>'
export WEB_BATCH_STATION_ID='<Cloud-station-UUID>'
# Append -f iot-web-batch-identity.compose.yml to that existing file list:
docker compose -p '<existing-IoT-project>' -f docker-compose.yml \
  -f iot-web-batch-identity.compose.yml up -d --no-deps --no-build weight-vision-service
```

If the inspect output lists more than `docker-compose.yml`, put those files
between the base file and the identity override in the last command. Then
check the container's `DEVICE_ID` and `STATION_ID` with `docker inspect`.
When IoT runs on the same Docker host as Edge, add
`--iot-container iot-layer-weight-vision-service-1` to the verifier command.

For dev PowerShell, set the same three variables with `$env:...` and run the
same Compose files and `python scripts/verify_edge_hybrid75.py` command.

## Current dev findings (2026-10-09)

- The model package exists in the running Edge image. Its manifest checksums
  pass and it loads successfully.
- Before the 2026-10-09 deployment, the required flags were `false`, the Edge
  contexts/token were empty, and the Cloud Batch API returned HTTP 401. The
  dev Edge was then reconfigured; the later preflight and strict session gate
  passed. Recheck these settings on every deploy because a temporary token
  or an omitted Compose override can regress them.
- The active `t-001/f-001/b-001` Batch has Arbor Acres Plus, male, and a
  start date. Its binding uses Cloud device ID
  `f2dc205d-92a6-4a1b-ba80-6c95612dcc9d` and Cloud station ID
  `f201fd16-2485-4d60-903f-b7b577114900`. The dev IoT `.env` currently
  says `wv-001` and `st-01`, which are different IDs. The active dev IoT
  container now overrides those with the Cloud UUIDs; its config was verified
  against the Batch. Preserve this override on subsequent Compose updates.
- With a temporary dev `edge_service` JWT, the required flags enabled and the
  actual Cloud device/station IDs allowlisted, the dev preflight passed.
  A replay of an archived real chicken image reached the persisted 75/25
  inference result for session `hybrid75-dev-1791537336`: 338.0 g standard,
  375.6502 g visual proxy, 347.4126 g hybrid. The replay uses the archived
  geometry and scale value with a current test timestamp; it is an integration
  test, not a fresh physical measurement or an accuracy validation.
- The first replay showed a duplicate `shadow_stub` result because media
  completion triggered inference before capture metadata existed. The hybrid
  override disables that trigger; IoT still requests inference after storing
  metadata. Session `hybrid75-dev-1791537942` passed the stricter gate, with
  one 75/25 inference result in Edge and Cloud and no stub result. Cloud also
  stores one separate `capture-metadata.v1` record for the same session.
- The dev JWT expires 8 hours after creation. Replace it with a provisioned
  site-scoped credential for sustained operation. The PoC gate must pass on
  PoC itself; a dev pass cannot stand in for that host.
- The 2026-10-09 offline tar was loaded back into Dev. Its two images were
  used to recreate the session and vision containers (both healthy); a new
  archived-image replay session `hybrid75-dev-1791540386` passed preflight
  and end-to-end gates against the web Batch with no stub/fallback result.
