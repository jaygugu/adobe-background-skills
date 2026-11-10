#!/usr/bin/env python3
"""Offline structural checks; not a replacement for Claude or Adobe validation."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def check():
    marketplace = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text())
    assert re.fullmatch(r'[a-z][a-z0-9-]*', marketplace['name'])
    assert marketplace['owner']['name']
    entries = marketplace['plugins']
    assert len(entries) == 1, 'This release contains one plugin'
    for entry in entries:
        plugin = (ROOT / entry['source']).resolve()
        assert plugin.is_relative_to(ROOT) and plugin.is_dir()
        manifest = json.loads((plugin / '.claude-plugin/plugin.json').read_text())
        assert manifest['name'] == entry['name']
        assert re.fullmatch(r'\d+\.\d+\.\d+', manifest['version'])
        assert not (plugin / 'bin').exists(), 'Cowork plugin must not contain bin/'
        skills = list((plugin / 'skills').glob('*/SKILL.md'))
        assert skills, 'No skill found'
        for skill in skills:
            content = skill.read_text(encoding='utf-8')
            assert content.startswith('---\n')
            frontmatter = content.split('---', 2)[1]
            assert re.search(r'^name: [a-z0-9-]+$', frontmatter, re.M)
            assert re.search(r'^description: .+', frontmatter, re.M)
            assert len(content.splitlines()) < 500
            for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', content):
                if not re.match(r'[a-zA-Z]+:', target):
                    assert (skill.parent / target).is_file(), f'Missing skill reference: {target}'
    sys.path.insert(0, str(ROOT / 'worker'))
    from queue_worker import Worker
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        root = Path(directory)
        with Worker(root, simulate=True) as worker:
            for example in sorted((ROOT / 'examples').glob('*.json')):
                job = json.loads(example.read_text(encoding='utf-8'))
                path = root / job['input']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'Simulation fixture only; not an Adobe document.')
                request = root / 'queue' / (job['id'] + '.json')
                request.write_text(json.dumps(job), encoding='utf-8')
            results = worker.drain()
            assert len(results) == 2 and all(r['state'] == 'simulated' for r in results)
    print('Package structure and sample job simulation passed. Adobe and Claude install remain unverified.')


if __name__ == '__main__':
    check()
