# Permit Watch: show resolved addresses and file-lead phone numbers

This update changes a title such as:

`D07-12-25-0113 — __CZYWDM — Site Plan Control`

to a title using the public Ottawa address once it has been resolved. It also
adds the public **File Lead Phone** field when Ottawa provides it, and updates
the existing card rather than making a duplicate when source details change.

## Install

1. In GitHub, open the `DKORVO/permit-watch` repository.
2. Upload the contents of the `app` folder from this update, replacing files
   when GitHub asks.
3. Commit the upload and wait for **Actions** to show a green check mark.
4. In TrueNAS, open **Apps** > **Installed** > **Permit Watch** > **Edit**,
   then select **Save**. Your existing database and settings stay in place.

The background address resolver will correct the older titles as it works
through the saved records. The dashboard's Ottawa address counter shows its
progress.
