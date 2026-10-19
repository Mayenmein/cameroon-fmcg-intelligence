import os
import requests
from dotenv import load_dotenv
from pathlib import Path
from tqdm import tqdm
import json, hashlib, zipfile, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
import pandas as pd

from src.config.settings import Settings
settings = Settings()

def _download_one(session, headers, file_meta, dest, retries=2, backoff=1):
    """Download a single file with retries. Returns (status, filename, reason)."""
    link = file_meta["links"]["download"]
    filename = file_meta.get("filename") or link.split("/")[-1]
    target = dest / filename

    if target.exists() and target.stat().st_size > 0:
        return "skipped", filename, None

    for attempt in range(retries + 1):
        try:
            with session.get(link, headers=headers, stream=True, timeout=120) as r:
                r.raise_for_status()
                tmp = target.with_suffix(target.suffix + ".part")
                with open(tmp, "wb") as out:
                    for chunk in r.iter_content(chunk_size=1 << 15):
                        out.write(chunk)
                tmp.rename(target)
            return "ok", filename, None
        except Exception as e:
            if attempt < retries:
                sleep(backoff)
                continue
            return "failed", filename, str(e)


def download_dataset(
    url: str,
    api_key: str,
    dest_dir: Path,
    limit: int | None = None,
    workers: int = 8,
    batch_size: int = 20,
):
    """Download files from a World Bank dataset listing with retries and concurrency.

    Args:
        url: API endpoint returning the file listing JSON.
        api_key: World Bank API key.
        dest_dir: Local folder to save files into.
        limit: Max number of files to download. None = all.
        workers: Number of concurrent download threads.
        batch_size: Not used for scheduling; kept for API compatibility.
    """
    headers = {"Authorization": f"Bearer {api_key}", "X-API-KEY": api_key}
    session = requests.Session()
    session.headers.update(headers)

    files = session.get(url, timeout=60).json().get("files", [])
    downloadable = [f for f in files if f.get("links", {}).get("download")]
    if limit is not None:
        downloadable = downloadable[:limit]

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(downloadable)} of {len(files)} files into {dest.resolve()}")

    results = {"ok": 0, "skipped": 0, "failed": 0}
    failures = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_download_one, session, headers, f, dest)
            for f in downloadable
        ]
        with tqdm(total=len(futures), desc="Downloading", unit="file") as bar:
            for fut in as_completed(futures):
                status, filename, reason = fut.result()
                results[status] += 1
                if status == "failed":
                    failures.append((filename, reason))
                bar.update(1)
                bar.set_postfix(ok=results["ok"], skip=results["skipped"], fail=results["failed"])

    print(f"\nDone. ok={results['ok']} skipped={results['skipped']} failed={results['failed']}")
    if failures:
        print("Failed files:")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
    return results

class WFPIngester:
    name = "wfp_prices"

    def __init__(self):
        self.zips_dir = settings.wfp_raw_path
        self.extract_dir = settings.wfp_interim_path
        self.extract_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(p: Path, retries: int = 5, delay: float = 0.5) -> str:
        for attempt in range(retries):
            try:
                return hashlib.sha256(p.read_bytes()).hexdigest()
            except PermissionError:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)

    def extract_all(self) -> list[Path]:
        """Unzip every archive; skip existing; write one manifest per zip."""
        out = []
        zips = sorted(self.zips_dir.glob("*.zip"))
        for zpath in tqdm(zips, desc="Extracting zips", unit="zip"):
            with zipfile.ZipFile(zpath) as z:
                members = [
                    m for m in z.namelist()
                    if m.lower().endswith((".csv", ".dta", ".xlsx"))
                ]
                for m in tqdm(members, desc=f"  {zpath.name}", unit="file", leave=False):
                    target = self.extract_dir / Path(m).name
                    if not target.exists():
                        target.write_bytes(z.read(m))
                    out.append(target)

            manifest = {
                "source_url": "https://microdata.worldbank.org/index.php/catalog/CMR_2021_RTFP_v02_M",
                "zip_file": zpath.name,
                "zip_sha256": self._sha256(zpath),
                "extracted_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "files": [
                    {"name": p.name, "size": p.stat().st_size, "sha256": self._sha256(p)}
                    for p in out if p.parent == self.extract_dir
                ],
            }
            (self.extract_dir / f"{zpath.stem}_manifest.json").write_text(
                json.dumps(manifest, indent=2)
            )

        print(f"Extracted {len(out)} files to {self.extract_dir}")
        return out

    def load_latest(self) -> pd.DataFrame:
        """Load the newest CSV in extracted/."""
        csvs = sorted(self.extract_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not csvs:
            raise FileNotFoundError("Run extract_all() first.")
        for csv in reversed(csvs):
            try:
                df = pd.read_csv(csv)
                print(f"Loaded {csv} with {len(df):,} rows.")
                return df
            except Exception as e:
                print(f"Failed to load {csv}: {e}")
        raise RuntimeError("No CSV could be loaded.")

if __name__ == "__main__":
    load_dotenv()
    download_dataset(
            url="https://microdata.worldbank.org//api/downloads/CMR_2021_RTFP_v02_M/files?type=data",
            api_key=os.environ["WB_API_KEY"],
            dest_dir=settings.wfp_raw_path,
            limit=0,
            workers=8,
        )
    
    wfp = WFPIngester()
    wfp.extract_all()
    wfp.load_latest()
