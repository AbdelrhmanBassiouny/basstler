bash -c '
read -rsp "{{ token_secret }}: " token && echo &&
{{ token_variable }}="$token" gh workflow run {{ site_workflow_name }} {{ repository_option }} {{ site_repository }} &&
for repository in {{ repositories }}; do
  printf %s "$token" | gh secret set {{ token_secret }} {{ repository_option }} "$repository"
done'
