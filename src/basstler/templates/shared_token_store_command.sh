bash -c '
read -rsp "token: " token && echo &&
{% for stored in secrets %}
printf %s "$token" | gh secret set {{ stored.secret }} --repo {{ stored.repository.full_name }}{% if not loop.last %} &&{% endif %}

{% endfor %}
'
