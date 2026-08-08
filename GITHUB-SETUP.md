# One-time GitHub setup

This project can publish its own container image automatically. The image name will be:

`ghcr.io/mrkorvo/permit-watch:stable`

## 1. Create the repository

1. Sign in at https://github.com/new.
2. Set **Repository name** to `permit-watch`.
3. Choose **Public**. This makes the container easy for TrueNAS to download. Do not put passwords or API keys in the repository.
4. Leave **Add a README file** unchecked.
5. Select **Create repository**.

## 2. Upload this project

1. On the new empty repository page, select **uploading an existing file**.
2. Drag in the project files and folders, including the hidden `.github` folder.
3. Do **not** upload `outputs`, old ZIP files, `data`, `.env`, or any file containing an OpenRouter key.
4. Select **Commit changes**.

GitHub will immediately start the automatic build. Open the **Actions** tab and wait for **Build and publish Permit Watch** to show a green check mark (usually a few minutes).

## 3. Make the container public

1. On the repository page, open **Packages** and select the `permit-watch` package.
2. Select **Package settings**.
3. Under **Danger Zone**, select **Change visibility**, then make the package **Public**.

Without this one-time setting, TrueNAS would require GitHub credentials to download the image.

## 4. Point TrueNAS to GitHub

In TrueNAS, edit the app YAML and replace it with the contents of `truenas-ghcr.compose.yaml`.

Before saving:

- Confirm `/mnt/tank/apps/permit-watch` uses your real pool name.
- Paste your current OpenRouter key into `OPENROUTER_API_KEY` if you want AI enrichment.

Save. TrueNAS downloads the `stable` image from GitHub automatically.

## Future updates

Make or upload changes to the `main` branch in GitHub. The action republishes `stable`. Then use the app's **Update** option in TrueNAS when it reports an image update. Your `/data` folder, database, and configured sources remain untouched.
