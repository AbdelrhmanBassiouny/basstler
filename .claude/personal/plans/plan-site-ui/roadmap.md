# plan-site-ui standing rules

- The site stays static: anything that writes goes through an owner-only command issue in the site repository, never a token in the browser.
- Every command issue is closed by its workflow once it has run or refused, with a comment saying which and why.
- Issue text is parsed into a pydantic model at the boundary and never interpolated into a shell or workflow expression.
- A button that changes the site shows that the site is rebuilding until the new build is live.
- Promotability is one rule shared with the stack's promotion order; the site never decides it separately.
