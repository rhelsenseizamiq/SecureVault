# ZM Password Manager v2.0 - Build Instructions

## Quick Build (Easiest Method)

### On Windows:

1. **Open Command Prompt** in the `PythonApplication1` folder
   - Right-click folder → "Open in Terminal" or "Open Command Prompt here"

2. **Run the build script:**
   ```cmd
   build.bat
   ```

3. **Wait 2-3 minutes** for the build to complete

4. **Your executable will be at:**
   ```
   dist\ZMPasswordManager.exe
   ```

5. **Double-click to run it!**

That's it! The build script handles everything automatically.

---

## Manual Build (If Script Fails)

### Step 1: Install Python

1. Download Python 3.8+ from https://python.org/downloads/
2. During installation, check "Add Python to PATH"
3. Verify installation:
   ```cmd
   python --version
   ```

### Step 2: Install Dependencies

```cmd
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
```

### Step 3: Build Executable

```cmd
python -m PyInstaller ZMPasswordManager.spec
```

### Step 4: Find Your Executable

```
dist\ZMPasswordManager.exe
```

---

## Troubleshooting

### "Python is not recognized"
- Python not installed or not in PATH
- Solution: Reinstall Python and check "Add to PATH" option

### "No module named 'cryptography'"
- Dependencies not installed
- Solution: Run `python -m pip install -r requirements.txt`

### "No module named 'ttkbootstrap'"
- ttkbootstrap not installed
- Solution: Run `python -m pip install ttkbootstrap`

### Build succeeds but executable won't run
- May be missing theme files
- Solution: Check `ZMPasswordManager.spec` has correct `datas` paths

### "Access is denied" when building
- Anti-virus blocking PyInstaller
- Solution: Temporarily disable anti-virus or add exception

### Executable is too large (>50MB)
- Normal - includes Python runtime and all dependencies
- Expected size: 15-25MB
- If larger, check for unnecessary includes

---

## Creating MSI Installer (Optional)

### Requirements:
- WiX Toolset v3.14: https://wixtoolset.org/

### Build MSI:

1. **Run the MSI build script:**
   ```cmd
   build_msi.bat
   ```

2. **Your installer will be created:**
   ```
   ZMPasswordManager.msi
   ```

### Manual MSI Build:

```cmd
"C:\Program Files (x86)\WiX Toolset v3.14\bin\candle.exe" installer.wxs
"C:\Program Files (x86)\WiX Toolset v3.14\bin\light.exe" installer.wixobj -o ZMPasswordManager.msi
```

---

## Testing the Executable

### First Test (Local):

1. Navigate to `dist` folder
2. Double-click `ZMPasswordManager.exe`
3. Application should start
4. Create a master password
5. Add a test credential
6. Close and reopen to test persistence

### Second Test (Clean Environment):

1. Copy `ZMPasswordManager.exe` to a different folder
2. Run it on a clean Windows machine (if available)
3. Should work without installing anything
4. Data will be stored in `%APPDATA%\ZMPasswordManager\`

---

## Build Output

### Expected Files:

**After building:**
```
dist/
  └── ZMPasswordManager.exe    (15-25MB)
build/
  └── [temporary build files]
```

**Data files (created at runtime):**
```
%APPDATA%\ZMPasswordManager\
  ├── master.dat               (hashed master password)
  ├── passwords.json.enc       (encrypted credentials)
  └── settings.json            (user preferences)
```

---

## Distribution

### To distribute your application:

**Option 1: Standalone EXE**
- Share `dist\ZMPasswordManager.exe`
- Users can run it directly
- No installation needed

**Option 2: MSI Installer**
- Share `ZMPasswordManager.msi`
- Users double-click to install
- Creates Start Menu shortcuts
- Professional installation experience

### Notes:
- Executable is portable (no installation required)
- Data stored in user's AppData folder
- No admin rights needed to run
- Safe to distribute

---

## Verification Checklist

After building, verify:

- [ ] Executable size is 15-25MB
- [ ] Double-click launches the application
- [ ] Login window appears
- [ ] Can create master password
- [ ] Can add credentials
- [ ] Can view/edit/delete credentials
- [ ] Password generator works
- [ ] Settings can be changed
- [ ] Auto-lock works (wait 10 minutes)
- [ ] Theme selection works (requires restart)
- [ ] Data persists after closing and reopening

---

## Advanced: Customization

### Change Icon:

1. Create or download an `.ico` file
2. Edit `ZMPasswordManager.spec`:
   ```python
   exe = EXE(
       ...
       icon='path/to/your/icon.ico',  # Add this line
   )
   ```
3. Rebuild

### Change Application Name:

1. Edit `ZMPasswordManager.spec`:
   ```python
   exe = EXE(
       ...
       name='MyPasswordManager',  # Change this
   )
   ```
2. Rebuild

### Reduce Size:

1. Edit `ZMPasswordManager.spec`:
   ```python
   exe = EXE(
       ...
       upx=True,  # Enable UPX compression
       upx_exclude=[],
   )
   ```
2. Rebuild

---

## Support

### Build fails?

1. Check Python version: `python --version` (need 3.8+)
2. Check dependencies: `python -m pip list`
3. Delete build folders and try again:
   ```cmd
   rmdir /s build
   rmdir /s dist
   ```
4. Read error messages carefully

### Still having issues?

- Review `TEST_RESULTS.md` for known issues
- Check `CLAUDE.md` for technical details
- Ensure all 20 Python files are present
- Verify `requirements.txt` exists

---

## Summary

**Easiest way:**
```cmd
build.bat
```

**Result:**
```
dist\ZMPasswordManager.exe
```

**Test it:**
```cmd
cd dist
ZMPasswordManager.exe
```

**Distribute:**
- Share the EXE file
- No installation needed
- Works on Windows 10/11

**Done!** 🎉

---

## Build Time

- **First build:** 2-3 minutes (downloading dependencies)
- **Subsequent builds:** 30-60 seconds

## System Requirements

**To build:**
- Windows 10/11
- Python 3.8+
- 500MB free space
- Internet connection (for dependencies)

**To run (end users):**
- Windows 10/11
- No Python needed
- 50MB free space
- No internet needed

---

## Files You Need

Make sure these files exist before building:

**Required:**
- `main.py` - Entry point
- `config.py` - Configuration
- `requirements.txt` - Dependencies
- `ZMPasswordManager.spec` - Build configuration
- All files in `crypto/`, `database/`, `models/`, `ui/`, `utils/`

**Optional:**
- `installer.wxs` - For MSI installer
- `icon.ico` - Custom icon

---

**Ready to build?** Run `build.bat` and you're done!
