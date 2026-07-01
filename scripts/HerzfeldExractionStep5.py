import json
import logging
import os
from pathlib import Path
from uuid import uuid4

import requests
from lxml import etree

resource_counter = 0

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# URL of the XML file
XML_URL = "https://sirismm.si.edu/EADs/FSA.A.06-ead.xml"
DEFAULT_XML_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "FSA.A.06-ead.xml",
    Path(__file__).resolve().parent / "FSA.A.06-ead.xml",
    Path.cwd() / "FSA.A.06-ead.xml",
    Path.cwd() / "data" / "FSA.A.06-ead.xml",
]


def local_name(tag):
    """Return the local name of an XML tag."""
    if not isinstance(tag, str):
        return ""
    return tag.split('}')[-1] if '}' in tag else tag


def iter_matching_descendants(element, tag_name):
    """Yield all descendants matching a tag name, regardless of namespace."""
    for child in element.iter():
        if local_name(child.tag) == tag_name:
            yield child


def iter_container_elements(element, levels):
    """Yield container elements (c, c01, c02, ...) with one of the requested levels."""
    for child in element.iter():
        if child.tag is None:
            continue
        name = local_name(child.tag)
        if name.startswith("c") and child.get("level") in levels:
            yield child


def iter_series_level_resources(container, stop_at_subseries=True):
    """Yield resource containers attached directly to a container, excluding those under subseries."""
    for child in container.iterchildren():
        if child.tag is None:
            continue
        name = local_name(child.tag)
        if not name.startswith("c"):
            continue

        level = child.get("level")
        if level in {"file", "item"}:
            yield child
        elif level == "subseries" and stop_at_subseries:
            continue
        elif level:
            yield from iter_series_level_resources(child, stop_at_subseries=stop_at_subseries)


def collect_resources_for_container(container, parent_id, parent_path, stop_at_subseries=True):
    """Collect metadata for resources beneath a container, including nested non-subseries containers."""
    resources = []
    for resource_element in iter_series_level_resources(container, stop_at_subseries=stop_at_subseries):
        resource_metadata = get_resource_metadata(
            resource_element,
            parent_id,
            parent_path + [resource_element.get("id", str(uuid4()))]
        )
        resources.append(resource_metadata)
    return resources


def get_element_text(element, tag_name, default=""):
    """Get text from a descendant element, regardless of namespace."""
    for child in element.iter():
        if local_name(child.tag) == tag_name:
            text = ''.join(child.itertext()).strip()
            if text:
                return text
    return default


def extract_structured_notes(element, tag_name):
    """Extract heading and paragraph content from arrangement/scopecontent-like blocks."""
    notes = []
    for note_element in element.iter():
        if local_name(note_element.tag) != tag_name:
            continue

        headings = []
        paragraphs = []
        for child in note_element.iter():
            name = local_name(child.tag)
            if name == 'head':
                text = ''.join(child.itertext()).strip()
                if text:
                    headings.append(text)
            elif name == 'p':
                text = ''.join(child.itertext()).strip()
                if text:
                    paragraphs.append(text)

        if not headings and not paragraphs:
            text = ''.join(note_element.itertext()).strip()
            if text:
                paragraphs.append(text)

        if headings or paragraphs:
            notes.append({
                "tag": tag_name,
                "heading": headings[0] if headings else '',
                "paragraphs": paragraphs,
                "text": ' '.join(paragraphs).strip(),
                "raw_text": ''.join(note_element.itertext()).strip(),
            })

    return notes


def get_origination_data(element):
    """Extract origination data from an element."""
    element_id = element.get('id', 'unknown')
    origination_nodes = list(iter_matching_descendants(element, 'origination'))
    if not origination_nodes:
        logger.debug(f"Element {element_id}: No <origination> found")
        return {"label": "", "persons": []}

    origination = origination_nodes[0]
    origination_data = {
        "label": origination.get('label', ''),
        "persons": []
    }

    for persname in iter_matching_descendants(origination, 'persname'):
        raw_content = etree.tostring(persname, encoding='unicode', pretty_print=True).strip()
        person = {
            "name": ''.join(persname.itertext()).strip(),
            "authfilenumber": persname.get('authfilenumber', ''),
            "source": persname.get('source', '')
        }
        origination_data["persons"].append(person)
        logger.debug(f"Element {element_id}: Origination person - {person} (raw: {raw_content})")

    logger.debug(f"Element {element_id}: Found {len(origination_data['persons'])} origination persons")
    return origination_data


def get_control_access(element):
    """Extract control access information from an element."""
    element_id = element.get('id', 'unknown')
    controlaccess_nodes = list(iter_matching_descendants(element, 'controlaccess'))
    if not controlaccess_nodes:
        logger.debug(f"Element {element_id}: No <controlaccess> found")
        return []

    controlaccess = controlaccess_nodes[0]
    raw_structure = etree.tostring(controlaccess, encoding='unicode', pretty_print=True).strip()
    logger.debug(f"Element {element_id}: Raw <controlaccess> structure: {raw_structure[:500]}...")

    terms = []
    for elem in controlaccess.iter():
        name = local_name(elem.tag)
        if name not in {'persname', 'subject', 'geogname', 'genreform'}:
            continue
        term_type = name
        raw_content = etree.tostring(elem, encoding='unicode', pretty_print=True).strip()
        term = {
            "type": term_type,
            "value": ''.join(elem.itertext()).strip(),
            "altrender": elem.get('altrender', ''),
            "source": elem.get('source', ''),
            "authfilenumber": elem.get('authfilenumber', '')
        }
        terms.append(term)
        logger.debug(f"Element {element_id}: Control access term - {term} (raw: {raw_content})")

    logger.debug(f"Element {element_id}: Found {len(terms)} control access terms")
    return terms


def get_resource_metadata(resource, parent_id, path):
    """Extract metadata for a resource (file or item)."""
    resource_id = resource.get('id', str(uuid4()))
    resource_type = resource.get('level', 'unknown')
    global resource_counter

    raw_structure = etree.tostring(resource, encoding='unicode', pretty_print=True).strip()
    logger.debug(f"Resource {resource_id} (type: {resource_type}) raw structure: {raw_structure[:500]}...")

    dao_nodes = list(iter_matching_descendants(resource, 'dao'))
    dao_data = {
        "href": '',
        "title": '',
        "description": ''
    }
    has_digital = False
    if dao_nodes:
        dao = dao_nodes[0]
        dao_data["href"] = dao.get('{http://www.w3.org/1999/xlink}href', '') or dao.get('href', '')
        dao_text = get_element_text(dao, 'daodesc')
        dao_data["title"] = dao_text
        dao_data["description"] = dao_text
        logger.debug(f"Resource {resource_id}: DAO - href: {dao_data['href']}, title: {dao_data['title']}")
        has_digital = bool(dao_data["href"]) and len(dao_data["href"]) > 0

    if has_digital:
        resource_counter += 1

    metadata = {
        "id": resource_id,
        "type": resource_type,
        "has_digital_image": bool(has_digital),
        "title": get_element_text(resource, 'unittitle'),
        "unitid": get_element_text(resource, 'unitid'),
        "scopecontent": get_element_text(resource, 'scopecontent'),
        "arrangement": get_element_text(resource, 'arrangement'),
        "notes": [],
        "scopecontent_notes": [],
        "arrangement_notes": [],
        "unitdate": get_element_text(resource, 'unitdate'),
        "physdesc": get_element_text(resource, 'physdesc'),
        "origination": get_origination_data(resource),
        "control_access": get_control_access(resource),
        "dao": dao_data,
        "parent_id": parent_id,
        "path": path,
    }

    metadata["notes"] = (
        extract_structured_notes(resource, 'scopecontent') +
        extract_structured_notes(resource, 'arrangement')
    )
    metadata["scopecontent_notes"] = extract_structured_notes(resource, 'scopecontent')
    metadata["arrangement_notes"] = extract_structured_notes(resource, 'arrangement')

    if not metadata["title"]:
        metadata["title"] = metadata["unitid"] or resource_id
        logger.debug(f"Resource {resource_id} (type: {resource_type}): Title empty, using fallback: '{metadata['title']}'")

    logger.debug(f"Resource {resource_id} (type: {resource_type}) metadata: {json.dumps(metadata, indent=2)}")
    return metadata


def get_subseries_metadata(subseries, series_id, parent_path):
    """Extract enriched metadata for a subseries."""
    subseries_id = subseries.get('id', str(uuid4()))
    path = parent_path + [subseries_id]

    raw_structure = etree.tostring(subseries, encoding='unicode', pretty_print=True).strip()
    logger.debug(f"Subseries {subseries_id} raw structure: {raw_structure[:1000]}...")

    metadata = {
        "id": subseries_id,
        "title": get_element_text(subseries, 'unittitle'),
        "unitid": get_element_text(subseries, 'unitid'),
        "scopecontent": get_element_text(subseries, 'scopecontent'),
        "arrangement": get_element_text(subseries, 'arrangement'),
        "notes": [],
        "scopecontent_notes": [],
        "arrangement_notes": [],
        "unitdate": get_element_text(subseries, 'unitdate'),
        "physdesc": get_element_text(subseries, 'physdesc'),
        "origination": get_origination_data(subseries),
        "control_access": get_control_access(subseries),
        "resources": [],
        "parent_id": series_id,
        "path": path,
    }

    metadata["notes"] = (
        extract_structured_notes(subseries, 'scopecontent') +
        extract_structured_notes(subseries, 'arrangement')
    )
    metadata["scopecontent_notes"] = extract_structured_notes(subseries, 'scopecontent')
    metadata["arrangement_notes"] = extract_structured_notes(subseries, 'arrangement')

    if not metadata["title"]:
        metadata["title"] = metadata["unitid"] or subseries_id
        logger.debug(f"Subseries {subseries_id}: Title empty, using fallback: '{metadata['title']}'")

    resources = collect_resources_for_container(subseries, subseries_id, path, stop_at_subseries=True)
    logger.debug(f"Found {len(resources)} resources (files and items) in subseries {subseries_id}")
    metadata["resources"] = resources

    if not metadata["control_access"]:
        for resource in metadata["resources"]:
            metadata["control_access"].extend(resource["control_access"])
        metadata["control_access"] = list({json.dumps(term, sort_keys=True): term for term in metadata["control_access"]}.values())
        logger.debug(f"Subseries {subseries_id}: Aggregated {len(metadata['control_access'])} control access terms from resources")

    logger.debug(f"Subseries {subseries_id} metadata: {json.dumps(metadata, indent=2)}")
    return metadata


def parse_herzfeld_tree(tree):
    """Parse an in-memory EAD XML tree and extract the archival hierarchy."""
    archive = {"series": []}

    series_elements = list(iter_container_elements(tree, {'series'}))
    logger.info(f"Found {len(series_elements)} series elements")

    if not series_elements:
        series_elements = [child for child in tree.iter() if child.get('level') == 'series']
        logger.info(f"Fallback: Found {len(series_elements)} elements with level='series'")

    for series in series_elements:
        series_id = series.get('id', str(uuid4()))
        raw_structure = etree.tostring(series, encoding='unicode', pretty_print=True).strip()
        logger.debug(f"Series {series_id} raw structure: {raw_structure[:1000]}...")

        series_title = get_element_text(series, 'unittitle') or get_element_text(series, 'unitid') or series_id
        logger.debug(f"Processing series: {series_title} (ID: {series_id})")

        series_data = {
            "id": series_id,
            "title": series_title,
            "control_access": get_control_access(series),
            "scopecontent": get_element_text(series, 'scopecontent'),
            "arrangement": get_element_text(series, 'arrangement'),
            "notes": [],
            "scopecontent_notes": [],
            "arrangement_notes": [],
            "resources": [],
            "subseries": [],
            "path": [series_id],
        }

        series_data["notes"] = (
            extract_structured_notes(series, 'scopecontent') +
            extract_structured_notes(series, 'arrangement')
        )
        series_data["scopecontent_notes"] = extract_structured_notes(series, 'scopecontent')
        series_data["arrangement_notes"] = extract_structured_notes(series, 'arrangement')

        series_resources = collect_resources_for_container(series, series_id, [series_id], stop_at_subseries=True)
        series_data["resources"] = series_resources
        logger.debug(f"Found {len(series_resources)} resources directly attached to series {series_id}")

        subseries_elements = list(iter_container_elements(series, {'subseries'}))
        logger.debug(f"Found {len(subseries_elements)} subseries in series {series_id}")

        for subseries in subseries_elements:
            subseries_data = get_subseries_metadata(subseries, series_id, [series_id])
            series_data["subseries"].append(subseries_data)

        archive["series"].append(series_data)

    return archive


def parse_herzfeld_xml(xml_path=None):
    """Parse the XML file from a local path or the remote URL and extract the hierarchy."""
    if xml_path is None:
        xml_path = os.environ.get('HERZFELD_EAD_XML')

    content = None
    source_desc = ""

    if xml_path:
        xml_path = Path(xml_path)
        if xml_path.exists():
            content = xml_path.read_bytes()
            source_desc = str(xml_path)
            logger.info(f"Reading EAD XML from local file: {xml_path}")

    if content is None:
        for candidate in DEFAULT_XML_CANDIDATES:
            if candidate.exists():
                content = candidate.read_bytes()
                source_desc = str(candidate)
                logger.info(f"Reading EAD XML from local file: {candidate}")
                break

    if content is None:
        try:
            response = requests.get(XML_URL, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            content = response.content
            source_desc = XML_URL
            logger.info(f"Reading EAD XML from remote URL: {XML_URL}")
        except requests.RequestException as e:
            logger.error(f"Failed to download XML: {e}")
            return {"series": [], "source": None}

    try:
        parser = etree.XMLParser(recover=True, resolve_entities=False)
        tree = etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as e:
        logger.error(f"Failed to parse XML: {e}")
        return {"series": [], "source": source_desc}

    archive_data = parse_herzfeld_tree(tree)
    archive_data["source"] = source_desc
    return archive_data


def main():
    archive_data = parse_herzfeld_xml()

    output_path = Path(__file__).resolve().parent.parent / 'data' / 'herzfeld_archive.json'
    output_path.parent.mkdir(exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        json.dump(archive_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Extracted {len(archive_data['series'])} series")
    for series in archive_data['series']:
        logger.info(f"Series: {series['title']} (ID: {series['id']}) with {len(series['subseries'])} subseries")
        for subseries in series['subseries']:
            resource_count = len(subseries['resources'])
            logger.info(
                f"  Subseries: {subseries['title']} (ID: {subseries['id']}) "
                f"with {resource_count} resources "
                f"(UnitID: {subseries['unitid'] or 'N/A'}, "
                f"Scope: {subseries['scopecontent'][:50] + '...' if subseries['scopecontent'] else 'N/A'})"
            )


if __name__ == "__main__":
    main()
    print(f"Total resources with digital images: {resource_counter}")