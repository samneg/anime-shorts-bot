# Deploying to Render.com (100% Free - $0/month)

## Step 1: Push Workspace Files to Your GitHub Repository
Push these 5 files to your new GitHub repository:
* `Dockerfile`
* `requirements.txt`
* `app.py`
* `telegram_bot.py`
* `anime_agent.py`

---

## Step 2: Create Free Web Service on Render
1. Go to [dashboard.render.com](https://dashboard.render.com/) and click **New +** → **Web Service**.
2. Select **Build and deploy from a Git repository** → click **Next**.
3. Select your GitHub repository that you just connected.
4. Set the configuration:
   * **Name:** `anime-shorts-bot`
   * **Region:** Any (e.g. Frankfurt, Oregon, Singapore)
   * **Runtime:** Select **Docker**
   * **Instance Type:** Select **Free ($0/month)**
5. Scroll down to **Environment Variables** → click **Add Environment Variable**:
   * **Key:** `TELEGRAM_BOT_TOKEN`
   * **Value:** `9090036197:AAGaLKi9cSggbOkhopPBveFm7n7H0eiCAH0`
6. Click **Deploy Web Service**!

Render will build the Docker container with FFmpeg, start `app.py`, and your bot will be running 24/7 in the cloud with zero PC required!
