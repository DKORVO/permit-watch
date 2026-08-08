# MERX: Ottawa and Gatineau opportunities

This update adds two public MERX searches to Permit Watch automatically:

* Ottawa opportunities
* Gatineau opportunities

They appear together on the MERX page. Upload these files into their matching
existing GitHub locations:

* `app/scraper.py`
* `app/views.py`
* `app/templates/index.html`
* `app/static/app.css`
* `sources.example.json`

The MERX sources are added automatically at runtime, so no manual edit of
`/data/sources.json` is required.
