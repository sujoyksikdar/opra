#!/usr/bin/env python3
"""
update_district_boundaries.py

Downloads the latest US congressional district boundary shapefiles from the
US Census Bureau Cartographic Boundary Files, converts them to GeoJSON, and
updates the per-state files used by the OPRA mock election map.

Requires the 'pyshp' library (auto-installed if missing).

Usage (run from the compsocsite/ directory):
    python3 scripts/update_district_boundaries.py
    python3 scripts/update_district_boundaries.py --congress 119 --year 2024
    python3 scripts/update_district_boundaries.py --dry-run
"""

import argparse
import io
import json
import os
import struct
import sys
import urllib.request
import urllib.error
import zipfile


# ---------------------------------------------------------------------------
# Dependency check — auto-install pyshp if not present
# ---------------------------------------------------------------------------

def _ensure_pyshp():
    try:
        import shapefile  # noqa: F401
    except ImportError:
        print("Installing required library 'pyshp'...")
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyshp', '-q'])
        print("Installed pyshp.\n")


# ---------------------------------------------------------------------------
# State FIPS → name mapping
# ---------------------------------------------------------------------------

FIPS_TO_STATE = {
    '01': 'Alabama',        '02': 'Alaska',         '04': 'Arizona',
    '05': 'Arkansas',       '06': 'California',     '08': 'Colorado',
    '09': 'Connecticut',    '10': 'Delaware',       '12': 'Florida',
    '13': 'Georgia',        '15': 'Hawaii',         '16': 'Idaho',
    '17': 'Illinois',       '18': 'Indiana',        '19': 'Iowa',
    '20': 'Kansas',         '21': 'Kentucky',       '22': 'Louisiana',
    '23': 'Maine',          '24': 'Maryland',       '25': 'Massachusetts',
    '26': 'Michigan',       '27': 'Minnesota',      '28': 'Mississippi',
    '29': 'Missouri',       '30': 'Montana',        '31': 'Nebraska',
    '32': 'Nevada',         '33': 'New Hampshire',  '34': 'New Jersey',
    '35': 'New Mexico',     '36': 'New York',       '37': 'North Carolina',
    '38': 'North Dakota',   '39': 'Ohio',           '40': 'Oklahoma',
    '41': 'Oregon',         '42': 'Pennsylvania',   '44': 'Rhode Island',
    '45': 'South Carolina', '46': 'South Dakota',  '47': 'Tennessee',
    '48': 'Texas',          '49': 'Utah',           '50': 'Vermont',
    '51': 'Virginia',       '53': 'Washington',     '54': 'West Virginia',
    '55': 'Wisconsin',      '56': 'Wyoming',
}

# Census Cartographic Boundary shapefile releases to try, newest first.
# Format: (census_release_year, congress_number)
# Update this list after each new Census release.
CENSUS_RELEASES = [
    (2024, 119),
    (2023, 118),
    (2022, 117),
    (2020, 116),
]

CENSUS_URL = (
    "https://www2.census.gov/geo/tiger/GENZ{year}/shp/"
    "cb_{year}_us_cd{congress}_500k.zip"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_get(url, timeout=180):
    req = urllib.request.Request(url, headers={'User-Agent': 'OPRA-DistrictUpdater/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def auto_detect_release():
    """
    Try each (year, congress) release from newest to oldest and return the
    first one whose zip file URL is reachable (reads only the first 16 bytes).
    """
    print("Auto-detecting latest Census Bureau release...")
    for year, congress in CENSUS_RELEASES:
        url = CENSUS_URL.format(year=year, congress=congress)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'OPRA-DistrictUpdater/1.0'})
            with urllib.request.urlopen(req, timeout=20) as resp:
                head = resp.read(16)
                # ZIP files start with PK\x03\x04
                if head[:2] == b'PK':
                    print(f"  Found: {congress}th Congress, {year} release.")
                    return year, congress
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"  HTTP {e.code} for {year}/{congress}.")
        except Exception:
            pass
    return None, None


def shapefile_to_geojson_features(zip_bytes, congress):
    """
    Given the raw bytes of a Census shapefile zip, returns a list of
    GeoJSON Feature dicts, one per congressional district.

    Normalises the CD field to 'CD116FP' so the existing map JS works
    without any template changes.
    """
    import shapefile

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    # Find the .shp and .dbf members (there is exactly one of each)
    names = zf.namelist()
    shp_name = next(n for n in names if n.endswith('.shp'))
    dbf_name = next(n for n in names if n.endswith('.dbf'))
    # shapefile.Reader can take separate file-like objects
    sf = shapefile.Reader(
        shp=io.BytesIO(zf.read(shp_name)),
        dbf=io.BytesIO(zf.read(dbf_name)),
    )

    field_names = [f[0] for f in sf.fields[1:]]  # skip DeletionFlag
    cd_field = next((f for f in field_names if f.startswith('CD') and f.endswith('FP')), None)

    features = []
    for sr in sf.shapeRecords():
        props = dict(zip(field_names, sr.record))
        # Coerce bytes → str (DBF fields can be bytes in some versions)
        props = {k: v.strip() if isinstance(v, (str, bytes)) else v
                 for k, v in props.items()}
        if isinstance(props.get('STATEFP'), bytes):
            props = {k: v.decode() if isinstance(v, bytes) else v
                     for k, v in props.items()}

        # Skip non-50-state features (territories)
        if props.get('STATEFP') not in FIPS_TO_STATE:
            continue

        # Normalize CD field name → CD116FP for backward compatibility
        if cd_field and cd_field != 'CD116FP':
            props['CD116FP'] = props.pop(cd_field)

        props['CDSESSN'] = str(congress)

        # Convert pyshp shape → GeoJSON geometry
        shape = sr.shape
        geom = _shape_to_geojson(shape)
        if geom is None:
            continue

        features.append({
            'type': 'Feature',
            'properties': props,
            'geometry': geom,
        })

    return features, cd_field


def _shape_to_geojson(shape):
    """Convert a pyshp shape record to a GeoJSON geometry dict."""
    import shapefile
    st = shape.shapeType
    # Polygon / PolygonZ / PolygonM
    if st in (5, 15, 25):
        parts = list(shape.parts) + [len(shape.points)]
        rings = [
            [list(p) for p in shape.points[parts[i]:parts[i + 1]]]
            for i in range(len(parts) - 1)
        ]
        if len(rings) == 1:
            return {'type': 'Polygon', 'coordinates': rings}
        return {'type': 'MultiPolygon', 'coordinates': [[r] for r in rings]}
    # MultiPatch / Null
    return None


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def update_districts(congress, year, output_dir, dry_run=False):
    url = CENSUS_URL.format(year=year, congress=congress)
    print(f"\nDownloading {congress}th Congress shapefile ({year} release)...")
    print(f"  {url}")

    try:
        zip_bytes = _http_get(url)
    except Exception as e:
        print(f"\nERROR: Could not download shapefile: {e}")
        print("Check your internet connection or try a different --year/--congress.")
        sys.exit(1)

    print(f"  Downloaded {len(zip_bytes) // 1024} KB. Converting to GeoJSON...")

    try:
        features, cd_field = shapefile_to_geojson_features(zip_bytes, congress)
    except Exception as e:
        print(f"\nERROR: Could not parse shapefile: {e}")
        sys.exit(1)

    if cd_field and cd_field != 'CD116FP':
        print(f"  '{cd_field}' normalized to 'CD116FP' for map compatibility.")

    # Group by state
    by_state = {}
    for feat in features:
        state_fip = feat['properties'].get('STATEFP')
        state_name = FIPS_TO_STATE.get(state_fip)
        if state_name:
            by_state.setdefault(state_name, []).append(feat)

    print(f"  States found: {len(by_state)}")
    if len(by_state) < 50:
        missing = sorted(set(FIPS_TO_STATE.values()) - set(by_state.keys()))
        print(f"  Missing: {', '.join(missing)}")

    updated = 0
    for state_name, feats in sorted(by_state.items()):
        filename = state_name.replace(' ', '_') + '.json'
        filepath = os.path.join(output_dir, filename)
        geojson = {'type': 'FeatureCollection', 'features': feats}

        if dry_run:
            print(f"  [DRY RUN] {filename}: {len(feats)} district(s)")
            continue

        with open(filepath, 'w') as f:
            json.dump(geojson, f, separators=(',', ':'))

        print(f"  Updated  {filename}  ({len(feats)} district(s))")
        updated += 1

    print()
    if dry_run:
        print(f"Dry run complete. {len(by_state)} file(s) would be written to:")
        print(f"  {output_dir}")
    else:
        print(f"Done. {updated} state file(s) updated in:")
        print(f"  {output_dir}")
        print()
        print("Next steps:")
        print("  1. Restart the dev server (changes are live immediately in development).")
        print("  2. In production, run collectstatic:")
        print("       docker compose exec web python3 manage.py collectstatic --noinput")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Update OPRA congressional district boundary GeoJSON files "
            "from the US Census Bureau."
        )
    )
    parser.add_argument(
        '--congress', type=int, default=None,
        help="Congressional session number (e.g. 119). Auto-detected if omitted."
    )
    parser.add_argument(
        '--year', type=int, default=None,
        help="Census release year (e.g. 2024). Auto-detected if omitted."
    )
    parser.add_argument(
        '--output-dir', default=None,
        help=(
            "Directory to write state GeoJSON files. "
            "Defaults to static/js/districts/ relative to this script."
        )
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Show what would be updated without writing any files."
    )
    args = parser.parse_args()

    # Resolve output directory
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.normpath(
            os.path.join(script_dir, '..', 'static', 'js', 'districts')
        )

    if not os.path.isdir(output_dir):
        print(f"ERROR: Output directory does not exist: {output_dir}")
        print("Run this script from the compsocsite/ directory, or pass --output-dir.")
        sys.exit(1)

    # Resolve congress / year
    congress = args.congress
    year = args.year

    if congress is None or year is None:
        det_year, det_congress = auto_detect_release()
        if det_year is None:
            print(
                "ERROR: Could not auto-detect a Census release. "
                "Specify --congress and --year manually.\n"
                "Example: python3 scripts/update_district_boundaries.py "
                "--congress 119 --year 2024"
            )
            sys.exit(1)
        congress = congress or det_congress
        year = year or det_year

    _ensure_pyshp()

    print(
        f"\n{'[DRY RUN] ' if args.dry_run else ''}"
        f"Updating to {congress}th Congress ({year} Census release)"
    )
    print(f"Output directory: {output_dir}\n")

    update_districts(congress, year, output_dir, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
