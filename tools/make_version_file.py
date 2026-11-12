"""Write a PyInstaller version resource so the exe's Properties > Details show the version."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stick_citizen import __version__  # noqa: E402

nums = [int(x) for x in __version__.split(".")[:3]] + [0]
t = tuple(nums[:4])
out = Path(sys.argv[1] if len(sys.argv) > 1 else "version_info.txt")
out.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'ShoelessTim'),
      StringStruct('FileDescription', 'Stick Citizen - HOSAS bindings for Star Citizen'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'StickCitizen'),
      StringStruct('OriginalFilename', 'StickCitizen-v{__version__}.exe'),
      StringStruct('ProductName', 'Stick Citizen'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print(out)
