"""OSM XML/JSON parser and transformer."""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RoadSegmentData:
    """Road segment data structure."""

    osm_id: int
    geom_coordinates: List[Tuple[float, float]]  # List of (lat, lng) tuples
    road_type: Optional[str] = None
    speed_limit: Optional[int] = None
    one_way: bool = False


class OSMParser:
    """Parser for OSM XML data."""

    # Highway type to road_type mapping
    HIGHWAY_TYPE_MAPPING = {
        "motorway": "motorway",
        "trunk": "trunk",
        "primary": "primary",
        "secondary": "secondary",
        "tertiary": "tertiary",
        "residential": "residential",
        "service": "service",
        "unclassified": "unclassified",
        "living_street": "residential",
        "pedestrian": "service",
        "footway": "service",
        "path": "service",
    }

    # Common speed limit mappings (km/h)
    SPEED_LIMIT_MAPPING = {
        "motorway": 120,
        "trunk": 110,
        "primary": 90,
        "secondary": 70,
        "tertiary": 50,
        "residential": 30,
        "service": 20,
        "unclassified": 50,
    }

    def __init__(self, bbox: Optional[Tuple[float, float, float, float]] = None):
        """
        Initialize OSM parser.

        Args:
            bbox: Optional bounding box for filtering (min_lat, min_lng, max_lat, max_lng)
        """
        self.bbox = bbox

    def parse_xml(self, xml_data: str) -> List[RoadSegmentData]:
        """
        Parse OSM XML data and extract road segments.

        Args:
            xml_data: OSM XML data as string

        Returns:
            List of RoadSegmentData objects
        """
        try:
            root = ET.fromstring(xml_data)
            logger.info(f"Parsing OSM XML with {len(root)} elements")

            # Extract nodes first (for way coordinates)
            nodes: Dict[int, Tuple[float, float]] = {}
            for node in root.findall("node"):
                node_id = int(node.get("id"))
                lat = float(node.get("lat"))
                lon = float(node.get("lon"))
                nodes[node_id] = (lat, lon)

            # Extract ways (road segments)
            road_segments: List[RoadSegmentData] = []
            for way in root.findall("way"):
                way_id = int(way.get("id"))
                road_segment = self._parse_way(way, way_id, nodes)
                if road_segment:
                    road_segments.append(road_segment)

            logger.info(f"Parsed {len(road_segments)} road segments from OSM data")
            return road_segments

        except ET.ParseError as e:
            logger.error(f"Failed to parse OSM XML: {str(e)}")
            raise ValueError(f"Invalid OSM XML data: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error parsing OSM data: {str(e)}")
            raise

    def _parse_way(
        self, way: ET.Element, way_id: int, nodes: Dict[int, Tuple[float, float]]
    ) -> Optional[RoadSegmentData]:
        """
        Parse a single OSM way element.

        Args:
            way: OSM way element
            way_id: Way ID
            nodes: Dictionary of node_id -> (lat, lon)

        Returns:
            RoadSegmentData or None if invalid
        """
        # Extract tags
        tags = {}
        for tag in way.findall("tag"):
            key = tag.get("k")
            value = tag.get("v")
            if key and value:
                tags[key] = value

        # Check if it's a highway
        highway_type = tags.get("highway")
        if not highway_type:
            return None

        # Map highway type
        road_type = self.HIGHWAY_TYPE_MAPPING.get(highway_type, highway_type)

        # Extract coordinates from nd (node) references
        coordinates: List[Tuple[float, float]] = []
        for nd in way.findall("nd"):
            node_id = int(nd.get("ref"))
            if node_id in nodes:
                coordinates.append(nodes[node_id])

        # Validate coordinates
        if len(coordinates) < 2:
            logger.debug(f"Way {way_id} has less than 2 coordinates, skipping")
            return None

        # Filter by bbox if provided (bbox is used for initial filtering)
        # Final filtering will be done by polygon in the importer
        if self.bbox:
            min_lat, min_lng, max_lat, max_lng = self.bbox
            # Check if any coordinate is within bbox
            in_bbox = any(
                min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
                for lat, lng in coordinates
            )
            if not in_bbox:
                return None

        # Extract speed limit
        speed_limit = self._extract_speed_limit(tags, road_type)

        # Extract one-way information
        one_way = self._extract_one_way(tags)

        return RoadSegmentData(
            osm_id=way_id,
            geom_coordinates=coordinates,
            road_type=road_type,
            speed_limit=speed_limit,
            one_way=one_way,
        )

    def _extract_speed_limit(self, tags: Dict[str, str], road_type: str) -> Optional[int]:
        """
        Extract speed limit from tags.

        Args:
            tags: OSM tags dictionary
            road_type: Road type

        Returns:
            Speed limit in km/h or None
        """
        # Try maxspeed tag first
        maxspeed = tags.get("maxspeed")
        if maxspeed:
            try:
                # Handle various formats: "50", "50 km/h", "50kph", etc.
                maxspeed_clean = maxspeed.lower().replace("km/h", "").replace("kph", "").strip()
                # Extract numbers
                import re

                numbers = re.findall(r"\d+", maxspeed_clean)
                if numbers:
                    return int(numbers[0])
            except (ValueError, AttributeError):
                pass

        # Fallback to default based on road type
        return self.SPEED_LIMIT_MAPPING.get(road_type)

    def _extract_one_way(self, tags: Dict[str, str]) -> bool:
        """
        Extract one-way information from tags.

        Args:
            tags: OSM tags dictionary

        Returns:
            True if one-way, False otherwise
        """
        oneway = tags.get("oneway", "no").lower()
        return oneway in ("yes", "true", "1", "-1")

    def validate_geometry(self, coordinates: List[Tuple[float, float]]) -> bool:
        """
        Validate geometry coordinates.

        Args:
            coordinates: List of (lat, lng) tuples

        Returns:
            True if valid, False otherwise
        """
        if len(coordinates) < 2:
            return False

        # Check coordinate ranges
        for lat, lng in coordinates:
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return False

        # Check for duplicate consecutive points
        for i in range(len(coordinates) - 1):
            if coordinates[i] == coordinates[i + 1]:
                return False

        return True

