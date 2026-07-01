import hashlib
import json
import os
import re
from pathlib import Path
from rdflib import Graph, Namespace, Literal, BNode
from rdflib.namespace import RDF, RDFS, SKOS
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY_PATH = ROOT / 'HezfeldOntology.ttl'
OUTPUT_PATH = ROOT / 'data' / 'herzfeld_rdfdata_v2.ttl'
XML_URL = 'https://sirismm.si.edu/EADs/FSA.A.06-ead.xml'
DEFAULT_XML_CANDIDATES = [
    ROOT / 'FSA.A.06-ead.xml',
    ROOT / 'data' / 'FSA.A.06-ead.xml',
    Path.cwd() / 'FSA.A.06-ead.xml',
    Path.cwd() / 'data' / 'FSA.A.06-ead.xml',
]

ARCH = Namespace('http://example.org/archival#')
SCHEMA = Namespace('http://schema.org/')


def safe_text(value):
    if value is None:
        return Literal('')
    return Literal(str(value))


def add_note(g, subject, note):
    note_node = BNode()
    g.add((subject, ARCH.hasNote, note_node))
    g.add((note_node, RDF.type, ARCH.Note))
    if note.get('heading'):
        g.add((note_node, ARCH.noteHeading, Literal(note['heading'])))
    if note.get('text'):
        g.add((note_node, ARCH.noteText, Literal(note['text'])))
    if note.get('tag'):
        g.add((note_node, ARCH.noteType, Literal(note['tag'])))


def slugify(value):
    value = re.sub(r'[^A-Za-z0-9]+', '-', str(value or '').strip().lower())
    return value.strip('-') or 'term'


def concept_iri(term):
    seed = '|'.join([
        term.get('value', ''),
        term.get('type', ''),
        term.get('source', ''),
        term.get('authfilenumber', ''),
    ])
    digest = hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]
    label = slugify(term.get('value') or term.get('authfilenumber') or digest)
    return ARCH[f'concept-{label}-{digest}']


def add_control_access(g, subject, terms):
    for term in terms or []:
        concept = concept_iri(term)
        g.add((subject, ARCH.hasControlAccessTerm, concept))
        g.add((concept, RDF.type, SKOS.Concept))
        g.add((concept, SKOS.prefLabel, Literal(term.get('value', ''))))
        if term.get('type'):
            g.add((concept, ARCH.termType, Literal(term['type'])))
        if term.get('source'):
            g.add((concept, ARCH.termSource, Literal(term['source'])))
        if term.get('authfilenumber'):
            g.add((concept, ARCH.termIdentifier, Literal(term['authfilenumber'])))


def add_digital_object(g, subject, dao):
    if not dao or not dao.get('href'):
        return
    digital_node = BNode()
    g.add((subject, ARCH.hasDigitalObject, digital_node))
    g.add((digital_node, RDF.type, ARCH.DigitalObject))
    g.add((digital_node, ARCH.hasDigitalImage, Literal(True)))
    g.add((digital_node, SCHEMA.url, Literal(dao['href'])))
    if dao.get('title'):
        g.add((digital_node, SCHEMA.name, Literal(dao['title'])))
    if dao.get('description'):
        g.add((digital_node, SCHEMA.description, Literal(dao['description'])))


def local_name(tag):
    if not isinstance(tag, str):
        return ''
    return tag.split('}')[-1] if '}' in tag else tag


def iter_matching_descendants(element, tag_name):
    for child in element.iter():
        if local_name(child.tag) == tag_name:
            yield child


def get_element_text(element, tag_name, default=''):
    for child in element.iter():
        if local_name(child.tag) == tag_name:
            text = ''.join(child.itertext()).strip()
            if text:
                return text
    return default


def extract_structured_notes(element, tag_name):
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
                'tag': tag_name,
                'heading': headings[0] if headings else '',
                'paragraphs': paragraphs,
                'text': ' '.join(paragraphs).strip(),
                'raw_text': ''.join(note_element.itertext()).strip(),
            })
    return notes


def get_control_access_terms(element):
    terms = []
    controlaccess_nodes = list(iter_matching_descendants(element, 'controlaccess'))
    if not controlaccess_nodes:
        return terms
    for elem in controlaccess_nodes[0].iter():
        name = local_name(elem.tag)
        if name not in {'persname', 'subject', 'geogname', 'genreform'}:
            continue
        terms.append({
            'type': name,
            'value': ''.join(elem.itertext()).strip(),
            'altrender': elem.get('altrender', ''),
            'source': elem.get('source', ''),
            'authfilenumber': elem.get('authfilenumber', ''),
        })
    return terms


def get_dao(resource):
    dao_nodes = list(iter_matching_descendants(resource, 'dao'))
    if not dao_nodes:
        return {}
    dao = dao_nodes[0]
    return {
        'href': dao.get('{http://www.w3.org/1999/xlink}href', '') or dao.get('href', ''),
        'title': get_element_text(dao, 'daodesc'),
        'description': get_element_text(dao, 'daodesc'),
    }


def iter_container_elements(element, levels):
    for child in element.iter():
        if child.tag is None:
            continue
        name = local_name(child.tag)
        if name.startswith('c') and child.get('level') in levels:
            yield child


def iter_resource_elements(container):
    for child in container.iterchildren():
        if child.tag is None:
            continue
        name = local_name(child.tag)
        if not name.startswith('c'):
            continue
        level = child.get('level')
        if level in {'file', 'item'}:
            yield child
        elif level:
            yield from iter_resource_elements(child)


def build_graph(tree):
    g = Graph()
    g.parse(str(ONTOLOGY_PATH), format='turtle')

    for series in iter_container_elements(tree, {'series'}):
        series_id = series.get('id', 'series')
        series_uri = ARCH[series_id]
        g.add((series_uri, RDF.type, ARCH.Series))
        g.add((series_uri, RDFS.label, Literal(get_element_text(series, 'unittitle') or series_id)))
        g.add((series_uri, ARCH.unitid, safe_text(series_id)))
        if get_element_text(series, 'scopecontent'):
            g.add((series_uri, ARCH.scopecontent, Literal(get_element_text(series, 'scopecontent'))))
        if get_element_text(series, 'arrangement'):
            g.add((series_uri, ARCH.arrangement, Literal(get_element_text(series, 'arrangement'))))
        for note in extract_structured_notes(series, 'scopecontent') + extract_structured_notes(series, 'arrangement'):
            add_note(g, series_uri, note)
        add_control_access(g, series_uri, get_control_access_terms(series))

        for subseries in iter_container_elements(series, {'subseries'}):
            sub_id = subseries.get('id', 'subseries')
            sub_uri = ARCH[sub_id]
            g.add((sub_uri, RDF.type, ARCH.Subseries))
            g.add((sub_uri, RDFS.label, Literal(get_element_text(subseries, 'unittitle') or sub_id)))
            g.add((sub_uri, ARCH.unitid, safe_text(get_element_text(subseries, 'unitid'))))
            g.add((sub_uri, ARCH.isPartOfSeries, series_uri))
            if get_element_text(subseries, 'scopecontent'):
                g.add((sub_uri, ARCH.scopecontent, Literal(get_element_text(subseries, 'scopecontent'))))
            if get_element_text(subseries, 'arrangement'):
                g.add((sub_uri, ARCH.arrangement, Literal(get_element_text(subseries, 'arrangement'))))
            for note in extract_structured_notes(subseries, 'scopecontent') + extract_structured_notes(subseries, 'arrangement'):
                add_note(g, sub_uri, note)
            add_control_access(g, sub_uri, get_control_access_terms(subseries))

            for resource in iter_resource_elements(subseries):
                res_id = resource.get('id', 'resource')
                res_uri = ARCH[res_id]
                g.add((res_uri, RDF.type, ARCH.Resource))
                g.add((res_uri, RDFS.label, Literal(get_element_text(resource, 'unittitle') or res_id)))
                g.add((res_uri, ARCH.unitid, safe_text(get_element_text(resource, 'unitid'))))
                g.add((res_uri, ARCH.isPartOfSubseries, sub_uri))
                if get_element_text(resource, 'scopecontent'):
                    g.add((res_uri, ARCH.scopecontent, Literal(get_element_text(resource, 'scopecontent'))))
                if get_element_text(resource, 'arrangement'):
                    g.add((res_uri, ARCH.arrangement, Literal(get_element_text(resource, 'arrangement'))))
                for note in extract_structured_notes(resource, 'scopecontent') + extract_structured_notes(resource, 'arrangement'):
                    add_note(g, res_uri, note)
                add_control_access(g, res_uri, get_control_access_terms(resource))
                dao = get_dao(resource)
                add_digital_object(g, res_uri, dao)
                g.add((res_uri, ARCH.hasDigitalImage, Literal(bool(dao.get('href')))))

    return g


def load_xml_tree():
    xml_path = os.environ.get('HERZFELD_EAD_XML')
    if xml_path:
        path = Path(xml_path)
        if path.exists():
            return etree.parse(str(path)).getroot()

    for candidate in DEFAULT_XML_CANDIDATES:
        if candidate.exists():
            return etree.parse(str(candidate)).getroot()

    import requests
    response = requests.get(XML_URL, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    return etree.fromstring(response.content)


def main():
    tree = load_xml_tree()
    g = build_graph(tree)
    OUTPUT_PATH.write_text(g.serialize(format='turtle'), encoding='utf-8')
    print(f'Wrote {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
