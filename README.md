# DUCKS Poker Rating Bot

This bot reads the results posts from the [DUCKS Poker Telegram channel](https://t.me/DUCKS_POKER), keeps a full history of every player's points, and publishes Overall and Monthly leaderboards in a Google Sheet — automatically, every day. See the [design spec](docs/superpowers/specs/2026-08-11-ducks-rating-bot-design.md) for how it works under the hood.

## 1. Google setup (click-by-click)

You need a Google Cloud "service account" — a robot account that the bot uses to write to your Sheet.

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project and name it `ducks-rating`.
3. In the left menu, open **APIs & Services**.
4. Enable the **Google Sheets API**.
5. Enable the **Google Drive API**.
6. Go to **Credentials**.
7. Click **Create credentials** → **Service account**.
8. Give it any name, then click through to finish.
9. Open the service account you just created.
10. Go to the **Keys** tab.
11. Click **Add key** → **Create new key** → choose **JSON**.
12. A JSON file downloads to your computer. Keep it safe — it is the bot's password.
13. Go to [sheets.new](https://sheets.new) to create a new Google Sheet. This will hold the ratings.
14. In the Sheet, click **Share**.
15. Open the JSON file you downloaded and find the field `client_email`. Copy that email address.
16. Paste that email into the Share box and give it **Editor** access.
17. Look at the Sheet's URL in your browser. It looks like `.../d/SOME_LONG_ID/edit`. Copy the `SOME_LONG_ID` part — this is your sheet ID. You will need it below.

## 2. GitHub setup

The bot runs automatically on GitHub, once a day.

1. Create a GitHub repository and push this code to it.
2. In the repository, go to **Settings** → **Secrets and variables** → **Actions**.
3. Click **New repository secret**.
4. Create a secret named `GOOGLE_CREDENTIALS`. For its value, paste the **full contents** of the JSON file you downloaded in step 1.
5. Click **New repository secret** again.
6. Create a secret named `SHEET_ID`. For its value, paste the sheet ID you copied in step 1.

## 3. Local run (backfill)

The first run has to read the whole channel history, so it's best to do it once on your own computer before turning on the daily automation.

1. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
2. Put the JSON file from step 1 next to the code, and name it `service_account.json`. (This file is never uploaded to GitHub — it's excluded on purpose.)
3. In PowerShell, run:
   ```
   $env:SHEET_ID = "<id>"; python -m src.main
   ```
   Replace `<id>` with your sheet ID.
4. The first run walks the whole channel history, so it can take a few minutes. Let it finish.

## 4. Daily operation

Once the GitHub secrets are set up, the bot keeps itself running.

- Open the **Actions** tab in your GitHub repository. You'll see the **Update ratings** workflow there.
- It runs automatically every day at 08:00 UTC.
- A green check mark means the Sheet was updated successfully.
- A red ❌ means something went wrong — click into the run to see the log.
- You can also update it manually any time: open the workflow and click **Run workflow**.

## 5. Fixing names

Sometimes the same player's name is typed slightly differently between posts. Use the **Aliases** tab in the Sheet to fix this.

- Add a row with the name as it was written, and the real player's name next to it.
- This takes effect on the next run, and it fixes the player's history retroactively — you don't need to touch old rows.
- The **Needs review** tab lists anything the bot wants a human to double-check, such as posts it couldn't parse or names it merged automatically.
