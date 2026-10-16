import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FANQIE = load('fanqie_refresh')
QIMAO = load('collect_qimao_web_ranks')


class FakePage:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class RequiredCollectorRetryTests(unittest.TestCase):
    def test_fanqie_retries_connection_close_with_fresh_pages(self):
        pages = []
        calls = []

        def page_factory():
            page = FakePage()
            pages.append(page)
            return page

        def collector(page, rank, output_dir, config, decoder):
            calls.append(page)
            if len(calls) < 3:
                raise ConnectionError('net connection closed')
            return {'gender': rank[2], 'rank_type': rank[3], 'status': 'success', 'valid_book_count': 10, 'errors': []}

        config = dict(FANQIE.DEFAULT_CONFIG)
        config.update({'rank_attempts': 3, 'retry_backoff_seconds': 0})
        result = FANQIE.collect_rank_with_retries(
            page_factory, FANQIE.RANKS[2], ROOT / 'tests' / 'fixtures' / 'unused-output',
            config, lambda value: value, collector=collector, sleeper=lambda _: None,
        )
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['attempt_count'], 3)
        self.assertEqual(len({id(page) for page in pages}), 3)
        self.assertTrue(all(page.closed for page in pages))

    def test_qimao_retries_before_accepting_channel(self):
        calls = []
        quote = chr(34)
        page = f'<a href={quote}/shuku/123/{quote}>Test Book</a>'

        def fetcher(url, timeout):
            calls.append((url, timeout))
            if len(calls) == 1:
                raise ConnectionError('connection reset')
            return page, {'http_status': 200, 'response_bytes': len(page)}

        rows, transport = QIMAO.fetch_and_parse_with_retries(
            gender='male', rank_type='hot', source_url='https://www.qimao.com/paihang/boy/hot/date/',
            timeout=1, attempts=3, retry_backoff=0, fetcher=fetcher, sleeper=lambda _: None,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(transport['attempt_count'], 2)
        self.assertEqual(len(transport['retry_errors']), 1)


class RuntimeContractTests(unittest.TestCase):
    def test_model_facing_skills_are_split_and_light(self):
        router = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        scan = (ROOT.parent / 'novel-market-scan' / 'SKILL.md').read_text(encoding='utf-8')
        candidate = (ROOT.parent / 'novel-candidate-portfolio' / 'SKILL.md').read_text(encoding='utf-8')
        self.assertLess(len(router.splitlines()), 80)
        self.assertLess(len(scan.splitlines()), 100)
        self.assertLess(len(candidate.splitlines()), 120)
        self.assertIn('novel-market-scan', router)
        self.assertIn('novel-candidate-portfolio', router)
        self.assertIn('Never claim that other lists are sufficient', scan)
        self.assertIn('novel-candidate-portfolio/scripts/candidate.py', router)
        self.assertIn('four count fields', router)

    def test_candidate_skill_matches_runtime_recovery_contract(self):
        skill_root = ROOT.parent / 'novel-candidate-portfolio'
        candidate = (skill_root / 'SKILL.md').read_text(encoding='utf-8')
        operations = (skill_root / 'references' / 'operations.md').read_text(encoding='utf-8')
        self.assertIn('128-call recovery budget', candidate)
        self.assertNotIn('four-call recovery budget', candidate)
        self.assertNotIn('eight-call recovery budget', candidate)
        self.assertNotIn('The 4-call recovery budget', operations)
        self.assertIn('targeted kernel supplements', operations)

    def test_registry_keeps_required_source_failure_policy(self):
        registry = json.loads((ROOT / 'references' / 'source-registry.json').read_text(encoding='utf-8'))
        policy = registry['required_source_failure_policy']
        self.assertEqual(policy['transient_attempts'], 3)
        self.assertEqual(policy['on_exhaustion'], 'degraded_and_formal_gate_closed')
        self.assertTrue(policy['substitution_forbidden'])


if __name__ == '__main__':
    unittest.main()
