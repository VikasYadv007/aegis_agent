from PyInstaller.utils.hooks import collect_data_files, copy_metadata

a = Analysis(['main.py'], pathex=[],
             datas=collect_data_files('customtkinter') + copy_metadata('google-genai') + [('assets/aegis.ico', 'assets')],
             hiddenimports=['aegis_app'],
             excludes=['matplotlib', 'numpy', 'pandas', 'pytest', 'IPython'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Aegis',
          debug=False, strip=False, upx=False, console=False,
          version='version_info.txt', icon='assets/aegis.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Aegis')
