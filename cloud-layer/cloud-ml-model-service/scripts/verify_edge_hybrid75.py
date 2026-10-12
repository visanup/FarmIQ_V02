"""Fail-closed deployment gate for the Edge Hybrid Trial 75S/25V.

Runs on either the Windows dev host or Ubuntu PoC with Python 3 and Docker.
Preflight checks the deployed flags, immutable model package, Cloud Batch data
from the web, and the Edge resolver cache. --session proves a real inference.
No credential is printed or saved by this script.
"""

import argparse
import json
import math
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


CONTAINERS = {
    "policy": "farmiq-edge-policy-sync",
    "session": "farmiq-edge-weighvision-session",
    "media": "farmiq-edge-media-store",
    "vision": "farmiq-edge-vision-inference",
}
EXPECTED_MODEL = "hybrid-trial-75s25v-v1"


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{' '.join(args[:3])}: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout


def env_for(container):
    info = json.loads(command("docker", "inspect", container))[0]
    if not info.get("State", {}).get("Running"):
        raise RuntimeError(f"{container} is not running")
    return dict(item.split("=", 1) for item in info["Config"]["Env"] if "=" in item)


def http_json(url, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"HTTP {error.code} from {url}: {error.read(400).decode(errors='replace')}") from error


def inspect_model():
    script = r'''
import hashlib,json,pathlib
from app.hybrid_trial_runtime import HybridTrialRuntime
p=pathlib.Path('/app/runtime-models/hybrid-trial-75s25v-v1-edge')
m=json.loads((p/'manifest.json').read_text())
assert m['model_version']=='hybrid-trial-75s25v-v1'
assert m['prediction_mode']=='individual_hybrid_standard_visual'
assert m['hybrid']['standard_weight']==0.75 and m['hybrid']['visual_weight']==0.25
for name,expected in m['files'].items():
    assert hashlib.sha256((p/name).read_bytes()).hexdigest()==expected, name
HybridTrialRuntime(str(p))
print(json.dumps({'model_version':m['model_version'],'sha256_verified':True,'loaded':True}))
'''
    return json.loads(command("docker", "exec", CONTAINERS["vision"], "python", "-c", script))


def cloud_batch(tenant, farm, barn, device, station, site):
    # Fetch inside policy-sync so the deployed BFF URL and scoped token are used.
    # Only the selected non-secret Batch fields are printed by the Node process.
    script = r'''
const [tenant,farm,barn,device,station,site]=process.argv.slice(1);
const url=new URL('/api/v1/edge/batch-context',process.env.BFF_BASE_URL);
url.searchParams.set('siteId',site);url.searchParams.set('sinceRevision','0');
fetch(url,{headers:{Authorization:`Bearer ${process.env.EDGE_CLOUD_TOKEN}`}})
 .then(async r=>{if(!r.ok)throw Error(`Cloud Batch API HTTP ${r.status}`);return r.json()})
 .then(data=>{
   const matches=(data.contexts||[]).filter(x=>x.tenantId===tenant&&x.farmId===farm&&x.barnId===barn&&x.status==='active'&&
     (x.deviceBindings||[]).some(b=>b.deviceId===device&&(b.stationId||null)===(station||null)));
   if(matches.length!==1)throw Error(`Expected one active web Batch binding; found ${matches.length}`);
   const x=matches[0];console.log(JSON.stringify({batchId:x.batchId,breedCode:x.breedCode,sex:x.sex,startDate:x.startDate,
     deviceId:device,stationId:station,revision:x.revision}));
 }).catch(e=>{console.error(e.message);process.exitCode=1});
'''
    output = command("docker", "exec", CONTAINERS["policy"], "node", "-e", script,
                     tenant, farm, barn, device, station or "", site)
    return json.loads(output)


def check_result(args, batch):
    session_url = f"{args.edge_base}/api/v1/weighvision/sessions/{urllib.parse.quote(args.session)}?tenantId={urllib.parse.quote(args.tenant)}"
    session = http_json(session_url, {"x-tenant-id": args.tenant})
    if isinstance(session, dict) and isinstance(session.get("data"), dict):
        session = session["data"]
    assert session.get("batchId") == batch["batchId"], "Session batch differs from web Batch"
    assert session.get("batchContextResolution") == "resolved", "Session Batch context is unresolved"
    assert session.get("deviceId") == args.device, "Session device differs from web binding"
    assert session.get("stationId") == args.station, "Session station differs from web binding"
    assert int(session.get("imageCount") or 0) > 0, "Session has no linked image"
    assert session.get("captureMetadata"), "Session has no capture geometry"
    provenance = session.get("batchContextProvenance") or {}
    context = provenance.get("context") or {}
    for key in ("breedCode", "sex", "startDate"):
        assert str(context.get(key)) == str(batch[key]), f"Session {key} differs from web Batch"

    url = f"{args.vision_base}/api/v1/inference/results?sessionId={urllib.parse.quote(args.session)}"
    payload = http_json(url)
    results = payload.get("results") or payload.get("data") or []
    if isinstance(results, dict):
        results = results.get("results") or []
    assert results, "No inference results for this session"
    unexpected = [(row.get("model_version") or row.get("modelVersion"),
                   (row.get("metadata") or {}).get("prediction_mode"))
                  for row in results if (row.get("model_version") or row.get("modelVersion")) != EXPECTED_MODEL]
    assert not unexpected, f"Session has non-75/25 inference results: {unexpected}"
    accepted = []
    for row in results:
        meta = row.get("metadata") or {}
        if (row.get("model_version") or row.get("modelVersion")) != EXPECTED_MODEL:
            continue
        if meta.get("prediction_mode") != "hybrid_trial_75s25v" or meta.get("stub_mode") is not False:
            continue
        if meta.get("batch_id") != batch["batchId"]:
            continue
        if meta.get("batch_context_resolution") != "resolved":
            continue
        if meta.get("breed_code") != batch["breedCode"] or meta.get("sex") != batch["sex"]:
            continue
        if not 1 <= int(meta.get("age_days") or -1) <= 56:
            continue
        if meta.get("fallback_engaged") is not False:
            continue
        standard = float(meta["standard_weight_g"])
        visual = float(meta["visual_standard_proxy_g"])
        hybrid = float(meta["hybrid_predicted_weight_g"])
        if not math.isclose(hybrid, 0.75 * standard + 0.25 * visual, rel_tol=1e-9):
            continue
        accepted.append({"result_id": row.get("id"), "weight_g": hybrid, "standard_g": standard, "visual_g": visual})
    assert accepted, "No 75/25 inference result with matching Batch and verified formula for this session"
    return accepted[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--farm", required=True)
    parser.add_argument("--barn", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--device", required=True, help="Cloud device ID, not display serial number")
    parser.add_argument("--station", default="", help="Cloud station ID, or omit if binding has no station")
    parser.add_argument("--session", help="Captured session ID; required for end-to-end PASS")
    parser.add_argument("--iot-container", help="Optional IoT container on this Docker host; checks its canonical device/station IDs")
    parser.add_argument("--edge-base", default="http://127.0.0.1:5105")
    parser.add_argument("--vision-base", default="http://127.0.0.1:5107")
    parser.add_argument("--policy-base", default="http://127.0.0.1:5109")
    args = parser.parse_args()

    policy = env_for(CONTAINERS["policy"])
    session = env_for(CONTAINERS["session"])
    media = env_for(CONTAINERS["media"])
    vision = env_for(CONTAINERS["vision"])
    if args.iot_container:
        iot = env_for(args.iot_container)
        assert iot.get("DEVICE_ID") == args.device, "IoT DEVICE_ID differs from web Batch binding"
        assert iot.get("STATION_ID") == args.station, "IoT STATION_ID differs from web Batch binding"
    expected = [
        (policy, "BATCH_CONTEXT_CACHE_ENABLED"),
        (session, "BATCH_CONTEXT_AUTO_BIND_ENABLED"),
        (vision, "BATCH_CONTEXT_INFERENCE_ENABLED"),
        (vision, "HYBRID_TRIAL_ENABLED"),
    ]
    for values, key in expected:
        assert values.get(key) == "true", f"{key} must be true (currently {values.get(key)!r})"
    assert media.get("TRIGGER_INFERENCE_ON_COMPLETE") == "false", "Premature media-complete inference trigger must be false"
    assert policy.get("EDGE_CLOUD_TOKEN"), "EDGE_CLOUD_TOKEN is empty"
    contexts = json.loads(policy.get("EDGE_CONTEXTS") or "[]")
    assert any(all(c.get(k) == v for k, v in (("tenantId", args.tenant), ("farmId", args.farm),
                                             ("barnId", args.barn), ("siteId", args.site))) for c in contexts), "EDGE_CONTEXTS misses this site"
    model = inspect_model()
    batch = cloud_batch(args.tenant, args.farm, args.barn, args.device, args.station, args.site)
    assert batch.get("breedCode") == "Arbor Acres Plus", "Local 75/25 package supports Arbor Acres Plus only"
    assert batch.get("sex") in ("male", "female", "as_hatched"), "Unsupported Batch sex"
    assert batch.get("startDate"), "Batch startDate is missing"
    resolver_url = (f"{args.policy_base}/api/v1/edge-config/batch-context/"
                    f"{urllib.parse.quote(args.tenant)}/{urllib.parse.quote(args.device)}/"
                    f"{urllib.parse.quote(args.station or '-')}")
    resolved = http_json(resolver_url).get("data") or {}
    assert resolved.get("outcome") == "resolved", f"Edge resolver: {resolved}"
    context = resolved.get("context") or {}
    for key in ("batchId", "breedCode", "sex", "startDate"):
        assert str(context.get(key)) == str(batch[key]), f"Edge cache {key} differs from Cloud web Batch"
    report = {"preflight": "PASS", "model": model, "batch": batch,
              "edge_batch_resolution": "resolved"}
    if args.iot_container:
        report["iot_identity"] = "MATCHES_WEB_BATCH"
    if args.session:
        report["end_to_end"] = "PASS"
        report["inference"] = check_result(args, batch)
    else:
        report["end_to_end"] = "NOT_TESTED: supply --session after a real capture"
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
