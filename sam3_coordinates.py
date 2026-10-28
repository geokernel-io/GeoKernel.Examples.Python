"""Transform WGS84 map prompts to the original raster CRS on the input worker."""
import ctypes as ct
import math
from geokernel.dll import find_bin_dir, load_library


def to_source(raster, points, box):
    gdal = load_library(find_bin_dir() / "gdal.dll")
    ptr, txt = ct.c_void_p, ct.c_char_p
    declarations = {
        "GDALAllRegister": ([], None), "GDALOpen": ([txt,ct.c_int],ptr),
        "GDALGetProjectionRef": ([ptr],txt), "GDALClose": ([ptr],None),
        "OSRNewSpatialReference": ([txt],ptr), "OSRImportFromEPSG": ([ptr,ct.c_int],ct.c_int),
        "OSRSetAxisMappingStrategy": ([ptr,ct.c_int],None), "OSRDestroySpatialReference": ([ptr],None),
        "OCTNewCoordinateTransformation": ([ptr,ptr],ptr), "OCTDestroyCoordinateTransformation": ([ptr],None),
        "OCTTransform": ([ptr,ct.c_int,ct.POINTER(ct.c_double),ct.POINTER(ct.c_double),ct.POINTER(ct.c_double)],ct.c_int),
    }
    for name,(args,result) in declarations.items():
        function = getattr(gdal,name)
        function.argtypes, function.restype = args,result
    gdal.GDALAllRegister()
    dataset = gdal.GDALOpen(str(raster).encode('utf-8'),0)
    if not dataset:
        raise RuntimeError("Cannot read source raster CRS.")
    try:
        wkt = gdal.GDALGetProjectionRef(dataset)
        if not wkt:
            raise RuntimeError("Source raster has no CRS.")
    finally:
        gdal.GDALClose(dataset)
    source = destination = transform = None
    try:
        source = gdal.OSRNewSpatialReference(None)
        destination = gdal.OSRNewSpatialReference(wkt)
        if not source or not destination or gdal.OSRImportFromEPSG(source,4326):
            raise RuntimeError("Cannot initialize prompt coordinate systems.")
        for srs in (source,destination):
            gdal.OSRSetAxisMappingStrategy(srs,0)
        transform = gdal.OCTNewCoordinateTransformation(source,destination)
        if not transform:
            raise RuntimeError("Cannot transform prompt coordinates.")
        def convert(x,y):
            x,y,z = ct.c_double(x),ct.c_double(y),ct.c_double()
            if not gdal.OCTTransform(transform,1,ct.byref(x),ct.byref(y),ct.byref(z)) or not all(map(math.isfinite,(x.value,y.value))):
                raise RuntimeError("Invalid map prompt coordinate.")
            return x.value,y.value
        result = []
        for point in points:
            x,y = convert(point['x'],point['y'])
            result.append(dict(x=x,y=y,positive=point['positive']))
        converted_box = None
        if box:
            a,b,c,d = box
            corners = [convert(a,b),convert(a,d),convert(c,b),convert(c,d)]
            xs,ys = zip(*corners)
            converted_box = [min(xs),min(ys),max(xs),max(ys)]
        return result,converted_box
    finally:
        if transform:
            gdal.OCTDestroyCoordinateTransformation(transform)
        for srs in (source,destination):
            if srs:
                gdal.OSRDestroySpatialReference(srs)
