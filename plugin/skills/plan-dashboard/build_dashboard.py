#!/usr/bin/env python3
"""Render a single plan's dashboard HTML from its manifest + live GitHub data.

Generic, plan-agnostic: every plan-specific value (title, items, tracking
link, ...) comes from the inputs below, never hardcoded here. This is the
deterministic half of /plan-dashboard - the skill (SKILL.md) is responsible
for gathering the inputs (git show on claude/personal-notes, GitHub API
calls) and for the one step this script cannot do itself: calling the
Artifact tool to publish the HTML this script produces.

Usage:
    python3 build_dashboard.py \\
        --plan /tmp/plan.yaml \\
        --roadmap /tmp/roadmap.md \\
        --pr-data /tmp/pr_data.json \\
        --output /tmp/dashboard.html \\
        [--tracking-url "https://github.com/<owner>/<repo>/issues/<n>"]

pr_data.json shape: {"<owner>/<repo>": {"<pr_number>": {"state": "open"|
"closed", "draft": bool, "merged_at": str|null}}} - one entry per PR number
referenced by any item, gathered by the skill via
mcp__github__list_pull_requests (bulk, paginated) before falling back to
mcp__github__pull_request_read for anything outside that page window.

Prints a one-line JSON summary to stdout (status counts, drift count,
ready-to-start/blocker-maybe-cleared item titles) so the calling skill can
report back without re-parsing the HTML it just wrote.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from render_common import esc, markdown_to_html

MAX_LEVEL = 4

LIVE_LABEL = {
    'merged': 'Merged',
    'open_draft': 'Open · Draft',
    'open_ready': 'Open · Ready',
    'closed_unmerged': 'Closed (unmerged)',
    'not_found': 'Not found on GitHub',
    None: 'No PR yet',
}
STATUS_LABEL = {
    'done': 'Done',
    'in_progress': 'In progress',
    'blocked': 'Blocked',
    'deferred': 'Deferred',
    'not_started': 'Not started',
}


class PlanValidationError(Exception):
    """Raised when a plan.yaml fails schema validation - see plans/README.md."""


def validate_plan(plan):
    """Check the same schema rules plan-create is required to produce
    manifests that pass. Collects every problem found rather than stopping
    at the first one, since a broken manifest is itself something the user
    needs the full picture of, not a single symptom."""
    problems = []

    if plan.get('schema_version') != 1:
        problems.append(f"schema_version must be 1, got {plan.get('schema_version')!r}")

    item_ids = []
    for item in plan.get('items', []):
        item_ids.append(item.get('id') or item.get('branch'))
    if len(item_ids) != len(set(item_ids)):
        seen = set()
        duplicates = {i for i in item_ids if i in seen or seen.add(i)}
        problems.append(f"duplicate item id(s): {sorted(duplicates)}")

    track_ids = {t['id'] for t in plan.get('tracks', [])}
    wave_ids = {w['id'] for w in plan.get('waves', [])}
    item_id_set = set(item_ids)

    for item in plan.get('items', []):
        item_id = item.get('id') or item.get('branch')
        if item.get('track') not in track_ids:
            problems.append(f"item {item_id!r} has unknown track {item.get('track')!r}")
        for dep in item.get('depends_on') or []:
            if dep not in item_id_set:
                problems.append(f"item {item_id!r} depends_on unknown id {dep!r}")

    for track in plan.get('tracks', []):
        if track.get('wave') not in wave_ids:
            problems.append(f"track {track['id']!r} has unknown wave {track.get('wave')!r}")

    if problems:
        raise PlanValidationError('; '.join(problems))


def live_state_of(item, pr_data, default_repo):
    pr = item.get('pr')
    if pr is None:
        return None
    repo_prs = pr_data.get(item.get('repo') or default_repo, {})
    p = repo_prs.get(str(pr))
    if p is None:
        return 'not_found'
    if p.get('merged_at'):
        return 'merged'
    if p.get('state') == 'closed':
        return 'closed_unmerged'
    if p.get('draft'):
        return 'open_draft'
    return 'open_ready'


def drift_of(item, live):
    pr = item.get('pr')
    status = item['status']
    if live == 'not_found':
        return f"PR #{pr} not found on GitHub"
    if status == 'done' and live in ('open_draft', 'open_ready'):
        return f"marked done, but PR #{pr} is still open"
    if status in ('not_started', 'blocked', 'deferred') and live == 'merged':
        return f"marked {status}, but PR #{pr} is already merged"
    if status in ('in_progress', 'blocked') and live in ('merged', 'closed_unmerged'):
        return f"marked {status}, but PR #{pr} is {live.replace('_', ' ')}"
    return None


def build(plan, roadmap_text, pr_data, tracking_url):
    repo = plan['default_repo']
    items_by_id = {(i.get('id') or i['branch']): i for i in plan['items']}

    counts = {'done': 0, 'in_progress': 0, 'blocked': 0, 'deferred': 0, 'not_started': 0}
    drift_flags = []
    for item in plan['items']:
        live = live_state_of(item, pr_data, repo)
        item['_live'] = live
        item['_drift'] = drift_of(item, live)
        counts[item['status']] += 1
        if item['_drift']:
            drift_flags.append(item)

    def is_effectively_done(item_id):
        item = items_by_id.get(item_id)
        if not item:
            return False
        return item['status'] == 'done' or item['_live'] == 'merged'

    ready_to_start = []
    blocker_maybe_cleared = []
    for item in plan['items']:
        deps = item.get('depends_on') or []
        if item['status'] in ('not_started', 'blocked') and deps and all(is_effectively_done(d) for d in deps):
            ready_to_start.append(item)
        elif (item['status'] == 'blocked' and deps
                and any(is_effectively_done(d) for d in deps)
                and not all(is_effectively_done(d) for d in deps)):
            blocker_maybe_cleared.append(item)

    def dep_chip(dep_id):
        dep = items_by_id.get(dep_id)
        label = dep['title'] if dep else dep_id
        short = dep.get('id', dep_id) if dep else dep_id
        return f'<span class="chip" title="{esc(label)}">{esc(short)}</span>'

    def pr_link(item):
        pr = item.get('pr')
        if pr is None:
            return '<span class="muted">no PR yet</span>'
        item_repo = item.get('repo') or repo
        return f'<a class="pr-link" href="https://github.com/{item_repo}/pull/{pr}" target="_blank" rel="noopener">#{pr}</a>'

    def render_item(item, level, wrap_parent_id):
        live = item['_live']
        live_class = f"live-{live}" if live else "live-none"
        drift_html = f'<div class="drift">⚠ {esc(item["_drift"])}</div>' if item['_drift'] else ''
        session_html = ''
        if item.get('session'):
            session_html = f'<a class="session-link" href="{esc(item["session"])}" target="_blank" rel="noopener">session ↗</a>'
        deps_html = ''
        if item.get('depends_on'):
            deps_html = '<div class="deps"><span class="deps-label">needs</span> ' + ' '.join(dep_chip(d) for d in item['depends_on']) + '</div>'
        blockers_html = ''
        if item.get('blockers'):
            blockers_html = '<div class="blockers">' + ''.join(f'<div class="blocker">▸ {esc(b)}</div>' for b in item['blockers']) + '</div>'
        notes_html = f'<div class="notes">{esc(item.get("notes", "")).strip()}</div>' if item.get('notes') else ''
        wrap_html = ''
        if wrap_parent_id:
            parent = items_by_id.get(wrap_parent_id)
            parent_label = parent['title'] if parent else wrap_parent_id
            wrap_html = f'<div class="wrap-arrow">◄ continues from <span class="mono">{esc(wrap_parent_id)}</span> <span class="wrap-parent-title">({esc(parent_label)})</span></div>'

        return f'''
    <article class="item status-{item['status']} {'has-drift' if item['_drift'] else ''}" style="margin-left: {level * 1.75}rem;">
      {wrap_html}
      <div class="item-row">
        <div class="item-spine"></div>
        <div class="item-body">
          <div class="item-head">
            <h4 class="item-title">{esc(item['title'])}</h4>
            <div class="item-badges">
              <span class="badge status-badge status-{item['status']}">{STATUS_LABEL[item['status']]}</span>
              <span class="badge live-badge {live_class}">{LIVE_LABEL[live]}</span>
            </div>
          </div>
          <div class="item-meta">
            <span class="mono id">{esc(item.get('id', item['branch']))}</span>
            <span class="mono branch">{esc(item['branch'])}</span>
            {pr_link(item)}
            {session_html}
          </div>
          {drift_html}
          {notes_html}
          {deps_html}
          {blockers_html}
        </div>
      </div>
    </article>'''

    def render_track_stack(track_items):
        """Order items into a dependency stack (same-track depends_on only),
        assign an indent level per item capped at MAX_LEVEL, wrapping back
        to level 0 (with a left-edge arrow back to the real parent) past
        the cap."""
        ids_in_track = {(i.get('id') or i['branch']) for i in track_items}
        children_by_parent = {}
        roots = []
        for item in track_items:
            item_id = item.get('id') or item['branch']
            same_track_deps = [d for d in (item.get('depends_on') or []) if d in ids_in_track]
            if same_track_deps:
                children_by_parent.setdefault(same_track_deps[0], []).append(item)
            else:
                roots.append(item)

        html_parts = []

        def walk(item, level, wrap_parent_id):
            item_id = item.get('id') or item['branch']
            next_level = level + 1
            wrap_for_children = None
            if next_level > MAX_LEVEL:
                next_level = 0
                wrap_for_children = item_id
            html_parts.append(render_item(item, level, wrap_parent_id))
            for child in children_by_parent.get(item_id, []):
                walk(child, next_level, wrap_for_children)

        for root in roots:
            walk(root, 0, None)

        return ''.join(html_parts)

    tracks_by_wave = {}
    for t in plan['tracks']:
        tracks_by_wave.setdefault(t['wave'], []).append(t)

    items_by_track = {}
    for i in plan['items']:
        items_by_track.setdefault(i['track'], []).append(i)

    waves_html = []
    for wave in plan['waves']:
        tracks = tracks_by_wave.get(wave['id'], [])
        tracks_html = []
        for track in tracks:
            track_items = items_by_track.get(track['id'], [])
            if not track_items:
                tracks_html.append(f'''
            <section class="track">
              <h3 class="track-title">{esc(track['name'])}</h3>
              <p class="track-empty">{esc(track.get('description', 'No tracked items.'))}</p>
            </section>''')
                continue
            items_html = render_track_stack(track_items)
            tracks_html.append(f'''
        <section class="track">
          <h3 class="track-title">{esc(track['name'])}</h3>
          <div class="item-list">{items_html}</div>
        </section>''')
        waves_html.append(f'''
    <section class="wave" id="wave-{esc(wave['id'])}">
      <div class="wave-eyebrow">{esc(wave['name'])}</div>
      {''.join(tracks_html)}
    </section>''')

    summary_pills = ''.join(
        f'<div class="stat"><span class="stat-num">{counts[k]}</span><span class="stat-label">{STATUS_LABEL[k]}</span></div>'
        for k in ('done', 'in_progress', 'blocked', 'deferred', 'not_started')
    )

    next_sections = []
    if drift_flags:
        rows = ''.join(f'<li><strong>{esc(i["title"])}</strong><br><span class="next-reason">{esc(i["_drift"])}</span></li>' for i in drift_flags)
        next_sections.append(f'<div class="next-group next-drift"><h4>Fix the manifest ({len(drift_flags)})</h4><ul>{rows}</ul></div>')
    if ready_to_start:
        rows = ''.join(f'<li><strong>{esc(i["title"])}</strong><br><span class="next-reason">all dependencies done — nothing structurally blocking it</span></li>' for i in ready_to_start)
        next_sections.append(f'<div class="next-group next-ready"><h4>Ready to start ({len(ready_to_start)})</h4><ul>{rows}</ul></div>')
    if blocker_maybe_cleared:
        rows = ''.join(f'<li><strong>{esc(i["title"])}</strong><br><span class="next-reason">some (not all) dependencies are done — worth re-checking the blocker</span></li>' for i in blocker_maybe_cleared)
        next_sections.append(f'<div class="next-group next-recheck"><h4>Blocker may be cleared ({len(blocker_maybe_cleared)})</h4><ul>{rows}</ul></div>')
    if not next_sections:
        next_sections.append('<p class="next-empty">Nothing actionable right now — every item is either in progress, fully blocked, or done.</p>')
    next_html = ''.join(next_sections)

    if drift_flags:
        rows = ''.join(f'<li>{esc(i["title"])} — {esc(i["_drift"])}</li>' for i in drift_flags)
        alert_html = f'<div class="alert-banner drift-banner"><strong>{len(drift_flags)} drift flag(s)</strong><ul>{rows}</ul></div>'
    else:
        alert_html = '<div class="alert-banner clean-banner">No drift — every item\'s manual status agrees with live GitHub state.</div>'

    tracking_link_html = ''
    if tracking_url:
        tracking_link_html = (
            f' <a class="tracking-link" href="{esc(tracking_url)}" '
            f'target="_blank" rel="noopener">Propose a structural change →</a>'
        )

    template_path = Path(__file__).parent / 'dashboard_template.html'
    template = template_path.read_text()

    output = (template
        .replace('{{TITLE}}', esc(plan['title']))
        .replace('{{DESCRIPTION}}', esc(plan['description']))
        .replace('{{REPO}}', esc(repo))
        .replace('{{TOTAL}}', str(len(plan['items'])))
        .replace('{{TRACKING_PR_LINK}}', tracking_link_html)
        .replace('{{SUMMARY_PILLS}}', summary_pills)
        .replace('{{ALERT_HTML}}', alert_html)
        .replace('{{NEXT_HTML}}', next_html)
        .replace('{{ROADMAP_HTML}}', markdown_to_html(roadmap_text))
        .replace('{{WAVES_HTML}}', ''.join(waves_html))
    )

    summary = {
        'counts': counts,
        'drift_count': len(drift_flags),
        'drift_items': [i['title'] for i in drift_flags],
        'ready_to_start': [i['title'] for i in ready_to_start],
        'blocker_maybe_cleared': [i['title'] for i in blocker_maybe_cleared],
    }
    return output, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--plan', required=True, help='Path to plan.yaml')
    parser.add_argument('--roadmap', required=True, help='Path to roadmap.md')
    parser.add_argument('--pr-data', required=True, help='Path to a JSON file: {"owner/repo": {"pr_number": {...}}}')
    parser.add_argument('--output', required=True, help='Path to write the dashboard HTML to')
    parser.add_argument('--tracking-url', default=None, help="The plan's tracking_issue html_url, if it has one")
    args = parser.parse_args()

    plan = yaml.safe_load(Path(args.plan).read_text())
    roadmap_text = Path(args.roadmap).read_text()
    pr_data = json.loads(Path(args.pr_data).read_text())

    try:
        validate_plan(plan)
    except PlanValidationError as exc:
        print(f"plan.yaml failed validation: {exc}", file=sys.stderr)
        return 1

    output, summary = build(plan, roadmap_text, pr_data, args.tracking_url)

    Path(args.output).write_text(output)
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
