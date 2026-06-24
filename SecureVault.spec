# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SecureVault + ZTerm

import os
from pathlib import Path

import ttkbootstrap
ttk_path = Path(ttkbootstrap.__file__).parent

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ttkbootstrap themes
        (str(ttk_path / 'themes'), 'ttkbootstrap/themes'),
    ],
    hiddenimports=[
        # ttkbootstrap
        'ttkbootstrap',
        'ttkbootstrap.themes',
        # cryptography
        'cryptography.hazmat.primitives.kdf.pbkdf2',
        'cryptography.hazmat.backends',
        # paramiko
        'paramiko',
        'paramiko.transport',
        'paramiko.auth_handler',
        'paramiko.channel',
        'paramiko.sftp_client',
        'paramiko.sftp_server',
        'paramiko.sftp_attr',
        'paramiko.rsakey',
        'paramiko.ed25519key',
        'paramiko.ecdsakey',
        'paramiko.dsskey',
        'paramiko.packet',
        'paramiko.compress',
        'paramiko.kex_group14',
        'paramiko.kex_ecdh_nist',
        'paramiko.kex_curve25519',
        # pyte
        'pyte',
        'pyte.screens',
        'pyte.graphics',
        'pyte.modes',
        'pyte.streams',
        'pyte.control',
        'pyte.escape',
        # ZTerm internal modules
        'zterm',
        'zterm.session_store',
        'zterm.ssh_client',
        'zterm.terminal_widget',
        'zterm.sftp_browser',
        'zterm.snippets',
        'zterm.history',
        'zterm.mobaxterm_import',
        # UI additions
        'ui.zterm_panel',
        'ui.zterm_session_dialog',
        'ui.zterm_import_dialog',
        'ui.zterm_multiexec',
        'ui.zterm_credtools',
        # Excel report export
        'openpyxl',
        'openpyxl.utils',
        'openpyxl.styles',
        'et_xmlfile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SecureVault',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
