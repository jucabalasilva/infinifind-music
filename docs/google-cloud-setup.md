# Setting up Google access (sign in with YouTube)

InfiniFind Music can read your YouTube playlists directly after you sign in with your Google
account. For that, the app needs an **OAuth client ID** from Google Cloud.

> **Coming later:** released builds will include a client ID verified by Google, so regular users
> won't need any of this. Until then, each person who runs the app from source creates their own
> (free, about 15 minutes, done once).

Google renames menu items from time to time; if a label below is different, look for the closest
one.

## 1. Create a project

1. Go to <https://console.cloud.google.com/> and sign in with the Google account you use on YouTube.
2. Click the project picker at the top → **New project**.
3. Name it `InfiniFind Music` and click **Create**. Make sure it's selected afterwards.

## 2. Turn on the YouTube Data API

1. Menu ☰ → **APIs & Services** → **Library**.
2. Search for **YouTube Data API v3**, open it and click **Enable**.

## 3. Describe the app (consent screen)

1. Menu ☰ → **Google Auth Platform** (or **APIs & Services → OAuth consent screen**) → **Get started**.
2. **App name:** `InfiniFind Music`. **User support email:** your email.
3. **Audience:** **External**.
4. **Contact information:** your email. Accept the policy and click **Create**.

## 4. Allow only the read-only YouTube permission

1. In **Google Auth Platform**, open **Data access** → **Add or remove scopes**.
2. Tick **`.../auth/youtube.readonly`** ("View your YouTube account") and save.
   Don't add any other scope: the app only needs to read playlists.

## 5. Add yourself as a test user

While the app is in **Testing**, only listed accounts can sign in (up to 100).

1. Open **Audience** → **Test users** → **Add users**.
2. Add the Google account(s) that will use the app and save.

Note: in Testing, Google ends the sign-in after **7 days**; just sign in again when the app asks.

## 6. Create the client ID

1. Open **Clients** → **Create client**.
2. **Application type:** **Desktop app**. Name: `InfiniFind Music desktop`.
3. Click **Create**, then **Download JSON**. The file is named like `client_secret_….json`.

## 7. Give the file to the app

1. Open InfiniFind Music. In the **YouTube account** panel, click **Set up Google access…**
   and choose the downloaded `.json` file.
2. Click **Sign in with Google**. Your browser opens Google's consent page. Because the app is
   in Testing, Google shows a "Google hasn't verified this app" notice: click **Continue**.
3. Allow **"View your YouTube account"**. The browser shows "Signed in" and the app updates.

The app keeps its copy of the file in its app-data folder (readable only by you) and never
uploads it anywhere. You can delete the downloaded copy afterwards. Never commit it to Git
(`.gitignore` already blocks `client_secret*.json` and `google_client.json`).

## What the app can and cannot do with this access

- **Can:** read your channel name and your playlists and the videos in them.
- **Cannot:** create, change or delete anything, see your watch history, or read your
  YouTube Music library (songs and albums you added) — the API doesn't expose it, so keep using
  the Google Takeout export for the library.
- **Sign out** in the app revokes the access at Google. You can also remove it at
  <https://myaccount.google.com/permissions>.
