# Football Rotation Manager

A Streamlit app for managing football team rotation when there are more active players than match-day spots.

The coach manually selects the starting XI. The app recommends 4 substitutes from the remaining available players using a fairness score and simple position-balance rules.

## Version 1 Security

This app is designed for a public GitHub repository.

- Real secrets are not committed.
- Real local database files are not committed.
- Google login uses Streamlit OIDC.
- Only approved coach emails can enter the app.
- Local development can use SQLite.
- Streamlit Community Cloud should use Supabase Postgres through Streamlit secrets.

Streamlit references:

- Secrets: https://docs.streamlit.io/develop/concepts/connections/secrets-management
- Login/OIDC: https://docs.streamlit.io/develop/concepts/connections/authentication
- `st.login`: https://docs.streamlit.io/develop/api-reference/user/st.login
- `st.user`: https://docs.streamlit.io/develop/api-reference/user/st.user

Supabase reference:

- Connection strings: https://supabase.com/docs/reference/postgres/connection-strings

## Project Structure

```text
football_rotation_app/
|-- app.py
|-- requirements.txt
|-- README.md
|-- supabase_schema.sql
|-- .streamlit/
|   `-- secrets.example.toml
|-- data/
|   `-- football.db
`-- src/
    |-- auth.py
    |-- database.py
    |-- fairness.py
    `-- utils.py
```

`data/football.db` is generated locally and ignored by Git.

## Features

- Add, edit, delete, and deactivate players.
- Add players with `Unassigned` positions until coaches fill them in.
- Create matches with date, opponent, and venue.
- Mark match availability for active players.
- Manually select exactly 11 starters.
- Recommend substitutes using fairness and position balance.
- Save match selections without overwriting match history.
- Enter post-match minutes and update player statistics.
- Track games, starts, subs, minutes, last played date, and consecutive sit-outs.
- Dashboard with player table and basic charts.

## Fairness Score

```text
fairness_score =
    (max_games_played - games_played) * 3
    + (max_starts - starts) * 2
    + (max_minutes - minutes_played) * 0.02
    + days_since_last_played * 0.2
    + consecutive_sitouts * 4
```

Players with no `last_played` date are treated as high priority.

## Position Balance

The substitute recommendation tries to include:

- At least 1 defender: `Goalkeeper`, `Centre Back`, `Left Back`, `Right Back`, `Left Wing Back`, `Right Wing Back`
- At least 1 midfielder: `Defensive Midfielder`, `Central Midfielder`, `Attacking Midfielder`, `Left Midfielder`, `Right Midfielder`
- At least 1 attacker: `Left Winger`, `Right Winger`, `Striker`, `Centre Forward`
- The 4th substitute is the highest remaining fairness score

If a group has no eligible available player, the app fills that spot by fairness score.

## Install Dependencies

From inside `football_rotation_app`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you are using the parent folder's existing virtual environment:

```powershell
cd "c:\Users\sgiri14\OneDrive - Charles Sturt University\Python Projects\Football Team App\football_rotation_app"
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure Local Secrets

Create a local secrets file:

```powershell
copy .streamlit\secrets.example.toml .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml`.

For quick local development before Google OAuth is configured:

```toml
approved_coach_emails = ["coach@example.com"]

[security]
allow_dev_bypass = true
dev_user_email = "coach@example.com"
```

Keep `allow_dev_bypass = false` in Streamlit Community Cloud.

## Configure Google Login

Create a Google OAuth client for a web application, then add these redirect URIs:

```text
http://localhost:8501/oauth2callback
https://YOUR-STREAMLIT-APP.streamlit.app/oauth2callback
```

Then set the local or cloud secrets:

```toml
approved_coach_emails = [
  "coach1@example.com",
  "coach2@example.com",
]

[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "replace-with-a-long-random-string"

[auth.google]
client_id = "your-google-client-id"
client_secret = "your-google-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
client_kwargs = { scope = "openid email profile", prompt = "select_account" }
```

For Streamlit Community Cloud, change `redirect_uri` to the deployed app URL:

```toml
[auth]
redirect_uri = "https://YOUR-STREAMLIT-APP.streamlit.app/oauth2callback"
cookie_secret = "replace-with-a-long-random-string"
```

## Configure Supabase

SQLite is fine for local testing. For Streamlit Community Cloud, use Supabase Postgres because local files on the cloud app are not a durable database.

1. Create a Supabase project.
2. Open the SQL editor.
3. Run `supabase_schema.sql`.
4. Open Project Settings, then Database.
5. Copy the session pooler connection string.
6. Add it to Streamlit secrets:

```toml
[database]
url = "postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
```

If Supabase gives you a `postgresql://` URL, this app also normalises it to `postgresql+psycopg://` automatically.

## Run Locally

From inside `football_rotation_app`:

```powershell
streamlit run app.py
```

Open the local URL printed by Streamlit, usually:

```text
http://localhost:8501
```

## Run In Positron

1. Open the `football_rotation_app` folder in Positron.
2. Select the virtual environment interpreter if Positron prompts you.
3. Open a terminal in Positron.
4. Activate the environment.
5. Run:

```powershell
streamlit run app.py
```

## Public Repo Checklist

Before pushing:

```powershell
git status --short
```

Do not commit:

- `.streamlit/secrets.toml`
- `data/*.db`
- Any real Google client secret
- Any real Supabase password

The root `.gitignore` already excludes those files.

## Push To GitHub

From the repository root:

```powershell
git add .
git commit -m "Add secure football rotation app"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/football_rotation_app.git
git push -u origin main
```

If the remote already exists:

```powershell
git add .
git commit -m "Add secure football rotation app"
git push
```

## Deploy To Streamlit Community Cloud

1. Push the project to GitHub.
2. Go to `https://share.streamlit.io/`.
3. Select the repository.
4. Set the main file path to `football_rotation_app/app.py` if this app is in a subfolder.
5. Open Advanced settings.
6. Paste your production secrets.
7. Ensure `allow_dev_bypass = false`.
8. Deploy.

Production secrets should include:

```toml
approved_coach_emails = ["coach@example.com"]

[auth]
redirect_uri = "https://YOUR-STREAMLIT-APP.streamlit.app/oauth2callback"
cookie_secret = "replace-with-a-long-random-string"

[auth.google]
client_id = "your-google-client-id"
client_secret = "your-google-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
client_kwargs = { scope = "openid email profile", prompt = "select_account" }

[database]
url = "postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
```

## Google Sheets Alternative

Google Sheets can work for a very small prototype, but this app uses three related tables and match history. Supabase Postgres is the better V1 deployment choice because it preserves relational constraints and avoids spreadsheet race conditions.
