# 🚀 GITHUB SETUP GUIDE — Bina Coding Ke, Sirf Browser Se
### (15-20 minute ka one-time kaam — uske baad roz automatic signal milega, ₹0 kharcha)

---

## STEP 1: GitHub account banao (agar nahi hai)
1. https://github.com kholo → **Sign up**
2. Email + password dalo, account ban gaya (free hai)

## STEP 2: Naya repository banao
1. Upar-right **"+"** icon → **"New repository"**
2. Repository name: `nifty-oi-predictor`
3. **Private** select karo (taki sirf tum dekh sako)
4. Baaki kuch mat chhedo → **"Create repository"** button

## STEP 3: Files upload karo (sabse important step)
1. Apne computer par `nifty-oi-predictor.zip` ko **extract/unzip** karo
   (Google Drive ke `04_Backups_and_GitHub_Repo` folder se download karke)
2. GitHub ke naye repo page par link dikhega: **"uploading an existing file"** → us par click karo
3. Extract kiye hue folder ke andar jao aur **saari files aur folders ko drag-drop** karo
   (`predictor` folder, `data` folder, `output` folder, `README.md`, `requirements.txt`, `GITHUB_SETUP_GUIDE.md`)
   ⚠️ `.github` wala folder drag-drop mein chhut sakta hai (hidden hota hai) — wo STEP 4 mein alag se karenge
4. Niche **"Commit changes"** button dabao → wait karo (data folder bada hai, 2-5 min)

## STEP 4: Automation wali file banao (.github folder)
1. Repo mein upar **"Add file" → "Create new file"**
2. File name mein EXACTLY ye type karo: `.github/workflows/daily.yml`
   (`/` type karte hi folder apne aap banta jayega)
3. Apne computer par extract kiye folder mein `.github/workflows/daily.yml` file ko
   **Notepad se kholo**, pura content **copy** karo, GitHub ke editor mein **paste** karo
   (Hidden folder nahi dikh raha? Windows: File Explorer → View → "Hidden items" ✓ | Mac: Cmd+Shift+. dabao)
4. **"Commit changes"** dabao

## STEP 5: Permission do (1 minute)
1. Repo mein **Settings** (upar tab) → left side **Actions → General**
2. Niche scroll karo **"Workflow permissions"** tak
3. **"Read and write permissions"** select karo → **Save**

## STEP 6: Pehla test chalao
1. Upar **"Actions"** tab → left mein **"Daily OI Prediction"**
2. Right side **"Run workflow"** button → green **"Run workflow"** confirm
3. 2-3 minute wait → green ✓ aa jaye to SAB SET! ❌ aaye to mujhe (AI chat) screenshot dikhana
4. Ab repo ke `output/PREDICTION.md` file mein **aaj ka signal** dikh raha hoga

## ✅ BAS! AB KYA HOGA:
- **Har din shaam ~7:45 baje** (aur backup 9:15 baje) system khud chalega
- NSE se data uthayega → signal banayega → `output/PREDICTION.md` update karega
- Tumhe roz sirf ek kaam: repo kholo → `output/PREDICTION.md` dekho → jo likha hai wo karo
- **Phone par shortcut:** repo ke PREDICTION.md ka link browser mein bookmark kar lo

---

## 📱 BONUS: Telegram par roz signal (optional, 5 minute)
Roz report kholne ka bhi jhanjhat nahi — signal seedha phone par:

1. Telegram kholo → search karo **@BotFather** → `/newbot` bhejo → naam do
   → wo tumhe ek **TOKEN** dega (jaise `110201543:AAHdqTc...`) — copy karo
2. Ab search karo **@userinfobot** → `/start` bhejo → wo tumhari **Chat ID** dega (jaise `123456789`)
3. GitHub repo → **Settings → Secrets and variables → Actions → "New repository secret"**:
   - Name: `TELEGRAM_BOT_TOKEN` | Value: (BotFather wala token) → Add
   - Phir dusra: Name: `TELEGRAM_CHAT_ID` | Value: (apni chat id) → Add
4. Apne bot ko Telegram mein ek baar `/start` bhej do (warna wo message nahi bhej sakta)
5. Done! Ab roz shaam ko Telegram par aayega:
   > 🟢🟢 NIFTY OI SIGNAL — aaj ka verdict + kitna invested rehna hai

---

## ❓ Common problems:
| Problem | Fix |
|---|---|
| Actions tab mein kuch nahi | STEP 4 dobara check — file ka naam EXACTLY `.github/workflows/daily.yml` hona chahiye |
| Run fail (red ❌) | STEP 5 wali permission check karo; phir bhi fail to log ka screenshot AI chat mein dikhao |
| Data upload mein error | `data` folder ki files 25MB se chhoti hain, aana chahiye — net slow ho to folder ke andar ki files 2-3 batch mein upload karo |
| Signal purana dikh raha | Actions tab mein dekho aakhri run kab hua — weekend/holiday ko naya data nahi aata (market band) |
