# Paste v4 UI files

Replace these mobile files with the matching files from `nexgene-ui-v4-github-2.zip` (or the agent `V4_*` artifacts):

1. `mobile/index.html` ← full v4 shell (must include `overview-stats`, `checkin-form`, `data-timeline`, `patterns-body`, `research-weekly`)
2. `mobile/styles.css` ← night field notebook v4
3. `mobile/fx.js` ← helix canvas
4. `mobile/app.core.js` ← already on main if size ~26KB
5. `mobile/app.js` ← thin loader of `/static/app.core.js` (already on main)

Do not use the classic `tabLogin` / `email` / `password` markup with app.core.js.
