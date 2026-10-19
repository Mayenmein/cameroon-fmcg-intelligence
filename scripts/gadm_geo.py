# src/ingestion/gadm_geo.py
import geopandas as gpd
from src.config.settings import Settings


def load_gadm(level: int) -> gpd.GeoDataFrame:
    """Load a GADM admin level for Cameroon as a GeoDataFrame."""
    path = Settings().data_raw_dir / "gadm" / f"gadm41_CMR_{level}.json.zip"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Download from gadm.org.")
    return gpd.read_file(path)


def build_region_dim() -> gpd.GeoDataFrame:
    """Extract 10 regions with centroid coordinates for dim_region."""
    region = load_gadm(3).to_crs(epsg=4326)
    region["latitude"] = region.geometry.representative_point().y
    region["longitude"] = region.geometry.representative_point().x
    region = region[["NAME_1", "NAME_2", "NAME_3", "latitude", "longitude"]].rename(
        columns={"NAME_1": "region_name", "NAME_2": "division_name", "NAME_3": "subdivision_name"} 
    )
    save_path = Settings().dim_region_path
    save_path.parent.mkdir(parents=True, exist_ok=True)
    region.to_csv(Settings().dim_region_path, index=False)
    return region

if __name__ == "__main__":
    regions = build_region_dim()
    print(regions.head())