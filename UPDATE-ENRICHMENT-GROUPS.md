# Install the dashboard grouping update

This update separates the dashboard into:

1. Awaiting Enrichment
2. Enriched
3. Enrichment Failed

## Upload to GitHub

1. Unzip this update package.
2. Open https://github.com/DKORVO/permit-watch.
3. Select **Add file**, then **Upload files**.
4. Drag the included `app` folder into the upload area.
5. Select **Commit changes**.

GitHub Actions will rebuild the container. Once the action has a green check mark, select **Update** for Permit Watch in TrueNAS.

Existing saved findings are automatically sorted into the correct category when the updated app starts. New findings are categorized as they are collected.
