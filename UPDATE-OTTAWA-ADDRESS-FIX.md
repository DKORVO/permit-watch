# Install the Ottawa address fix

This update prevents internal Ottawa values like `__CZYWDM` from appearing as addresses. Existing records are refreshed during the next scrape; clearing the database is not required.

1. Unzip this package.
2. Open https://github.com/DKORVO/permit-watch.
3. Select **Add file** then **Upload files**.
4. Drag in the included `app` folder and select **Commit changes**.
5. Wait for the GitHub Actions build to finish with a green check mark.
6. In TrueNAS, open Permit Watch, select **Edit**, then **Save**. Keep `pull_policy: always` in the YAML.
7. When the app is running, select **Run now** once.

The next scrape updates matching saved entries with corrected public source fields.
