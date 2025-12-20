"""OSM import API endpoints."""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.services.osm.osm_service import import_osm_data, get_osm_import_status
from app.services.osm.routing_topology import RoutingTopology
from app.services.osm.boundary_service import BoundaryService
from app.services.osm.boundary_importer import BoundaryImporter
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/osm", tags=["OSM"])


class OSMImportRequest(BaseModel):
    """Request model for OSM import."""

    clear_existing: bool = False
    create_topology: bool = True
    bbox: Optional[List[float]] = None  # [min_lat, min_lng, max_lat, max_lng]
    highway_tags: Optional[List[str]] = None


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """
    Get OSM import and routing topology status.

    Returns:
        Dictionary with import status and statistics
    """
    try:
        status = get_osm_import_status(db)
        return status
    except Exception as e:
        logger.error(f"Failed to get OSM status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/import")
def import_osm(
    request: OSMImportRequest,
    db: Session = Depends(get_db),
):
    """
    Import OSM data and create routing topology.

    Args:
        request: OSM import request parameters
        db: Database session

    Returns:
        Dictionary with import results
    """
    try:
        # Convert bbox list to tuple if provided
        bbox = None
        if request.bbox:
            if len(request.bbox) != 4:
                raise HTTPException(
                    status_code=400,
                    detail="Bbox must contain 4 values: [min_lat, min_lng, max_lat, max_lng]",
                )
            bbox = tuple(request.bbox)

        logger.info(f"Starting OSM import (clear_existing={request.clear_existing})")

        result = import_osm_data(
            db=db,
            bbox=bbox,
            clear_existing=request.clear_existing,
            create_topology=request.create_topology,
            highway_tags=request.highway_tags,
        )

        if result["success"]:
            return {
                "success": True,
                "message": "OSM import completed successfully",
                **result,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"OSM import failed: {', '.join(result.get('errors', []))}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import OSM data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/refresh-topology")
def refresh_topology(
    force: bool = Query(False, description="Force recreation of topology"),
    db: Session = Depends(get_db),
):
    """
    Refresh pgRouting topology.

    Args:
        force: If True, drop existing topology before creating
        db: Database session

    Returns:
        Dictionary with topology creation results
    """
    try:
        settings = get_settings()
        topology_tolerance = getattr(settings, "osm_topology_tolerance", 0.0001)

        topology_service = RoutingTopology(db, tolerance=topology_tolerance)
        result = topology_service.create_topology(force_recreate=force)

        if result.get("success"):
            return {
                "success": True,
                "message": "Topology refreshed successfully",
                **result,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Topology refresh failed: {result.get('error', 'Unknown error')}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh topology: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Topology refresh failed: {str(e)}")


@router.get("/topology-status")
def get_topology_status(db: Session = Depends(get_db)):
    """
    Get routing topology status.

    Returns:
        Dictionary with topology status information
    """
    try:
        settings = get_settings()
        topology_tolerance = getattr(settings, "osm_topology_tolerance", 0.0001)

        topology_service = RoutingTopology(db, tolerance=topology_tolerance)
        status = topology_service.get_topology_status()

        return status

    except Exception as e:
        logger.error(f"Failed to get topology status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get topology status: {str(e)}"
        )


@router.post("/import-boundary")
def import_boundary(
    force: bool = Query(False, description="Force re-import even if boundary exists"),
    db: Session = Depends(get_db),
):
    """
    Import Küçükçekmece boundary from OSM.

    Args:
        force: If True, re-import even if boundary already exists
        db: Database session

    Returns:
        Dictionary with import results
    """
    try:
        settings = get_settings()

        # Check if boundary already exists
        importer = BoundaryImporter(db)
        boundary_exists = importer.boundary_exists(
            settings.kucukcekmece_boundary_name,
            settings.kucukcekmece_boundary_admin_level
        )

        if boundary_exists and not force:
            return {
                "success": True,
                "message": "Boundary already exists. Use force=true to re-import",
                "boundary_exists": True,
            }

        # Fetch boundary from OSM
        logger.info("Fetching Küçükçekmece boundary from OSM...")
        boundary_service = BoundaryService(
            api_url=getattr(settings, "overpass_api_url", "https://overpass-api.de/api/interpreter")
        )

        # Use fallback bbox to limit search area
        bbox = settings.kucukcekmece_fallback_bbox
        xml_data = boundary_service.fetch_boundary_by_name(
            name=settings.kucukcekmece_boundary_name,
            admin_level=settings.kucukcekmece_boundary_admin_level,
            bbox=bbox,
        )

        # Import boundary
        result = importer.import_boundary(
            name=settings.kucukcekmece_boundary_name,
            admin_level=settings.kucukcekmece_boundary_admin_level,
            xml_data=xml_data,
            update_existing=force,
        )

        if result["success"]:
            return {
                "success": True,
                "message": "Boundary imported successfully",
                **result,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Boundary import failed: {result.get('error', 'Unknown error')}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import boundary: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Boundary import failed: {str(e)}")


@router.get("/boundary-status")
def get_boundary_status(db: Session = Depends(get_db)):
    """
    Get Küçükçekmece boundary status.

    Returns:
        Dictionary with boundary status information
    """
    try:
        settings = get_settings()
        importer = BoundaryImporter(db)

        boundary_exists = importer.boundary_exists(
            settings.kucukcekmece_boundary_name,
            settings.kucukcekmece_boundary_admin_level
        )

        if not boundary_exists:
            return {
                "boundary_loaded": False,
                "message": "Küçükçekmece boundary not loaded. Use POST /api/v1/osm/import-boundary to import it.",
            }

        boundary = importer.get_boundary(
            settings.kucukcekmece_boundary_name,
            settings.kucukcekmece_boundary_admin_level
        )

        return {
            "boundary_loaded": True,
            "name": boundary.name,
            "admin_level": boundary.admin_level,
            "created_at": boundary.created_at.isoformat() if boundary.created_at else None,
            "updated_at": boundary.updated_at.isoformat() if boundary.updated_at else None,
        }

    except Exception as e:
        logger.error(f"Failed to get boundary status: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get boundary status: {str(e)}"
        )

