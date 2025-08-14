# deploy-wallpaper.py
import os
import json
import shutil
from json import JSONDecodeError
from pathlib import Path
from config_loader import OUTPUT_BASE_DIR, build_view_key, canonicalize  # shared helpers

PROJECTS_JSON_PATH = Path("projects.json")
VIEWS_JSON_PATH = Path("views_config.json")

# Optional: set STAGE_ONLY=1 to skip copying into Wallpaper Engine (creates/updates staging only)
STAGE_ONLY = os.environ.get("STAGE_ONLY", "0") == "1"


def find_parent_dir_for_key(output_root: Path, canonical_key: str) -> Path | None:
    """
    Return the folder under output_root that corresponds to the canonical_key.
    Primary match: exact folder named canonical_key.
    Fallback: scan subfolders and match canonicalized names (handles legacy folders with symbols like µ).
    """
    direct = output_root / canonical_key
    if direct.is_dir():
        return direct

    # Fallback scan (legacy symbols, mixed unicode)
    for child in output_root.iterdir():
        if not child.is_dir():
            continue
        if canonicalize(child.name) == canonical_key:
            return child

    return None


def stage_from_latest_run(parent_dir: Path) -> Path | None:
    """
    Create/update a staging folder from the latest timestamped run folder.
    Returns the staging path or None if unavailable.
    """
    # pick latest timestamped run by mtime (not by name)
    all_runs = [d for d in parent_dir.iterdir() if d.is_dir() and d.name != 'staging']
    if not all_runs:
        print(f"  ❌ No downloaded frame sets found in {parent_dir}")
        return None

    latest_run_folder = max(all_runs, key=lambda d: d.stat().st_mtime)
    print(f"  [1/4] Latest source frames: {latest_run_folder.name}")

    # staging
    staging_dir = parent_dir / "staging"
    staging_dir.mkdir(exist_ok=True)

    # copy & rename
    print(f"  [2/4] Staging and renaming frames...")
    source_files = sorted(latest_run_folder.glob("*.png"))
    if not source_files:
        print("  ❌ No .png frames found in the latest folder.")
        return None

    for i, frame_path in enumerate(source_files):
        (staging_dir / f"frame_{i:03d}.png").write_bytes(frame_path.read_bytes())
    print(f"  ✅ Staged and renamed {len(source_files)} frames.")

    # Copy manifest for provenance if present
    src_manifest = latest_run_folder / "manifest.json"
    if src_manifest.exists():
        shutil.copy2(src_manifest, staging_dir / "current_manifest.json")

    return staging_dir


def deploy_latest_frames(view_config: dict, project_path_str: str):
    project_path = Path(project_path_str)
    key = build_view_key(view_config)

    print(f"\n{'='*20}\n➡️  Deploying '{key}'\n{'='*20}")

    # Locate the parent output directory robustly (handles legacy unicode)
    parent_dir = find_parent_dir_for_key(OUTPUT_BASE_DIR, key)
    if parent_dir is None:
        print(f"  ❌ Source folder not found for key: {key} (under {OUTPUT_BASE_DIR})")
        return

    staging_dir = stage_from_latest_run(parent_dir)
    if staging_dir is None:
        return

    if STAGE_ONLY:
        print("  [3/4] Stage-only mode: skipping copy to Wallpaper Engine.")
        print("  [4/4] Cleanup skipped — originals & staging preserved.")
        return

    # deploy to Wallpaper Engine materials
    materials_path = project_path / "materials"
    if not materials_path.is_dir():
        print(f"  ❌ 'materials' subfolder not found in {project_path}")
        return

    print(f"  [3/4] Deploying to Wallpaper Engine...")
    copied = 0
    for new_frame in sorted(staging_dir.glob("frame_*.png")):
        shutil.copy2(str(new_frame), str(materials_path))  # copy2 preserves mtime
        copied += 1
    print(f"  ✅ Deployment complete. Copied {copied} frames.")

    # Drop a copy of the current manifest next to the project for reference
    try:
        manifest_in_stage = staging_dir / "current_manifest.json"
        if manifest_in_stage.exists():
            shutil.copy2(manifest_in_stage, project_path / "current_manifest.json")
            print("  ℹ️  Wrote current_manifest.json to project folder.")
    except Exception as e:
        print(f"  ⚠️  Could not copy manifest into project: {e}")

    print(f"  [4/4] Cleanup skipped — originals & staging preserved.")


def main():
    # load configs
    try:
        views = json.loads(VIEWS_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"❌ Missing {VIEWS_JSON_PATH}")
        return
    except JSONDecodeError as e:
        print(f"❌ {VIEWS_JSON_PATH} is not valid JSON: {e}")
        return

    try:
        projs_raw = json.loads(PROJECTS_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"❌ Missing {PROJECTS_JSON_PATH}")
        return
    except JSONDecodeError as e:
        print(f"❌ {PROJECTS_JSON_PATH} is not valid JSON: {e}")
        return

    # normalize project key names using canonicalize (handles µ/μ and other symbols)
    projects: dict[str, str] = {}
    for p in projs_raw:
        name = p.get("view_name_base", "")
        normalized = canonicalize(name)
        projects[normalized] = p["project_path"]

    # deploy each matching view
    for view in views:
        key = build_view_key(view)
        if key in projects:
            deploy_latest_frames(view, projects[key])
        else:
            # Fallback: try canonicalized form of our own key (defensive)
            alt_key = canonicalize(key)
            if alt_key in projects:
                deploy_latest_frames(view, projects[alt_key])
            else:
                print(f"ℹ️  Skipping '{key}' — no matching entry in projects.json")

    print("\n✅ All deployment tasks complete.")


if __name__ == "__main__":
    main()
