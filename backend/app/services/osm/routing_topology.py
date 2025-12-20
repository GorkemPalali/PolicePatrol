"""pgRouting topology creation and management."""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class RoutingTopology:
    """Service for creating and managing pgRouting topology."""

    def __init__(self, db: Session, tolerance: float = 0.0001):
        """
        Initialize routing topology service.

        Args:
            db: Database session
            tolerance: Topology tolerance in degrees (default: 0.0001 ~ 11 meters)
        """
        self.db = db
        self.tolerance = tolerance

    def create_topology(self, force_recreate: bool = False) -> Dict[str, any]:
        """
        Create pgRouting topology for road_segment table.

        Args:
            force_recreate: If True, drop existing topology before creating

        Returns:
            Dictionary with topology creation results
        """
        try:
            # Check if pgRouting extension exists
            if not self._check_pgrouting_extension():
                logger.error("pgRouting extension not found")
                return {
                    "success": False,
                    "error": "pgRouting extension not installed",
                }

            # Check if road_segment table has data
            segment_count = self.db.execute(
                text("SELECT COUNT(*) FROM road_segment")
            ).scalar()
            if segment_count == 0:
                logger.warning("No road segments found, skipping topology creation")
                return {
                    "success": False,
                    "error": "No road segments found",
                    "segment_count": 0,
                }

            logger.info(f"Creating topology for {segment_count} road segments...")

            # Update costs first
            self._update_costs()

            # Drop existing topology if force_recreate
            if force_recreate:
                logger.info("Dropping existing topology...")
                self._drop_topology()

            # Create topology
            logger.info(f"Creating topology with tolerance {self.tolerance}...")
            result = self.db.execute(
                text("""
                    SELECT pgr_createTopology(
                        'road_segment',
                        :tolerance,
                        'geom',
                        'id',
                        'source',
                        'target',
                        rows_where := 'true'
                    )
                """),
                {"tolerance": self.tolerance},
            )
            topology_result = result.scalar()

            if topology_result:
                logger.info(f"Topology created successfully: {topology_result}")
            else:
                logger.warning("Topology creation returned no result")

            # Validate topology
            validation = self._validate_topology()

            return {
                "success": True,
                "segment_count": segment_count,
                "tolerance": self.tolerance,
                "topology_result": str(topology_result),
                "validation": validation,
            }

        except Exception as e:
            logger.error(f"Failed to create topology: {str(e)}")
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
            }

    def _check_pgrouting_extension(self) -> bool:
        """Check if pgRouting extension is installed."""
        try:
            result = self.db.execute(
                text("""
                    SELECT EXISTS(
                        SELECT 1 FROM pg_extension WHERE extname = 'pgrouting'
                    )
                """)
            ).scalar()
            return result
        except Exception:
            return False

    def _update_costs(self) -> None:
        """Update cost and reverse_cost for all road segments."""
        try:
            logger.info("Updating road segment costs...")
            self.db.execute(
                text("""
                    UPDATE road_segment
                    SET cost = ST_Length(geom::geometry),
                        reverse_cost = CASE 
                            WHEN one_way THEN 1e9
                            ELSE ST_Length(geom::geometry)
                        END
                    WHERE cost IS NULL OR reverse_cost IS NULL
                """)
            )
            self.db.commit()
            logger.info("Costs updated successfully")
        except Exception as e:
            logger.error(f"Failed to update costs: {str(e)}")
            raise

    def _drop_topology(self) -> None:
        """Drop existing topology (reset source and target columns)."""
        try:
            self.db.execute(
                text("""
                    UPDATE road_segment
                    SET source = NULL, target = NULL
                """)
            )
            self.db.commit()
            logger.info("Topology dropped (source/target columns reset)")
        except Exception as e:
            logger.error(f"Failed to drop topology: {str(e)}")
            raise

    def _validate_topology(self) -> Dict[str, any]:
        """
        Validate created topology.

        Returns:
            Dictionary with validation results
        """
        try:
            # Count segments with source/target
            stats = self.db.execute(
                text("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(source) as with_source,
                        COUNT(target) as with_target,
                        COUNT(CASE WHEN source IS NOT NULL AND target IS NOT NULL THEN 1 END) as connected
                    FROM road_segment
                """)
            ).first()

            total = stats[0] if stats else 0
            with_source = stats[1] if stats else 0
            with_target = stats[2] if stats else 0
            connected = stats[3] if stats else 0

            connection_rate = (connected / total * 100) if total > 0 else 0

            return {
                "total_segments": total,
                "segments_with_source": with_source,
                "segments_with_target": with_target,
                "connected_segments": connected,
                "connection_rate_percent": round(connection_rate, 2),
            }

        except Exception as e:
            logger.error(f"Failed to validate topology: {str(e)}")
            return {"error": str(e)}

    def refresh_topology(self) -> Dict[str, any]:
        """
        Refresh topology (recreate from scratch).

        Returns:
            Dictionary with refresh results
        """
        logger.info("Refreshing routing topology...")
        return self.create_topology(force_recreate=True)

    def get_topology_status(self) -> Dict[str, any]:
        """
        Get current topology status.

        Returns:
            Dictionary with topology status information
        """
        try:
            # Check if topology exists
            has_topology = self.db.execute(
                text("""
                    SELECT COUNT(*) > 0
                    FROM road_segment
                    WHERE source IS NOT NULL OR target IS NOT NULL
                """)
            ).scalar()

            if not has_topology:
                return {
                    "has_topology": False,
                    "message": "No topology created yet",
                }

            # Get topology statistics
            validation = self._validate_topology()

            return {
                "has_topology": True,
                "tolerance": self.tolerance,
                **validation,
            }

        except Exception as e:
            logger.error(f"Failed to get topology status: {str(e)}")
            return {
                "has_topology": False,
                "error": str(e),
            }

