from geoalchemy2.shape import from_shape, to_shape
from geoalchemy2 import Geography
from shapely.geometry import Point, LineString, Polygon
from shapely import wkt
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Tuple, Optional
from functools import lru_cache


def lat_lng_to_geography(lat: float, lng: float) -> str:
    """Convert lat/lng to PostGIS Geography POINT"""
    point = Point(lng, lat)
    return from_shape(point, srid=4326)


def geography_to_lat_lng(geom) -> Tuple[float, float]:
    """Convert PostGIS Geography to lat/lng tuple"""
    if geom is None:
        return (0.0, 0.0)
    
    # Use raw SQL to get lat/lng from geography
    # This is more reliable than to_shape for geography types
    return (float(geom.y), float(geom.x))


def geography_to_geojson(db: Session, geom, geom_type: str = "Point") -> Optional[dict]:
    """Convert PostGIS Geography to GeoJSON using ST_AsGeoJSON"""
    if geom is None:
        return None
    
    # Use PostGIS function to convert to GeoJSON
    result = db.execute(
        text("SELECT ST_AsGeoJSON(ST_GeomFromWKB(:geom))::json"),
        {"geom": geom.data}
    ).scalar()
    
    if result:
        return result
    
    return None


def get_point_coordinates(db: Session, geom) -> Tuple[float, float]:
    """Get lat/lng from geography point using PostGIS functions"""
    if geom is None:
        return (0.0, 0.0)
    
    try:
        # Method 1: Use ST_Y and ST_X directly on geography
        # Note: ST_Y returns latitude, ST_X returns longitude
        result = db.execute(
            text("""
                SELECT 
                    ST_Y(CAST(:geom AS geometry)) as lat,
                    ST_X(CAST(:geom AS geometry)) as lng
            """),
            {"geom": geom}
        ).first()
        
        if result and result.lat is not None and result.lng is not None:
            return (float(result.lat), float(result.lng))
    except Exception as e1:
        # Fallback: Try using to_shape if geom has data attribute
        try:
            if hasattr(geom, 'data'):
                shape = to_shape(geom)
                if hasattr(shape, 'y') and hasattr(shape, 'x'):
                    return (float(shape.y), float(shape.x))
        except Exception as e2:
            # Last fallback: Try direct attribute access
            try:
                if hasattr(geom, 'y') and hasattr(geom, 'x'):
                    return (float(geom.y), float(geom.x))
            except Exception:
                pass
    
    return (0.0, 0.0)


def get_kucukcekmece_boundary(db: Session) -> Optional[Geography]:
    """
    Get Küçükçekmece boundary polygon from database.

    Args:
        db: Database session

    Returns:
        Geography polygon or None if not found
    """
    from app.core.config import get_settings
    from app.models.administrative_boundary import AdministrativeBoundary

    settings = get_settings()
    boundary = (
        db.query(AdministrativeBoundary)
        .filter(
            AdministrativeBoundary.name == settings.kucukcekmece_boundary_name,
            AdministrativeBoundary.admin_level == settings.kucukcekmece_boundary_admin_level,
        )
        .first()
    )

    if boundary:
        return boundary.geom
    return None


def get_kucukcekmece_bbox_from_polygon(db: Session) -> Optional[Tuple[float, float, float, float]]:
    """
    Calculate bounding box from Küçükçekmece polygon.

    Args:
        db: Database session

    Returns:
        Tuple of (min_lat, min_lng, max_lat, max_lng) or None if polygon not found
    """
    boundary_geom = get_kucukcekmece_boundary(db)
    if not boundary_geom:
        from app.core.config import get_settings
        settings = get_settings()
        return settings.kucukcekmece_fallback_bbox

    try:
        result = db.execute(
            text("""
                SELECT 
                    ST_YMin(CAST(:geom AS geometry)) as min_lat,
                    ST_XMin(CAST(:geom AS geometry)) as min_lng,
                    ST_YMax(CAST(:geom AS geometry)) as max_lat,
                    ST_XMax(CAST(:geom AS geometry)) as max_lng
                FROM (SELECT :geom::geography as geom) as g
            """),
            {"geom": boundary_geom},
        ).first()

        if result and all(
            [
                result.min_lat is not None,
                result.min_lng is not None,
                result.max_lat is not None,
                result.max_lng is not None,
            ]
        ):
            return (
                float(result.min_lat),
                float(result.min_lng),
                float(result.max_lat),
                float(result.max_lng),
            )
    except Exception as e:
        # Log error but don't fail
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to calculate bbox from polygon: {str(e)}")

    from app.core.config import get_settings
    settings = get_settings()
    return settings.kucukcekmece_fallback_bbox


def validate_within_boundary(
    db: Session, lat: float, lng: float
) -> Tuple[bool, Optional[str]]:
    """
    Validate if coordinates are within Küçükçekmece boundary.

    Args:
        db: Database session
        lat: Latitude
        lng: Longitude

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if within boundary, False otherwise
        - error_message: Error message if not valid, None if valid
    """
    from app.core.config import get_settings

    settings = get_settings()

    # Check if strict validation is enabled
    strict_validation = getattr(settings, "strict_boundary_validation", True)
    if not strict_validation:
        return (True, None)

    try:
        # Try to use polygon boundary first
        boundary_geom = get_kucukcekmece_boundary(db)

        if boundary_geom:
            # Use polygon validation
            result = db.execute(
                text("""
                    SELECT is_within_kucukcekmece(ST_GeogFromText(:wkt))
                """),
                {"wkt": f"SRID=4326;POINT({lng} {lat})"},
            ).scalar()

            if result:
                return (True, None)
            else:
                return (
                    False,
                    f"Koordinatlar ({lat}, {lng}) Küçükçekmece polygon sınırları dışında",
                )
        else:
            # Fallback to bbox validation
            bbox = get_kucukcekmece_bbox_from_polygon(db) or settings.kucukcekmece_fallback_bbox
            min_lat, min_lng, max_lat, max_lng = bbox

            if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
                return (True, None)
            else:
                return (
                    False,
                    f"Koordinatlar ({lat}, {lng}) Küçükçekmece bounding box sınırları dışında "
                    f"(sınırlar: lat [{min_lat}, {max_lat}], lng [{min_lng}, {max_lng}])",
                )

    except Exception as e:
        # Log error but don't fail validation if there's a database error
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Boundary validation error: {str(e)}")

        # If validation fails due to error, allow the operation (fail open)
        # This prevents system from breaking if boundary is not loaded
        return (True, None)