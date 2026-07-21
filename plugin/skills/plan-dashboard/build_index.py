#!/usr/bin/env python3
"""Render the master index of every plan from a list of plan summaries.

Generic - takes a list of already-computed plan summaries (see --plans
below) and renders them; it has no idea what a plan actually contains
beyond that. Pair with build_dashboard.py, whose --output JSON summary
gives you the done/total counts to build one of these entries from.

Usage:
    python3 build_index.py --plans /tmp/plans.json --output /tmp/index.html

plans.json shape: a JSON list of objects, each:
    {
        "id": "<plan-id>",
        "title": "...",
        "description": "...",
        "done": <int>,
        "total": <int>,
        "dashboard_url": "<url>" or null   // null if never published yet
    }
"""

import argparse
import json
import sys
from pathlib import Path

from render_common import esc


def render_card(plan):
    total = plan['total']
    done = plan['done']
    pct = (done / total * 100) if total else 0
    complete = total > 0 and done == total

    if plan.get('dashboard_url'):
        open_tag = f'<a class="plan-card{" complete" if complete else ""}" href="{esc(plan["dashboard_url"])}" target="_blank" rel="noopener">'
        close_tag = '</a>'
    else:
        open_tag = f'<div class="plan-card{" complete" if complete else ""}">'
        close_tag = '</div>'

    progress = f'{done} / {total} done' if total else 'no items yet'
    no_dashboard = '' if plan.get('dashboard_url') else '<p class="no-dashboard">Not published yet — run /plan-dashboard on it.</p>'

    return f'''    {open_tag}
      <div class="plan-head">
        <h2 class="plan-title">{esc(plan['title'])}</h2>
        <span class="plan-progress mono">{esc(progress)}</span>
      </div>
      <p class="plan-desc">{esc(plan.get('description', ''))}</p>
      {no_dashboard}
      <div class="bar"><div class="bar-fill" style="width: {pct:.1f}%"></div></div>
    {close_tag}'''


def build(plans):
    if not plans:
        cards_html = '    <p class="empty">No plans found under .claude/personal/plans/*/plan.yaml.</p>'
    else:
        cards_html = '\n'.join(render_card(p) for p in plans)

    template_path = Path(__file__).parent / 'index_template.html'
    template = template_path.read_text()
    return template.replace('{{PLAN_CARDS}}', cards_html)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plans', required=True, help='Path to a JSON list of plan summaries')
    parser.add_argument('--output', required=True, help='Path to write the index HTML to')
    args = parser.parse_args()

    plans = json.loads(Path(args.plans).read_text())
    output = build(plans)
    Path(args.output).write_text(output)


if __name__ == '__main__':
    sys.exit(main())
