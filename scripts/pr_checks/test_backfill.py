from contextlib import redirect_stdout
from io import BytesIO, StringIO
import unittest
from unittest.mock import patch

from backfill_html import backfill, github_api, parse_numbers


class BackfillTests(unittest.TestCase):
    def setUp(self):
        self.pages = [[dict(number=47, state='open', draft=False),
                       dict(number=48, state='open', draft=True)]]
        self.writes = []

    def api(self, method, path, body=None):
        if method == 'POST':
            self.writes.append((path, body))
            return None
        if path == '':
            return {'default_branch': 'trunk'}
        page = int(path.rsplit('=', 1)[1])
        return self.pages[page - 1]

    def run_backfill(self, **kwargs):
        with redirect_stdout(StringIO()):
            return backfill(self.api, **kwargs)

    def test_all_open_prs_are_dispatched_from_the_default_branch(self):
        self.assertEqual(self.run_backfill(dispatch=True), [47, 48])
        self.assertEqual(self.writes, [
            ('actions/workflows/html-review.yml/dispatches',
             {'ref': 'trunk', 'inputs': {'pr_number': str(number)}}) for number in (47, 48)])

    def test_selection_is_validated_before_any_build_is_queued(self):
        with self.assertRaises(ValueError):
            self.run_backfill(numbers={47, 999}, dispatch=True)
        self.assertEqual(self.writes, [])

    def test_selected_prs_only(self):
        self.run_backfill(numbers={48}, dispatch=True)
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0][1]['inputs'], {'pr_number': '48'})

    def test_default_is_read_only(self):
        self.assertEqual(self.run_backfill(), [47, 48])
        self.assertEqual(self.writes, [])

    def test_all_pages_are_included_without_duplicate_dispatches(self):
        self.pages = [[dict(number=n, state='open') for n in range(1, 101)],
                      [dict(number=100, state='open'), dict(number=101, state='open')]]
        self.assertEqual(self.run_backfill(dispatch=True), list(range(1, 102)))
        self.assertEqual(len(self.writes), 101)

    def test_closed_prs_are_not_dispatched(self):
        self.pages[0][0]['state'] = 'closed'
        self.assertEqual(self.run_backfill(dispatch=True), [48])

    def test_empty_repository_queues_nothing(self):
        self.pages = [[]]
        self.assertEqual(self.run_backfill(dispatch=True), [])
        self.assertEqual(self.writes, [])

    def test_parse_selection(self):
        self.assertIsNone(parse_numbers(' '))
        self.assertEqual(parse_numbers('47, 48 47'), {47, 48})
        self.assertEqual(parse_numbers('47,,48'), {47, 48})
        for value in ('0', '-1', '47,invalid'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_numbers(value)

    def test_dispatch_handles_github_empty_204_response(self):
        with patch.dict('os.environ', {'GITHUB_REPOSITORY': 'course/material', 'GITHUB_TOKEN': 'test'}), \
                patch('backfill_html.urlopen', return_value=BytesIO(b'')) as request:
            self.assertIsNone(github_api('POST', 'actions/workflows/html-review.yml/dispatches',
                                        {'ref': 'main', 'inputs': {'pr_number': '47'}}))
        self.assertEqual(request.call_args.args[0].method, 'POST')


if __name__ == '__main__':
    unittest.main()
