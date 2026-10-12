"""Apply the two verified Hybrid 75/25 Edge source fixes to an Edge checkout.

Run: python3 apply_edge_hybrid75_source.py /path/to/edge-layer
The script is idempotent and refuses to change an unexpected source version.
"""

import argparse
from pathlib import Path


PATCHES = (
    (
        "edge-vision-inference/app/job_service.py",
        (
            'bbox = detection.get("bbox") or detection.get("bbox_xyxy") or {}',
            'bbox = detection.get("bbox") or detection.get("bbox_xyxy") or normalized.get("bbox") or {}',
        ),
        (
            'mask_area = _to_float(detection.get("mask_area_px2"))',
            'mask_area = _to_float(detection.get("mask_area_px2"))\n'
            '                    if mask_area is None:\n'
            '                        mask_area = _to_float(normalized.get("mask_area_px2"))',
        ),
    ),
    (
        "edge-weighvision-session/src/services/sessionService.ts",
        (
            'where: { tenantId_eventId: { tenantId, eventId } },\n'
            '      create: {\n'
            '        sessionId,\n'
            '        tenantId,\n'
            '        mediaObjectId,',
            'where: { sessionId_mediaObjectId: { sessionId, mediaObjectId } },\n'
            '      create: {\n'
            '        sessionId,\n'
            '        tenantId,\n'
            '        mediaObjectId,',
        ),
    ),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edge_root", type=Path)
    args = parser.parse_args()
    root = args.edge_root.resolve()
    assert (root / "docker-compose.yml").is_file(), f"Not an Edge checkout: {root}"
    pending = []
    for relative, *changes in PATCHES:
        path = root / relative
        original = path.read_text(encoding="utf-8")
        updated = original
        for before, after in changes:
            if after in updated:
                continue
            if updated.count(before) != 1:
                raise RuntimeError(f"Unexpected source at {path}: expected one matching snippet")
            updated = updated.replace(before, after, 1)
        pending.append((path, original, updated))
    for path, original, updated in pending:
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print(f"PATCHED {path}")
        else:
            print(f"ALREADY_APPLIED {path}")


if __name__ == "__main__":
    main()
