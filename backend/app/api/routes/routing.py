from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.routing import (
    MultiStationRouteRequest,
    MultiStationRouteResponse,
    RouteOptimizeRequest,
    RouteResponse,
    RouteWaypoint,
    StationRoute,
)
from app.services.routing.multi_station_coordinator import (
    coordinate_multi_station_routes,
)
from app.services.routing.route_optimizer import compute_route, RouteRequest

router = APIRouter(prefix="/routing", tags=["routing"])


@router.post("/optimize", response_model=RouteResponse)
def optimize_route(
    body: RouteOptimizeRequest,
    db: Session = Depends(get_db)
):
    """Optimize patrol route based on risk cells"""
    
    try:
        route_request = RouteRequest(
            station_id=body.station_id,
            risk_threshold=body.risk_threshold,
            max_minutes=body.max_minutes,
            end_station_id=body.end_station_id
        )
        
        result = compute_route(db, route_request)
        
        # Convert to response format
        waypoints = [
            RouteWaypoint(
                lat=wp.lat,
                lng=wp.lng,
                risk_score=wp.risk_score
            )
            for wp in result.waypoints
        ]
        
        return RouteResponse(
            waypoints=waypoints,
            total_distance=result.total_distance,
            total_time=result.total_time,
            risk_coverage=result.risk_coverage,
            path=result.path
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Route optimization failed: {str(e)}"
        )


@router.post("/optimize-multi", response_model=MultiStationRouteResponse)
def optimize_multi_station_route(
    body: MultiStationRouteRequest,
    db: Session = Depends(get_db),
):
    """Optimize coordinated routes for multiple police stations"""
    
    try:
        # Check if multi-station coordination is enabled
        from app.core.config import get_settings
        settings = get_settings()
        
        if not getattr(settings, "multi_station_coordination_enabled", True):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Multi-station coordination is disabled"
            )
        
        # Validate station IDs if provided
        if body.station_ids:
            from app.models.police_station import PoliceStation
            from app.services.utils import validate_within_boundary
            from app.services.routing.route_optimizer import get_station_coordinates
            
            valid_stations = []
            for station_id in body.station_ids:
                station = db.query(PoliceStation).filter(
                    PoliceStation.id == station_id,
                    PoliceStation.active == True
                ).first()
                
                if not station:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Station {station_id} not found or inactive"
                    )
                
                # Validate station is within Küçükçekmece boundary
                lat, lng = get_station_coordinates(db, station_id)
                is_valid, error_message = validate_within_boundary(db, lat, lng)
                if not is_valid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Station {station.name} is outside Küçükçekmece boundary: {error_message}"
                    )
                
                valid_stations.append(station_id)
            
            if not valid_stations:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No valid active stations found"
                )
        
        # Coordinate routes
        result = coordinate_multi_station_routes(
            db=db,
            station_ids=body.station_ids,
            risk_threshold=body.risk_threshold,
            max_minutes_per_station=body.max_minutes_per_station,
            minimize_overlap=body.minimize_overlap,
            distribute_by_capacity=body.distribute_by_capacity,
        )
        
        # Convert to response format
        station_routes = []
        for station_id, station_name, route_result in result.station_routes:
            waypoints = [
                RouteWaypoint(
                    lat=wp.lat,
                    lng=wp.lng,
                    risk_score=wp.risk_score,
                )
                for wp in route_result.waypoints
            ]
            
            station_routes.append(
                StationRoute(
                    station_id=station_id,
                    station_name=station_name,
                    waypoints=waypoints,
                    total_distance=route_result.total_distance,
                    total_time=route_result.total_time,
                    risk_coverage=route_result.risk_coverage,
                    path=route_result.path,
                )
            )
        
        return MultiStationRouteResponse(
            routes=station_routes,
            total_stations=len(station_routes),
            total_risk_coverage=result.total_risk_coverage,
            overlap_percentage=result.overlap_percentage,
            coordination_score=result.coordination_score,
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Multi-station route optimization failed: {str(e)}"
        )
    