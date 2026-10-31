"""Download a project-local Android build toolchain from official sources."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "build" / "android-tools"
ROOT.mkdir(parents=True, exist_ok=True)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "TVRemote-build"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def install(name, url, checksum):
    archive = ROOT / f"{name}.zip"
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        print(f"Downloading {name}...", flush=True)
        archive.write_bytes(fetch(url))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        raise RuntimeError(f"Checksum mismatch: {name}")
    destination = ROOT / name
    if not destination.exists():
        destination.mkdir()
        with zipfile.ZipFile(archive) as source:
            for entry in source.namelist():
                if not (destination / entry).resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError("Unsafe archive path")
            source.extractall(destination)
    print(f"Ready: {destination}", flush=True)


if __name__ == "__main__":
    assets = json.loads(fetch("https://api.github.com/repos/adoptium/temurin21-binaries/releases/latest"))["assets"]
    jdk = next(a for a in assets if a["name"].startswith("OpenJDK21U-jdk_x64_windows_hotspot_")
               and a["name"].endswith(".zip"))
    jdk_url = jdk["browser_download_url"]
    gradle = "https://services.gradle.org/distributions/gradle-8.11.1-bin.zip"
    jobs = [
        ("jdk", jdk_url, fetch(jdk_url + ".sha256.txt").decode().split()[0]),
        ("gradle", gradle, fetch(gradle + ".sha256").decode().strip()),
        ("sdk-tools", "https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip",
         "90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a"),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda job: install(*job), jobs))
