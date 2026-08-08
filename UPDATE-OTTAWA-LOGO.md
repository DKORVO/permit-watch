# Permit Watch: City of Ottawa header

This update adds the supplied City of Ottawa logo and the words **City of
Ottawa** to the Permit Watch dashboard header.

The logo is kept in the persistent TrueNAS folder:

`/mnt/tank/apps/permit-watch/assets/ottawa-logo.png`

You can replace that image later with `ottawa-logo.png`, `ottawa-logo.svg`, or
`ottawa-logo.webp`, then refresh the dashboard. No rebuild is required for a
logo replacement.

## GitHub installation

Upload each item to the matching existing location in your repository:

* `app/views.py`
* `app/templates/index.html`
* `app/static/app.css`
* `app/assets/ottawa-logo.png`
* `deploy/entrypoint.sh`

Do not upload these files to the repository root. Wait for the GitHub Action
to finish, make a new release tag, and deploy that tag in TrueNAS.
