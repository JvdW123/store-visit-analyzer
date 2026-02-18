# Password Protection Setup Guide

The Store Visit Analyzer now includes password protection that runs **before any content is shown**.

## 🔒 How It Works

1. **Password protection is the FIRST thing that runs** - before any data or UI is displayed
2. If `APP_PASSWORD` is set in secrets, users must enter the password to access the app
3. If `APP_PASSWORD` is not set, the app runs without protection (useful for local development)
4. Once authenticated, the session remains active until the browser is closed

---

## 🏠 Local Development Setup

### Option 1: No Password (Easiest for Development)

1. Copy the example file:
   ```bash
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```

2. Edit `.streamlit\secrets.toml` and **comment out** the `APP_PASSWORD` line:
   ```toml
   # APP_PASSWORD = "change-me-to-secure-password"  # Commented out = no password
   
   ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-key"
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```

The app will load directly without asking for a password.

### Option 2: Simple Password for Local Testing

1. Copy the example file:
   ```bash
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```

2. Edit `.streamlit\secrets.toml`:
   ```toml
   APP_PASSWORD = "dev"  # Simple password for testing
   
   ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-key"
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```

You'll be prompted to enter "dev" as the password.

---

## ☁️ Streamlit Cloud Deployment

### Step 1: Deploy Your App

1. Push your code to GitHub (secrets.toml is already in .gitignore)
2. Go to https://share.streamlit.io
3. Click "New app" and select your repository
4. Deploy the app

### Step 2: Add Secrets

1. In Streamlit Cloud, go to your app dashboard
2. Click on your app → **"Settings"** → **"Secrets"**
3. Add your secrets in TOML format:

```toml
APP_PASSWORD = "YourSecureProductionPassword123!"
ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-anthropic-key"
```

4. Click **"Save"**
5. The app will automatically restart

### Step 3: Share with Colleagues

Send them:
- The app URL (e.g., `https://your-app.streamlit.app`)
- The password (via secure channel - email, Slack DM, etc.)

---

## 🔐 Security Best Practices

### Password Requirements

For production, use a **strong password**:
- ✅ At least 12 characters
- ✅ Mix of uppercase, lowercase, numbers, symbols
- ✅ Not a dictionary word
- ✅ Unique to this application

**Good examples:**
- `StoreVisit2026!Analytics`
- `DataClean#Secure789`
- `Shelf@Analysis2026!`

**Bad examples:**
- ❌ `password`
- ❌ `123456`
- ❌ `admin`

### Sharing the Password

- ✅ **DO**: Share via secure channels (encrypted email, password manager, Slack DM)
- ✅ **DO**: Change the password if someone leaves the team
- ✅ **DO**: Use different passwords for different environments (dev/staging/prod)
- ❌ **DON'T**: Put the password in emails subject lines
- ❌ **DON'T**: Share in public Slack channels
- ❌ **DON'T**: Write it down where others can see

### Rotating Passwords

To change the password:

**Streamlit Cloud:**
1. Go to app settings → Secrets
2. Update the `APP_PASSWORD` value
3. Save (app will restart)
4. Notify your colleagues of the new password

**Local:**
1. Edit `.streamlit\secrets.toml`
2. Change `APP_PASSWORD = "new-password"`
3. Restart the app

---

## 🧪 Testing Password Protection

### Test 1: With Password Protection

1. Create `.streamlit\secrets.toml` with:
   ```toml
   APP_PASSWORD = "test123"
   ANTHROPIC_API_KEY = "sk-ant-api03-..."
   ```

2. Run: `streamlit run app.py`

3. **Expected behavior:**
   - Login screen appears immediately
   - No other content is visible
   - Entering wrong password shows error
   - Entering "test123" grants access
   - After login, full app is visible

### Test 2: Without Password Protection

1. Edit `.streamlit\secrets.toml`:
   ```toml
   # APP_PASSWORD = "test123"  # Commented out
   ANTHROPIC_API_KEY = "sk-ant-api03-..."
   ```

2. Run: `streamlit run app.py`

3. **Expected behavior:**
   - App loads directly
   - No login screen
   - Full functionality available immediately

---

## ❓ Troubleshooting

### Problem: "Password incorrect" but I'm sure it's right

**Solution:** Check for:
- Extra spaces before/after the password in secrets.toml
- Wrong quotes (use straight quotes `"` not curly quotes `"`)
- Case sensitivity (passwords are case-sensitive)

### Problem: App shows content before asking for password

**Solution:** This shouldn't happen! The password check is at the very top of app.py. If you see content before login, check:
1. Is `APP_PASSWORD` actually set in secrets?
2. Did you restart the app after changing secrets?
3. Are you already authenticated in your browser session?

Try: Clear browser cookies or open in incognito mode

### Problem: Can't access secrets.toml

**Solution:** 
- The file is in `.streamlit\secrets.toml` (not in the root directory)
- If it doesn't exist, copy from `.streamlit\secrets.toml.example`
- Make sure you have the `.streamlit` directory

### Problem: Forgot the password

**Solution:**

**For Streamlit Cloud:**
- You (the admin) can view/change it in app settings → Secrets

**For local:**
- Edit `.streamlit\secrets.toml` and change `APP_PASSWORD`

---

## 📝 Summary

- ✅ Password protection runs **FIRST**, before any content loads
- ✅ Protects **ALL** pages and functionality
- ✅ Can be disabled for local development (comment out `APP_PASSWORD`)
- ✅ Easy to deploy on Streamlit Cloud (just add to Secrets)
- ✅ Session-based (stays logged in until browser closes)

For questions or issues, contact the development team.
