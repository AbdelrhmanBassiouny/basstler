PR #75, item stack-maintenance/dashboard-token-economy.

Plan
- plan_page writes page + dashboard.css/.js/-content.html, prints content_digest
- URL cache: per-key mapping (url, content_digest), legacy flat lines still read
- refresh_dashboard.sh --url-cache: reports unchanged + url
- record_url --content-digest; skill: skip on unchanged, publish with files

Done
- branch, draft PR, manifest in progress

Next
- split template into css/body/js parts (tests first)
