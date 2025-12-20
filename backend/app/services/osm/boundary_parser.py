"""OSM boundary parser for extracting polygon from OSM relation data."""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BoundaryParser:
    """Parser for OSM boundary/relation data."""

    def parse_boundary_xml(self, xml_data: str) -> Optional[List[List[Tuple[float, float]]]]:
        """
        Parse OSM XML and extract boundary polygon coordinates.

        Args:
            xml_data: OSM XML data as string

        Returns:
            List of polygon rings (outer ring + holes), each ring is a list of (lat, lng) tuples
            Returns None if parsing fails
        """
        try:
            root = ET.fromstring(xml_data)
            logger.info(f"Parsing OSM boundary XML with {len(root)} elements")

            # Extract nodes first
            nodes: Dict[int, Tuple[float, float]] = {}
            for node in root.findall("node"):
                node_id = int(node.get("id"))
                lat = float(node.get("lat"))
                lon = float(node.get("lon"))
                nodes[node_id] = (lat, lon)

            # Find relation with boundary=administrative
            relations = root.findall("relation")
            boundary_relation = None
            for relation in relations:
                tags = {tag.get("k"): tag.get("v") for tag in relation.findall("tag")}
                if tags.get("boundary") == "administrative":
                    boundary_relation = relation
                    break

            if not boundary_relation:
                logger.warning("No administrative boundary relation found")
                return None

            # Extract outer way (main boundary)
            outer_ways = []
            inner_ways = []  # Holes in the polygon

            for member in boundary_relation.findall("member"):
                role = member.get("role")
                member_type = member.get("type")
                member_ref = int(member.get("ref"))

                if member_type == "way":
                    # Find the way element
                    way = root.find(f"way[@id='{member_ref}']")
                    if way is None:
                        continue

                    # Extract coordinates
                    coordinates = []
                    for nd in way.findall("nd"):
                        node_id = int(nd.get("ref"))
                        if node_id in nodes:
                            coordinates.append(nodes[node_id])

                    if len(coordinates) >= 3:  # At least 3 points for a polygon
                        if role == "outer" or role is None:
                            outer_ways.append(coordinates)
                        elif role == "inner":
                            inner_ways.append(coordinates)

            if not outer_ways:
                logger.warning("No outer ways found in boundary relation")
                return None

            # Combine outer ways into a single polygon
            # For simplicity, use the first outer way (largest one)
            # In production, you might want to merge multiple outer ways
            polygon_rings = [outer_ways[0]]

            # Add inner ways as holes
            polygon_rings.extend(inner_ways)

            logger.info(f"Parsed boundary with {len(polygon_rings)} rings ({len(outer_ways)} outer, {len(inner_ways)} inner)")
            return polygon_rings

        except ET.ParseError as e:
            logger.error(f"Failed to parse OSM XML: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing boundary: {str(e)}")
            return None

    def coordinates_to_wkt(
        self, coordinates: List[Tuple[float, float]], close_ring: bool = True
    ) -> str:
        """
        Convert coordinates to WKT format.

        Args:
            coordinates: List of (lat, lng) tuples
            close_ring: If True, ensure ring is closed (first point = last point)

        Returns:
            WKT string for POLYGON
        """
        if len(coordinates) < 3:
            raise ValueError("Polygon must have at least 3 points")

        # Close ring if needed
        if close_ring and coordinates[0] != coordinates[-1]:
            coordinates = coordinates + [coordinates[0]]

        # Convert to WKT format: (lng lat, lng lat, ...)
        # Note: WKT uses (lng lat) order, not (lat lng)
        coords_str = ", ".join([f"{lng} {lat}" for lat, lng in coordinates])
        return f"POLYGON(({coords_str}))"

