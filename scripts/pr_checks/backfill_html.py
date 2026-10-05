"""List or dispatch HTML reviews for existing open PRs, including forks."""
import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen


def github_api(method, path, body=None):
    request = Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}".rstrip('/'),
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'},
        method=method)
    with urlopen(request, timeout=60) as response:
        data = response.read()
        return json.loads(data) if data else None


def parse_numbers(value):
    if not value.strip():
        return None
    parts = re.split(r'[\s,]+', value.strip())
    if not all(re.fullmatch(r'[1-9][0-9]*', part) for part in parts):
        raise ValueError('Expected positive PR numbers separated by commas or spaces')
    return {int(part) for part in parts}


def backfill(api, numbers=None, dispatch=False):
    repository = api('GET', '')
    open_numbers = set()
    page = 1
    while True:
        prs = api('GET', f'pulls?state=open&per_page=100&page={page}')
        open_numbers.update(pr['number'] for pr in prs if pr['state'] == 'open')
        if len(prs) < 100:
            break
        page += 1
    if numbers is not None and numbers - open_numbers:
        raise ValueError('These PRs are not open: ' + ', '.join(map(str, sorted(numbers - open_numbers))))
    selected = sorted(open_numbers if numbers is None else numbers)
    for number in selected:
        if dispatch:
            api('POST', 'actions/workflows/html-review.yml/dispatches',
                {'ref': repository['default_branch'], 'inputs': {'pr_number': str(number)}})
        print(f"{'Queued' if dispatch else 'Would queue'} HTML review for PR #{number}", flush=True)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prs', default=os.environ.get('PR_NUMBERS', ''),
                        help='Comma-separated PR numbers; empty selects every open PR')
    parser.add_argument('--dispatch', action='store_true', help='Queue builds instead of just listing PRs')
    args = parser.parse_args()
    numbers = backfill(github_api, parse_numbers(args.prs), args.dispatch)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write(f"{'Queued' if args.dispatch else 'Selected'} {len(numbers)} HTML reviews: "
                         + ', '.join(f'#{number}' for number in numbers) + '\n')


if __name__ == '__main__':
    main()
