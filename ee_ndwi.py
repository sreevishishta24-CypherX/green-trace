"""
Optional Earth Engine NDWI helper. Requires authenticated Earth Engine (ee) client.

Function compute_ndwi(bbox, out_path, start_date, end_date) -> saves ndwi PNG to out_path and returns path.
If Earth Engine isn't available or not authenticated, raises RuntimeError with a helpful message.
"""
from typing import Tuple
import json
import requests


def compute_ndwi(bbox: Tuple[float, float, float, float], out_png_path: str, start_date: str = None, end_date: str = None, vis_params: dict = None) -> str:
    """Compute NDWI for the bbox using Sentinel-2 in Earth Engine and save a thumbnail PNG.

    bbox: (minlon, minlat, maxlon, maxlat)
    out_png_path: local path to save PNG
    start_date / end_date: ISO date strings, optional (defaults to last 90 days)
    vis_params: dict passed to getThumbURL (optional)

    Returns path to saved PNG.

    Notes: This function requires the earthengine-api package and an authenticated EE session. If EE isn't
    initialized or the environment isn't authenticated, a RuntimeError is raised with instructions.
    """
    try:
        import ee
    except Exception as e:
        raise RuntimeError("earthengine-api is not installed in the environment: install 'earthengine-api' to enable NDWI support")

    try:
        ee.Initialize()
    except Exception as e:
        raise RuntimeError("Earth Engine initialization failed. Authenticate with 'earthengine authenticate' before using NDWI features. Error: {}".format(e))

    # default date range: last 90 days
    if end_date is None:
        import datetime
        end_date = datetime.date.today().isoformat()
    if start_date is None:
        import datetime
        start_date = (datetime.date.fromisoformat(end_date) - datetime.timedelta(days=90)).isoformat()

    minlon, minlat, maxlon, maxlat = bbox
    region = ee.Geometry.Rectangle([minlon, minlat, maxlon, maxlat])

    # Sentinel-2 surface reflectance collection (COPERNICUS/S2_SR) has B3 (green) and B8 (nir)
    collection = ee.ImageCollection('COPERNICUS/S2_SR') \
        .filterBounds(region) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))

    if collection.size().getInfo() == 0:
        raise RuntimeError(f"No Sentinel-2 images found in {start_date}..{end_date} for bbox {bbox}")

    # median composite
    image = collection.median()

    # NDWI = (green - nir) / (green + nir) -> B3 and B8
    ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')

    if vis_params is None:
        vis_params = {'min': -1, 'max': 1, 'palette': ['white', 'blue']}

    try:
        thumb_params = {
            'min': vis_params.get('min', -1),
            'max': vis_params.get('max', 1),
            'palette': ','.join(vis_params.get('palette', ['white','blue'])),
            'region': json.dumps([minlon, minlat, maxlon, maxlat]),
            'dimensions': 512,
            'format': 'png'
        }
        url = ndwi.getThumbURL(thumb_params)
    except Exception as e:
        # getThumbURL can fail in some setups; surface a helpful error
        raise RuntimeError(f"Failed to generate NDWI thumbnail URL from Earth Engine: {e}")

    # download the thumbnail
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(out_png_path, 'wb') as f:
        for chunk in resp.iter_content(1024):
            f.write(chunk)

    return out_png_path
