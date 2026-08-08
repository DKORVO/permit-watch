# Automatic Ottawa address backfill

This update automatically resolves missing Ottawa addresses from the public application-detail service.

- Starts about one minute after Permit Watch starts.
- Resolves up to 25 addresses every 10 minutes.
- Waits half a second between City requests.
- Shows `resolved` and `remaining` address counts on the dashboard.
- Does not use OpenRouter or consume AI requests.

## Install

1. Unzip this package.
2. Open https://github.com/DKORVO/permit-watch.
3. Select **Add file**, then **Upload files**.
4. Drag in the included `app` folder and select **Commit changes**.
5. Wait for the GitHub Actions build to finish with a green check mark.
6. In TrueNAS, open Permit Watch, select **Edit**, then **Save**.

The existing TrueNAS configuration works without changes. If you want to change its pace later, add the following under `environment:` in the TrueNAS YAML:

```yaml
ADDRESS_RESOLUTION_INTERVAL_MINUTES: "10"
ADDRESS_RESOLUTION_BATCH_SIZE: "25"
```

Keep the default values unless you have a specific need to slow it down.
