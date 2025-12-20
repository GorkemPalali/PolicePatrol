from dataclasses import dataclass
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from app.models.police_station import PoliceStation
from app.models.risk_cell import RiskCell
from app.services.utils import get_point_coordinates
from app.core.config import get_settings


@dataclass
class RouteRequest:
    station_id: UUID
    risk_threshold: float = 0.7
    max_minutes: int = 90
    end_station_id: Optional[UUID] = None


@dataclass
class RouteWaypoint:
    lat: float
    lng: float
    risk_score: Optional[float] = None


@dataclass
class RouteResult:
    waypoints: List[RouteWaypoint]
    total_distance: float
    total_time: float
    risk_coverage: float
    path: dict  # GeoJSON LineString


def get_station_coordinates(db: Session, station_id: UUID) -> Tuple[float, float]:
    """Get lat/lng coordinates of a police station"""
    station = db.query(PoliceStation).filter(PoliceStation.id == station_id).first()
    if not station:
        raise ValueError(f"Station {station_id} not found")
    
    return get_point_coordinates(db, station.geom)


def get_high_risk_cells(
    db: Session,
    risk_threshold: float,
    bbox: Optional[Tuple[float, float, float, float]] = None
) -> List[RiskCell]:
    """Get risk cells above threshold within Küçükçekmece polygon boundaries"""
    from app.services.utils import get_kucukcekmece_boundary
    
    query = db.query(RiskCell).filter(RiskCell.risk_score >= risk_threshold)
    
    # Filter by polygon intersection
    # If custom bbox provided, we still need to filter by polygon
    # The bbox is only used for initial filtering, final filter is polygon
    boundary_geom = get_kucukcekmece_boundary(db)
    
    if boundary_geom:
        # Use polygon intersection
        query = query.filter(
            text("""
                ST_Intersects(
                    geom,
                    (SELECT geom FROM administrative_boundary 
                     WHERE name = 'Küçükçekmece' AND admin_level = 8 LIMIT 1)
                )
            """)
        )
    else:
        # Fallback to bbox if polygon not available
        from app.core.config import get_settings
        from app.services.utils import get_kucukcekmece_bbox_from_polygon
        settings = get_settings()
        kucukcekmece_bbox = get_kucukcekmece_bbox_from_polygon(db) or settings.kucukcekmece_fallback_bbox
        
        if bbox:
            effective_bbox = (
                max(bbox[0], kucukcekmece_bbox[0]),
                max(bbox[1], kucukcekmece_bbox[1]),
                min(bbox[2], kucukcekmece_bbox[2]),
                min(bbox[3], kucukcekmece_bbox[3])
            )
        else:
            effective_bbox = kucukcekmece_bbox
        
        query = query.filter(
            text("""
                ST_Intersects(
                    geom,
                    ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326)::geography
                )
            """).params(
                min_lat=effective_bbox[0],
                min_lng=effective_bbox[1],
                max_lat=effective_bbox[2],
                max_lng=effective_bbox[3]
            )
        )
    
    return query.limit(100).all()  # Limit to top 100 risk cells


def cluster_risk_cells(
    db: Session,
    risk_cells: List[RiskCell],
    max_clusters: int = 10
) -> List[Tuple[float, float, float]]:
    """
    Cluster risk cells and return cluster centers with average risk.
    Returns list of (lat, lng, avg_risk_score)
    """
    if not risk_cells:
        return []
    
    # Simple approach: group by proximity
    # Get centroids of risk cells
    centroids = []
    for cell in risk_cells:
        centroid = db.execute(
            text("""
                SELECT 
                    ST_Y(ST_Centroid(ST_GeomFromWKB(:geom))) as lat,
                    ST_X(ST_Centroid(ST_GeomFromWKB(:geom))) as lng
            """),
            {"geom": cell.geom.data}
        ).first()
        
        if centroid:
            centroids.append({
                "lat": float(centroid.lat),
                "lng": float(centroid.lng),
                "risk": cell.risk_score
            })
    
    # Simple clustering: group nearby points
    clusters = []
    used = set()
    
    for i, point in enumerate(centroids):
        if i in used:
            continue
        
        cluster_points = [point]
        used.add(i)
        
        # Find nearby points (within 500m)
        for j, other_point in enumerate(centroids):
            if j in used:
                continue
            
            # Calculate distance
            dist = ((point["lat"] - other_point["lat"]) ** 2 + 
                   (point["lng"] - other_point["lng"]) ** 2) ** 0.5 * 111000
            
            if dist < 500:
                cluster_points.append(other_point)
                used.add(j)
        
        # Calculate cluster center and average risk
        avg_lat = sum(p["lat"] for p in cluster_points) / len(cluster_points)
        avg_lng = sum(p["lng"] for p in cluster_points) / len(cluster_points)
        avg_risk = sum(p["risk"] for p in cluster_points) / len(cluster_points)
        
        clusters.append((avg_lat, avg_lng, avg_risk))
        
        if len(clusters) >= max_clusters:
            break
    
    return clusters


def compute_route_via_points(
    db: Session,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    waypoints: List[Tuple[float, float]],
    max_distance_m: float
) -> RouteResult:
    """
    Compute route using pgRouting.
    This is a simplified version - full implementation would use pgr_ksp or similar.
    """
    # Check if pgRouting is available
    try:
        # Try to use pgRouting if road_segment table has topology
        # For now, return a simple straight line route with waypoints
        
        all_points = [(start_lat, start_lng)] + waypoints + [(end_lat, end_lng)]
        
        # Create simplified route (straight lines between points)
        route_waypoints = []
        total_distance = 0.0
        
        for i in range(len(all_points) - 1):
            lat1, lng1 = all_points[i]
            lat2, lng2 = all_points[i + 1]
            
            # Calculate distance (Haversine approximation)
            import math
            R = 6371000  # Earth radius in meters
            
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlng / 2) ** 2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = R * c
            
            total_distance += distance
            
            route_waypoints.append(RouteWaypoint(
                lat=lat1,
                lng=lng1,
                risk_score=None
            ))
        
        # Add final point
        route_waypoints.append(RouteWaypoint(
            lat=end_lat,
            lng=end_lng,
            risk_score=None
        ))
        
        # Estimate time (assuming average speed of 30 km/h)
        total_time = (total_distance / 1000.0) / 30.0 * 60.0
        
        # Create GeoJSON LineString
        coordinates = [[lng, lat] for lat, lng in all_points]
        path = {
            "type": "LineString",
            "coordinates": coordinates
        }
        
        # Calculate risk coverage (simplified)
        risk_coverage = min(1.0, len(waypoints) / 10.0)
        
        return RouteResult(
            waypoints=route_waypoints,
            total_distance=total_distance,
            total_time=total_time,
            risk_coverage=risk_coverage,
            path=path
        )
        
    except Exception as e:
        # Fallback: simple route
        raise ValueError(f"Route computation failed: {str(e)}")


def compute_route(
    db: Session,
    request: RouteRequest
) -> RouteResult:
    """
    Main route optimization function.
    """
    # Get start station coordinates
    start_lat, start_lng = get_station_coordinates(db, request.station_id)
    
    # Determine end station
    if request.end_station_id:
        end_lat, end_lng = get_station_coordinates(db, request.end_station_id)
    else:
        # Return to start station
        end_lat, end_lng = start_lat, start_lng
    
    # Get high-risk cells within Küçükçekmece polygon boundaries
    from app.core.config import get_settings
    from app.services.utils import get_kucukcekmece_bbox_from_polygon, get_kucukcekmece_boundary
    settings = get_settings()
    
    # Check if start station is within Küçükçekmece polygon
    boundary_geom = get_kucukcekmece_boundary(db)
    if boundary_geom:
        # Check if station is within polygon
        station_within = db.execute(
            text("""
                SELECT ST_Within(
                    ST_GeogFromText('POINT(:lng :lat)'),
                    (SELECT geom FROM administrative_boundary 
                     WHERE name = 'Küçükçekmece' AND admin_level = 8 LIMIT 1)
                )
            """),
            {"lat": start_lat, "lng": start_lng}
        ).scalar()
        
        if station_within:
            # Use polygon boundary (no bbox needed, polygon filter will be applied in get_high_risk_cells)
            bbox = None
        else:
            # Station outside Küçükçekmece, use 5km radius
            bbox = (
                start_lat - 0.045,  # ~5km
                start_lng - 0.045,
                start_lat + 0.045,
                start_lng + 0.045
            )
    else:
        # Fallback to bbox if polygon not available
        kucukcekmece_bbox = get_kucukcekmece_bbox_from_polygon(db) or settings.kucukcekmece_fallback_bbox
        if (kucukcekmece_bbox[0] <= start_lat <= kucukcekmece_bbox[2] and
            kucukcekmece_bbox[1] <= start_lng <= kucukcekmece_bbox[3]):
            bbox = kucukcekmece_bbox
        else:
            bbox = (
                start_lat - 0.045,
                start_lng - 0.045,
                start_lat + 0.045,
                start_lng + 0.045
            )
    
    risk_cells = get_high_risk_cells(db, request.risk_threshold, bbox)
    
    # Cluster risk cells
    risk_clusters = cluster_risk_cells(db, risk_cells, max_clusters=10)
    
    # Extract waypoints (cluster centers)
    waypoints = [(lat, lng) for lat, lng, _ in risk_clusters]
    
    # Limit waypoints based on max time
    # Rough estimate: each waypoint adds ~10 minutes
    max_waypoints = max(1, request.max_minutes // 10)
    waypoints = waypoints[:max_waypoints]
    
    # Compute route
    max_distance_m = request.max_minutes * 30 * 1000 / 60
    
    route = compute_route_via_points(
        db,
        start_lat,
        start_lng,
        end_lat,
        end_lng,
        waypoints,
        max_distance_m
    )
    
    # Add risk scores to waypoints
    for i, waypoint in enumerate(route.waypoints):
        if i < len(risk_clusters):
            waypoint.risk_score = risk_clusters[i][2]
    
    return route