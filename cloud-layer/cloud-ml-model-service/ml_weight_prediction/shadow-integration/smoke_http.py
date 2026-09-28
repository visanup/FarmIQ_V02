"""Exercise actual HTTP jobs, XGBoost and PostgreSQL; no accuracy claim."""
import asyncio
import json
import os
import uuid
import httpx
import asyncpg


async def main():
    db = await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        async with httpx.AsyncClient(base_url='http://edge:8000', timeout=10) as client:
            for rejected in (False, True):
                session_id = 'mock-' + str(uuid.uuid4()) + ('-reject' if rejected else '')
                response = await client.post('/api/v1/inference/jobs', json={
                    'tenant_id': 'mock-tenant', 'farm_id': 'mock-farm', 'barn_id': 'mock-barn',
                    'device_id': 'mock-camera', 'session_id': session_id, 'media_id': 'mock-media',
                })
                response.raise_for_status()
                job_id = response.json()['job_id']
                event = None
                for _ in range(100):
                    event = await db.fetchrow('SELECT * FROM allocation_shadow_events WHERE tenant_id=$1 AND session_id=$2', 'mock-tenant', session_id)
                    if event:
                        break
                    await asyncio.sleep(.2)
                assert event, 'Shadow event did not arrive'
                job = (await client.get('/api/v1/inference/jobs/' + job_id)).json()
                assert job['status'] == 'completed', job
                scalar = await db.fetchrow('SELECT * FROM inference_results WHERE id=$1::uuid', job_id)
                assert float(scalar['predicted_weight_kg']) == 1.23
                assert json.loads(scalar['metadata'])['stub_mode'] is False
                payload = json.loads(event['payload_json'])
                assert payload['shadow_only'] and not payload['decision_use_allowed']
                assert not payload['individual_accuracy_validated']
                assert event['delivery_status'] == 'held_shadow'
                expected = 'REJECTED_QUALITY' if rejected else 'WEAK_ALLOCATION'
                assert payload['prediction_status'] == expected, payload
                birds = await db.fetch('SELECT * FROM session_bird_allocations WHERE event_id=$1', event['event_id'])
                assert len(birds) == (0 if rejected else 2)
                if birds:
                    assert abs(sum(b['allocated_weight_g'] for b in birds)-800) < .1
                assert await db.fetchval("SELECT count(*) FROM sync_outbox WHERE session_id=$1 AND event_type='inference.completed'", session_id) == 1
                assert await db.fetchval("SELECT count(*) FROM sync_outbox WHERE event_type='weighvision.group_allocation.completed'") == 0
                print(json.dumps({'session_id': session_id, 'status': expected, 'legacy_kg': 1.23, 'birds': len(birds), 'held_shadow': True}))
    finally:
        await db.close()


asyncio.run(main())
