# shellmate.spec — single-file binary (kim-style). Artifact name via SHELLMATE_ARTIFACT.
import os

a = Analysis(
    ["llm.py"],
    datas=[("commands.json", ".")],
    hiddenimports=["tldr"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=os.environ.get("SHELLMATE_ARTIFACT", "shellmate"),
    console=True,
    upx=False,
)