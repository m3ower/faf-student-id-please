"""Check cache overlay isolation and preservation using synthetic Compose configuration."""
import copy
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile


def validate():
    root = Path(__file__).resolve().parents[1]
    base = ['docker-compose.yml', 'docker-compose.owned-broker.yml', 'docker-compose.owned-cache.yml']
    variants = [base, base + ['docker-compose.warehouse.yml', 'docker-compose.cache.yml']]
    overlay = 'docker-compose.owned-cache-sharding.yml'
    # An explicitly supplied candidate HA overlay is read only; never fetched or activated.
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ha-overlay', type=Path)
    args = parser.parse_args()
    if args.ha_overlay:
        variants.append(variants[-1] + [str(args.ha_overlay.resolve())])
    files = {f for v in variants for f in v} | {overlay}
    env = os.environ.copy()
    for filename in files:
        for key in re.findall(r'\$\{([A-Z][A-Z0-9_]*):\?', (root / filename).read_text(encoding='utf-8')):
            env[key] = ('example.invalid/test:' + key.lower()) if key.endswith('_IMAGE') else secrets.token_urlsafe(32)
    env['CACHE_APPLICANT_IMAGE'] = 'example.invalid/applicant:1.6.0'
    env['CACHE_RECORD_IMAGE'] = 'example.invalid/record:1.6.0'
    env['SHARDED_APPLICANT_IMAGE'] = 'example.invalid/applicant:1.7.0'
    env['SHARDED_RECORD_IMAGE'] = 'example.invalid/record:1.7.0'
    env['OWNED_CACHE_VIRTUAL_NODES'] = '128'
    checks = 0
    with tempfile.TemporaryDirectory(prefix='owned-cache-compose-') as temp:
        empty = Path(temp) / 'empty.env'; empty.write_text('', encoding='utf-8')
        def resolve(files):
            command = ['docker', 'compose', '--project-directory', str(root), '--env-file', str(empty)]
            for f in files: command += ['-f', str(root / f)]
            command += ['config', '--format', 'json']
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            if result.returncode: raise RuntimeError('Synthetic Compose validation failed; resolved values withheld')
            return json.loads(result.stdout)
        for files in variants:
            files=[f for f in files if f!='docker-compose.owned-cache.yml']+['docker-compose.owned-cache.yml']
            before = resolve(files); after = resolve(files + [overlay])
            owned = {'applicant-service': ('applicant-read-cache', 'applicant-net', 'SHARDED_APPLICANT_IMAGE'),
                     'applicant-service-2': ('applicant-read-cache', 'applicant-net', 'SHARDED_APPLICANT_IMAGE'),
                     'university-record-service': ('record-read-cache', 'record-net', 'SHARDED_RECORD_IMAGE'),
                     'university-record-service-2': ('record-read-cache', 'record-net', 'SHARDED_RECORD_IMAGE')}
            assert set(after['services']) - set(before['services']) == {'applicant-read-cache-b', 'applicant-read-cache-c', 'record-read-cache-b', 'record-read-cache-c'}
            for name, service in before['services'].items():
                actual = copy.deepcopy(after['services'][name])
                if name in owned:
                    cache, network, image = owned[name]
                    assert actual['image'] == env[image]
                    assert actual['environment']['CACHE_ENABLED'] == 'true'
                    address = 'CACHE_REDIS_HOST' if cache.startswith('applicant') else 'CACHE_REDIS_ADDR'
                    assert actual['environment'][address] == cache + ('' if cache.startswith('applicant') else ':6379')
                    assert cache not in actual.get('depends_on', {})
                    assert actual['environment']['CACHE_REDIS_NODES'] == 'a='+cache+':6379,b='+cache+'-b:6379,c='+cache+'-c:6379'
                    assert actual['environment']['CACHE_VIRTUAL_NODES'] == '128'
                    for key in ('CACHE_REDIS_NODES', 'CACHE_VIRTUAL_NODES'): actual['environment'].pop(key)
                    actual['image'] = service['image']
                assert actual == service, 'Overlay changed unrelated configuration for ' + name
                checks += 1
            for name, network in [(owner+'-read-cache'+suffix, owner+'-net') for owner in ('applicant','record') for suffix in ('','-b','-c')]:
                cache = after['services'][name]
                assert set(cache['networks']) == {network} and after['networks'][network]['internal']
                assert not cache.get('ports') and len(cache['volumes']) == 1
                assert cache['volumes'][0]['read_only'] and cache['volumes'][0]['type'] == 'bind'
                assert '@sha256:' in cache['image']
                assert cache['entrypoint'] == ['sh', '/owned-cache/start.sh']
                checks += 1
    print('PASS: ' + str(checks) + ' sharded Compose preservation/isolation checks')


if __name__ == '__main__':
    validate()
