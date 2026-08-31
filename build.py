"""
SeatHunter Build Script
Usage: python build.py
"""
import os
import sys
import shutil
import subprocess

# Python version check
if sys.version_info < (3, 8):
    sys.exit(
        f"SeatHunter requires Python >= 3.8, "
        f"current: {sys.version_info.major}.{sys.version_info.minor}"
    )


def check_dependencies():
    """Check and install required dependencies."""
    print("=" * 50)
    print(f"Checking dependencies (Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})...")
    print("=" * 50)

    missing = []

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"  [OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  [Missing] PyInstaller")
        missing.append("pyinstaller")

    # Check project dependencies
    deps = {
        "playwright": "playwright",
        "requests": "requests",
        "yaml": "pyyaml",
        "prettytable": "prettytable",
        "pwinput": "pwinput",
    }
    # pywin32 is Windows-only
    if sys.platform == "win32":
        deps["win32gui"] = "pywin32"

    for module, package in deps.items():
        try:
            __import__(module)
            print(f"  [OK] {package}")
        except ImportError:
            print(f"  [Missing] {package}")
            missing.append(package)

    # Check tkinter (for GUI mode)
    try:
        import tkinter
        print("  [OK] tkinter")
    except ImportError:
        print("  [WARN] tkinter not available - GUI mode will not work, falling back to CLI")

    if missing:
        print(f"\nInstalling missing dependencies: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("Dependencies installed.\n")

    # Verify PyInstaller is available
    try:
        import PyInstaller
    except ImportError:
        print("Error: PyInstaller install failed. Run: pip install pyinstaller")
        sys.exit(1)


def find_playwright_chromium():
    """Find Playwright Chromium browser path."""
    if sys.platform == "win32":
        default_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ms-playwright')
    elif sys.platform == "darwin":
        default_path = os.path.join(os.path.expanduser('~'), 'Library', 'Caches', 'ms-playwright')
    else:
        default_path = os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright')

    browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', default_path)

    if not os.path.exists(browsers_path):
        print("Error: Playwright browser directory not found.")
        print("Run: python -m playwright install chromium")
        sys.exit(1)

    # Platform-specific Chromium binary directory names
    if sys.platform == "win32":
        chrome_subdir = ('chrome-win64', 'chrome.exe')
    elif sys.platform == "darwin":
        chrome_subdir = ('chrome-mac', 'Chromium')
    else:
        chrome_subdir = ('chrome-linux', 'chrome')

    for item in os.listdir(browsers_path):
        if item.startswith('chromium-') and not item.startswith('chromium_headless'):
            chromium_dir = os.path.join(browsers_path, item)
            if os.path.exists(os.path.join(chromium_dir, *chrome_subdir)):
                print(f"  Found Chromium: {chromium_dir}")
                return chromium_dir

    print("Error: Playwright Chromium browser not found.")
    print("Run: python -m playwright install chromium")
    sys.exit(1)


def generate_version_file():
    """Generate Windows version info file (reduces antivirus false positives)."""
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.txt')
    content = '''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 0, 0, 0),
    prodvers=(2, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'080404b0',
      [StringStruct(u'CompanyName', u'HDU SeatHunter'),
      StringStruct(u'FileDescription', u'HDU Library Seat Booking Tool'),
      StringStruct(u'FileVersion', u'2.0.0'),
      StringStruct(u'InternalName', u'SeatHunter'),
      StringStruct(u'LegalCopyright', u'MIT License'),
      StringStruct(u'OriginalFilename', u'SeatHunter.exe'),
      StringStruct(u'ProductName', u'SeatHunter'),
      StringStruct(u'ProductVersion', u'2.0.0')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)'''
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  [OK] Generated version info: {version_file}")
    return version_file


def run_pyinstaller():
    """Run PyInstaller build."""
    print("\n" + "=" * 50)
    print("Running PyInstaller...")
    print("=" * 50)

    spec_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SeatHunter.spec')
    subprocess.run(
        [sys.executable, '-m', 'PyInstaller', spec_file, '--clean', '--noconfirm'],
        check=True
    )


def copy_extra_files(dist_dir, chromium_dir):
    """Copy extra files to output directory."""
    print("\n" + "=" * 50)
    print("Copying extra files...")
    print("=" * 50)

    project_root = os.path.dirname(os.path.abspath(__file__))

    # Copy Chromium
    chromium_dest = os.path.join(dist_dir, 'chromium')
    if os.path.exists(chromium_dest):
        print("  Removing old Chromium...")
        shutil.rmtree(chromium_dest)
    print("  Copying Chromium browser (this may take a few minutes)...")
    shutil.copytree(chromium_dir, chromium_dest)
    print(f"  [OK] Chromium -> {chromium_dest}")

    # Copy docs
    docs_src = os.path.join(project_root, 'docs')
    docs_dest = os.path.join(dist_dir, 'docs')
    if os.path.exists(docs_dest):
        shutil.rmtree(docs_dest)
    if os.path.exists(docs_src):
        shutil.copytree(docs_src, docs_dest)
        print(f"  [OK] docs -> {docs_dest}")

    # Create empty config and logs directories
    for dirname in ['config', 'logs']:
        d = os.path.join(dist_dir, dirname)
        os.makedirs(d, exist_ok=True)
        print(f"  [OK] {dirname} directory -> {d}")

    # Copy seathunter package (for source mode)
    sh_src = os.path.join(project_root, 'seathunter')
    sh_dest = os.path.join(dist_dir, 'seathunter')
    if os.path.exists(sh_dest):
        shutil.rmtree(sh_dest)
    if os.path.exists(sh_src):
        shutil.copytree(sh_src, sh_dest)
        print(f"  [OK] seathunter package -> {sh_dest}")


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(project_root, 'dist', 'SeatHunter')

    print("SeatHunter Build Tool")
    print(f"Project directory: {project_root}")
    print(f"Python: {sys.version}")
    print()

    # 1. Check dependencies
    check_dependencies()

    # 2. Find Chromium
    print("\nLocating Playwright Chromium...")
    chromium_dir = find_playwright_chromium()

    # 3. Generate version info
    print("\nGenerating version info...")
    generate_version_file()

    # 4. Run PyInstaller
    run_pyinstaller()

    # 5. Copy extra files
    copy_extra_files(dist_dir, chromium_dir)

    # 6. Done
    print("\n" + "=" * 50)
    print("Build complete!")
    print("=" * 50)
    print(f"\nOutput directory: {dist_dir}")
    print(f"\nUsage:")
    print(f"  1. Distribute the entire {dist_dir} folder")
    print(f"  2. Users run {os.path.join(dist_dir, 'SeatHunter.exe')}")
    print(f"\nNote: SeatHunter.exe depends on the _internal directory and other")
    print(f"      files in the dist folder. Do NOT run it alone.")
    print()

    # Show total size
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(dist_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    print(f"Total size: {total_size / (1024 * 1024):.1f} MB")


if __name__ == '__main__':
    main()
