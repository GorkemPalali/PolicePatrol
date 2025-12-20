"""Database import service for OSM road segments."""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from geoalchemy2 import Geography

from app.models.road_segment import RoadSegment
from app.services.osm.osm_parser import RoadSegmentData

logger = logging.getLogger(__name__)


class OSMImporter:
    """Service for importing OSM road segments into database."""

    def __init__(self, db: Session, clear_existing: bool = False):
        """
        Initialize OSM importer.

        Args:
            db: Database session
            clear_existing: If True, clear existing road segments before import
        """
        self.db = db
        self.clear_existing = clear_existing

    def import_road_segments(
        self, road_segments: List[RoadSegmentData], batch_size: int = 1000
    ) -> dict:
        """
        Import road segments into database.

        Args:
            road_segments: List of RoadSegmentData objects
            batch_size: Number of segments to insert per batch

        Returns:
            Dictionary with import statistics
        """
        stats = {
            "total": len(road_segments),
            "imported": 0,
            "skipped": 0,
            "errors": 0,
        }

        try:
            # Clear existing data if requested
            if self.clear_existing:
                logger.info("Clearing existing road segments...")
                deleted_count = self.db.query(RoadSegment).delete()
                self.db.commit()
                logger.info(f"Deleted {deleted_count} existing road segments")

            # Import in batches
            for i in range(0, len(road_segments), batch_size):
                batch = road_segments[i : i + batch_size]
                batch_stats = self._import_batch(batch)
                stats["imported"] += batch_stats["imported"]
                stats["skipped"] += batch_stats["skipped"]
                stats["errors"] += batch_stats["errors"]

                logger.info(
                    f"Imported batch {i // batch_size + 1}: "
                    f"{batch_stats['imported']} segments, "
                    f"{batch_stats['skipped']} skipped, "
                    f"{batch_stats['errors']} errors"
                )

            self.db.commit()
            logger.info(
                f"Import completed: {stats['imported']} imported, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )

            return stats

        except Exception as e:
            self.db.rollback()
            logger.error(f"Import failed: {str(e)}")
            raise

    def _import_batch(self, road_segments: List[RoadSegmentData]) -> dict:
        """
        Import a batch of road segments.

        Args:
            road_segments: List of RoadSegmentData objects

        Returns:
            Dictionary with batch statistics
        """
        stats = {"imported": 0, "skipped": 0, "errors": 0}

        for segment_data in road_segments:
            try:
                # Convert coordinates to LineString WKT
                # OSM uses (lat, lng), PostGIS expects (lng, lat) for geography
                coords_wkt = ", ".join(
                    [f"{lng} {lat}" for lat, lng in segment_data.geom_coordinates]
                )
                linestring_wkt = f"LINESTRING({coords_wkt})"

                # Filter by Küçükçekmece polygon boundary
                # Only import segments that intersect with the boundary
                # Use ST_Intersects for LineString (not ST_Within, as segments can cross boundary)
                segment_intersects = self.db.execute(
                    text("""
                        SELECT ST_Intersects(
                            ST_GeogFromText(:wkt),
                            (SELECT geom FROM administrative_boundary 
                             WHERE name = 'Küçükçekmece' AND admin_level = 8 LIMIT 1)
                        )
                    """),
                    {"wkt": f"SRID=4326;{linestring_wkt}"}
                ).scalar()
                
                if not segment_intersects:
                    stats["skipped"] += 1
                    continue

                # Check if segment already exists
                existing = self.db.query(RoadSegment).filter(RoadSegment.id == segment_data.osm_id).first()

                # Use raw SQL to insert geometry properly
                geom_sql = text(f"ST_GeogFromText('SRID=4326;{linestring_wkt}')")

                if existing:
                    # Update existing segment using raw SQL
                    self.db.execute(
                        text("""
                            UPDATE road_segment 
                            SET geom = ST_GeogFromText(:wkt),
                                road_type = :road_type,
                                speed_limit = :speed_limit,
                                one_way = :one_way
                            WHERE id = :id
                        """),
                        {
                            "wkt": f"SRID=4326;{linestring_wkt}",
                            "road_type": segment_data.road_type,
                            "speed_limit": segment_data.speed_limit,
                            "one_way": segment_data.one_way,
                            "id": segment_data.osm_id,
                        },
                    )
                    stats["imported"] += 1
                else:
                    # Insert new segment using raw SQL
                    self.db.execute(
                        text("""
                            INSERT INTO road_segment (id, geom, road_type, speed_limit, one_way)
                            VALUES (:id, ST_GeogFromText(:wkt), :road_type, :speed_limit, :one_way)
                        """),
                        {
                            "id": segment_data.osm_id,
                            "wkt": f"SRID=4326;{linestring_wkt}",
                            "road_type": segment_data.road_type,
                            "speed_limit": segment_data.speed_limit,
                            "one_way": segment_data.one_way,
                        },
                    )
                    stats["imported"] += 1

            except Exception as e:
                logger.warning(f"Failed to import segment {segment_data.osm_id}: {str(e)}")
                stats["errors"] += 1
                continue

        return stats

    def get_import_statistics(self) -> dict:
        """
        Get statistics about imported road segments.

        Returns:
            Dictionary with statistics
        """
        try:
            total_count = self.db.query(RoadSegment).count()

            # Count by road type
            road_type_counts = (
                self.db.query(RoadSegment.road_type, text("COUNT(*)"))
                .group_by(RoadSegment.road_type)
                .all()
            )

            # Count one-way roads
            one_way_count = self.db.query(RoadSegment).filter(RoadSegment.one_way == True).count()

            return {
                "total_segments": total_count,
                "road_types": {rt: count for rt, count in road_type_counts},
                "one_way_count": one_way_count,
                "two_way_count": total_count - one_way_count,
            }

        except Exception as e:
            logger.error(f"Failed to get import statistics: {str(e)}")
            return {"error": str(e)}

    def check_data_exists(self) -> bool:
        """
        Check if road segment data already exists in database.

        Returns:
            True if data exists, False otherwise
        """
        try:
            count = self.db.query(RoadSegment).count()
            return count > 0
        except Exception:
            return False

