# plan-site-ui standing rules

- Anything that writes goes through the plan service's write API as the signed-in viewer (basstler-service/site-actions), never a token in the browser.
- Request text is parsed into a pydantic model at the boundary and never interpolated into a shell or workflow expression.
- A button that changes the site shows its result live on the page, or the reason it was refused (basstler-service/live-pages).
- Promotability is one rule shared with the stack's promotion order; the site never decides it separately.
- A link that leaves the site (a pull request, branch, issue or GitHub page) opens in a new tab with `target="_blank" rel="noopener"`; links between the site's own pages stay in the same tab.
