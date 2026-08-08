# Install the Retry Enrichment update

This adds a **Retry enrichment** button to Permit Watch. It retries only findings in **Enrichment Failed** and does not scrape Ottawa again.

## Install

1. Unzip this update package.
2. Open https://github.com/DKORVO/permit-watch.
3. Select **Add file** then **Upload files**.
4. Drag the included `app` folder into the upload area.
5. Select **Commit changes**.
6. Wait for the GitHub Actions build to show a green check.
7. In TrueNAS, open Permit Watch, select **Edit**, and then **Save**. Keep `pull_policy: always` in the YAML so TrueNAS pulls the new image.

After the site restarts, the button appears when there are failed enrichments. One click retries up to 10 items. The current result appears in the **Last run** message.

To change the number of retries later, add this under `environment:` in the TrueNAS YAML:

```yaml
ENRICHMENT_RETRY_LIMIT: "10"
```

Keep the number low when using a free OpenRouter model.
