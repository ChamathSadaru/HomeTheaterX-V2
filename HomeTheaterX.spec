# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

added_files = [
    ('web', 'web'),
    ('apo', 'apo'),
    ('Splash.jpg', '.'),
    ('samsung.ico', '.'),
]

hidden_imports = [
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'clr',
    'clr_loader',
    'pythonnet',
    'pycaw',
    'pycaw.pycaw',
    'comtypes',
    'comtypes.client',
    'sounddevice',
    'numpy',
    'pystray',
    'pystray._win32',
    'PIL',
    'PIL.ImageTk',
    'PIL._tkinter_finder',
    'websockets',
    'websockets.legacy',
    'websockets.legacy.server',
    'websockets.server',
    'websockets.asyncio.server',
    'winotify',
    'pywinauto',
    'winsound',
    'tkinter',
]

a = Analysis(
    ['web_server.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HomeTheaterX',
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
    icon='samsung.ico',
)
