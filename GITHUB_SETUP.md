# GitHub Setup Guide

Follow these steps to push your QRR project to GitHub.

## Prerequisites
- Git installed on your system
- GitHub account created
- Repository created on GitHub (can be empty)

## Step 1: Install Git (if not already installed)

### Windows
Download from: https://git-scm.com/download/win

### macOS
```bash
brew install git
```

### Linux
```bash
sudo apt-get install git  # Ubuntu/Debian
sudo yum install git      # CentOS/RHEL
```

## Step 2: Configure Git (first time only)

Open terminal/command prompt in the QRR folder and run:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

## Step 3: Initialize Git Repository

```bash
cd C:\Users\ajmee\OneDrive\Desktop\QRR
git init
```

## Step 4: Add Files to Git

```bash
# Add all files
git add .

# Check what will be committed
git status
```

## Step 5: Create First Commit

```bash
git commit -m "Initial commit - QR Attendance System"
```

## Step 6: Create Repository on GitHub

1. Go to https://github.com
2. Click "+" icon → "New repository"
3. Name: `QRR` or `attendance-system`
4. Description: "QR Code Student Attendance Management System"
5. Choose Public or Private
6. **DO NOT** initialize with README (we already have one)
7. Click "Create repository"

## Step 7: Link Local Repository to GitHub

GitHub will show you commands. Use the second option (existing repository):

```bash
# Replace YOUR_USERNAME and YOUR_REPO_NAME with your details
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

### Example:
```bash
git remote add origin https://github.com/ajmee/attendance-system.git
git branch -M main
git push -u origin main
```

## Step 8: Enter GitHub Credentials

When prompted:
- **Username:** Your GitHub username
- **Password:** Use Personal Access Token (not password)

### Creating Personal Access Token:
1. Go to GitHub → Settings → Developer settings
2. Personal access tokens → Tokens (classic)
3. Generate new token
4. Select scopes: `repo` (full control)
5. Copy token and use as password

## Step 9: Verify Upload

1. Refresh your GitHub repository page
2. All files should be visible
3. README.md will display automatically

## Future Updates

After making changes to your code:

```bash
# Check what changed
git status

# Add specific files
git add filename.py

# Or add all changes
git add .

# Commit with message
git commit -m "Description of changes"

# Push to GitHub
git push
```

## Common Git Commands

```bash
# View commit history
git log

# View remote repository URL
git remote -v

# Pull latest changes from GitHub
git pull

# Create a new branch
git checkout -b feature-name

# Switch branches
git checkout main

# Merge branch into main
git merge feature-name

# Discard local changes
git checkout -- filename.py

# Remove file from git (keeps local copy)
git rm --cached filename.py
```

## .gitignore Already Created

The following files/folders are excluded from Git:
- `__pycache__/` - Python cache
- `*.db` - SQLite databases
- `venv/` - Virtual environment
- `static/qr_codes/*.png` - Generated QR codes
- `static/qr_sessions/*.png` - Session QR codes
- `*.log` - Log files

## Sensitive Information

⚠️ **Before pushing, ensure:**
- No passwords in code (use environment variables)
- No database credentials hardcoded
- No API keys exposed
- Update `db_config.py` to use environment variables:

```python
import os

SERVER = os.getenv('SQL_SERVER', 'localhost')
DATABASE = os.getenv('SQL_DATABASE', 'attendance_system')
```

## Repository Settings Recommendations

### After Pushing:

1. **Add Topics** (GitHub)
   - qr-code, attendance, flask, sql-server, python

2. **Add Description**
   - "QR Code-based Student Attendance Management System with Admin, Teacher & Student Portals"

3. **Enable Issues** (for bug tracking)

4. **Add LICENSE file**
   - Click "Add file" → "Create new file"
   - Name: `LICENSE`
   - Choose MIT License template

5. **Add Screenshot**
   - Create `screenshots/` folder
   - Add dashboard.png, scan.png, etc.
   - Reference in README.md

## Collaborative Workflow

If working with team:

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/QRR.git

# Create feature branch
git checkout -b feature/new-feature

# Make changes and commit
git add .
git commit -m "Add new feature"

# Push branch
git push origin feature/new-feature

# Create Pull Request on GitHub
```

## Troubleshooting

### Error: "Repository not found"
- Check remote URL: `git remote -v`
- Verify repository exists on GitHub
- Check spelling of username/repo name

### Error: "Permission denied"
- Verify Personal Access Token is correct
- Check token has `repo` scope
- Try SSH instead of HTTPS

### Large Files Error
- GitHub has 100MB file limit
- Use Git LFS for large files
- Or add to .gitignore

## Resources

- Git Documentation: https://git-scm.com/doc
- GitHub Guides: https://guides.github.com/
- Git Cheat Sheet: https://education.github.com/git-cheat-sheet-education.pdf
