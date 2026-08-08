# Install the Ottawa detail-address update

This update resolves missing Ottawa addresses through the City's public per-application detail endpoint.

- It requests only applications whose address is missing.
- It resolves at most 25 applications each time **Run now** is selected.
- It waits half a second between detail requests.
- It does not use OpenRouter or consume AI requests.

## Install

1. Unzip this package.
2. Open https://github.com/DKORVO/permit-watch.
3. Select **Add file**, then **Upload files**.
4. Drag in the included `app` folder and select **Commit changes**.
5. Wait for the GitHub Actions build to show a green check mark.
6. In TrueNAS, open Permit Watch, select **Edit**, then **Save**. Keep `pull_policy: always` in the YAML.
7. When the app returns to Running, select **Run now** once.

The app remembers resolved addresses, so each subsequent run progresses to the next group of up to 25 missing addresses instead of repeating the first group.
