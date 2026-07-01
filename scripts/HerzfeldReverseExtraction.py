import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from lxml import etree
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, OWL, XSD, SKOS

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

LOCAL_XML = r"C:\Users\Mehran\HerzfeldDocuments-1\data\FSA.A.06-ead.xml"

MDHN = Namespace("http://example.org/mdhn/herzfeld#")
SCHEMA = Namespace("http://schema.org/")

class HerzfeldReverseExtractor:
    def __init__(self):
        self.g = Graph()
        self.control_terms = {}
        self.series_map = {}
        self.subseries_map = {}
        self.setup_ontology()
        self.item_counter = 0
        self.digital_counter = 0

    def setup_ontology(self):
        self.g.bind("mdhn", MDHN)
        self.g.bind("schema", SCHEMA)
        self.g.bind("skos", SKOS)
        self.g.add((MDHN.ArchivalOntology, RDF.type, OWL.Ontology))
        self.g.add((MDHN.Series, RDF.type, OWL.Class))
        self.g.add((MDHN.Subseries, RDF.type, OWL.Class))
        self.g.add((MDHN.Resource, RDF.type, OWL.Class))
        self.g.add((MDHN.DigitalObject, RDF.type, OWL.Class))

        # Hierarchy properties
        self.g.add((MDHN.hasResource, RDF.type, OWL.ObjectProperty))
        self.g.add((MDHN.hasResource, RDFS.domain, MDHN.Subseries))
        self.g.add((MDHN.hasResource, RDFS.range, MDHN.Resource))
        self.g.add((MDHN.hasResource, RDFS.subPropertyOf, SCHEMA.hasPart))
        self.g.add((MDHN.hasResource, OWL.inverseOf, MDHN.isPartOfSubseries))

        self.g.add((MDHN.hasSubseries, RDF.type, OWL.ObjectProperty))
        self.g.add((MDHN.hasSubseries, RDFS.domain, MDHN.Series))
        self.g.add((MDHN.hasSubseries, RDFS.range, MDHN.Subseries))
        self.g.add((MDHN.hasSubseries, RDFS.subPropertyOf, SCHEMA.hasPart))
        self.g.add((MDHN.hasSubseries, OWL.inverseOf, MDHN.isPartOfSeries))

        self.g.add((MDHN.isPartOfSeries, RDF.type, OWL.ObjectProperty))
        self.g.add((MDHN.isPartOfSubseries, RDF.type, OWL.ObjectProperty))
        self.g.add((MDHN.IIIFManifest, RDF.type, OWL.DatatypeProperty))
        self.g.add((MDHN.hasDigitalImage, RDF.type, OWL.DatatypeProperty))
        self.g.add((MDHN.controlAccess, RDF.type, OWL.ObjectProperty))

    def get_text(self, element, tag):
        for el in element.iter():
            if el.tag.endswith(tag):
                text = ''.join(el.itertext()).strip()
                if text:
                    return text
        return ""

    def get_control_term(self, value):
        if not value: return None
        key = re.sub(r'[^a-zA-Z0-9]', '_', value.strip().lower())[:60]
        if key not in self.control_terms:
            term_uri = MDHN[key]
            self.g.add((term_uri, RDF.type, SKOS.Concept))
            self.g.add((term_uri, SKOS.prefLabel, Literal(value.strip(), lang="en")))
            self.control_terms[key] = term_uri
        return self.control_terms[key]

    def parse_and_process(self):
        tree = etree.parse(LOCAL_XML)
        logger.info("XML loaded.")

        # Series
        for series in tree.xpath("//*[local-name()='c'][@level='series']"):
            sid = series.get('id') or f"series_{uuid4().hex[:8]}"
            s_uri = MDHN[f"ref{sid}"]
            self.series_map[sid] = s_uri
            self.g.add((s_uri, RDF.type, MDHN.Series))
            title = self.get_text(series, 'unittitle') or "Untitled Series"
            self.g.add((s_uri, RDFS.label, Literal(title, lang="en")))
            self.g.add((s_uri, SCHEMA.name, Literal(title, lang="en")))
            for term in self.extract_control_access(series):
                self.g.add((s_uri, MDHN.controlAccess, term))

        # Subseries
        for sub in tree.xpath("//*[local-name()='c'][@level='subseries']"):
            sid = sub.get('id') or f"sub_{uuid4().hex[:8]}"
            s_uri = MDHN[f"ref{sid}"]
            self.subseries_map[sid] = s_uri
            self.g.add((s_uri, RDF.type, MDHN.Subseries))
            title = self.get_text(sub, 'unittitle') or "Untitled Subseries"
            self.g.add((s_uri, RDFS.label, Literal(title, lang="en")))
            self.g.add((s_uri, SCHEMA.name, Literal(title, lang="en")))
            for term in self.extract_control_access(sub):
                self.g.add((s_uri, MDHN.controlAccess, term))

            # Link to parent series
            parent = sub.getparent()
            while parent is not None:
                if parent.get('level') == 'series':
                    pid = parent.get('id')
                    if pid and pid in self.series_map:
                        self.g.add((s_uri, MDHN.isPartOfSeries, self.series_map[pid]))
                    break
                parent = parent.getparent()

        # Resources
        items = tree.xpath("//*[local-name()='c'][@level='item' or @level='file']")
        for item in items:
            item_id = item.get('id') or f"item_{uuid4().hex[:8]}"
            resource_uri = MDHN[f"ref{item_id}"]

            self.g.add((resource_uri, RDF.type, MDHN.Resource))

            title = self.get_text(item, 'unittitle') or self.get_text(item, 'unitid') or "Untitled"
            self.g.add((resource_uri, RDFS.label, Literal(title, lang="en")))
            self.g.add((resource_uri, SCHEMA.name, Literal(title, lang="en")))
            self.g.add((resource_uri, SCHEMA.description, Literal(title, lang="en")))

            if unitid := self.get_text(item, 'unitid'):
                self.g.add((resource_uri, MDHN.unitid, Literal(unitid)))
            if unitdate := self.get_text(item, 'unitdate'):
                self.g.add((resource_uri, MDHN.unitdate, Literal(unitdate)))
            if physdesc := self.get_text(item, 'physdesc'):
                self.g.add((resource_uri, MDHN.physdesc, Literal(physdesc)))
            if scope := self.get_text(item, 'scopecontent'):
                self.g.add((resource_uri, MDHN.scopecontent, Literal(scope)))

            for term in self.extract_control_access(item):
                self.g.add((resource_uri, MDHN.controlAccess, term))

            # Hierarchy link
            parent = item.getparent()
            while parent is not None:
                level = parent.get('level')
                pid = parent.get('id')
                if level == 'subseries' and pid and pid in self.subseries_map:
                    self.g.add((resource_uri, MDHN.isPartOfSubseries, self.subseries_map[pid]))
                    self.g.add((self.subseries_map[pid], MDHN.hasResource, resource_uri))
                    break
                elif level == 'series' and pid and pid in self.series_map:
                    self.g.add((resource_uri, MDHN.isPartOfSeries, self.series_map[pid]))
                    break
                parent = parent.getparent()

            # DAO + IIIFManifest
            has_digital = False
            for dao in item.xpath(".//*[local-name()='dao']"):
                href = dao.get('{http://www.w3.org/1999/xlink}href') or dao.get('href') or ""
                if 'ids.si.edu' in href:
                    has_digital = True
                    self.digital_counter += 1
                    self.g.add((resource_uri, SCHEMA.url, URIRef(href)))
                    item_id_extracted = self.extract_id_from_href(href)
                    manifest_url = f"https://ids.si.edu/ids/manifest/{item_id_extracted}"
                    self.g.add((resource_uri, MDHN.IIIFManifest, Literal(manifest_url)))
                    break

            self.g.add((resource_uri, MDHN.hasDigitalImage, Literal(has_digital, datatype=XSD.boolean)))

            self.item_counter += 1
            if self.item_counter % 2000 == 0:
                logger.info(f"Processed {self.item_counter} items...")

        output_dir = Path(r"C:\Users\Mehran\HerzfeldDocuments-1\data")
        output_dir.mkdir(exist_ok=True)
        self.g.serialize(output_dir / "herzfeld_rdfdata_updated.ttl", format="turtle", encoding="utf-8")
        logger.info(f"✅ Full hierarchical RDF generated with Series, Subseries, and Resources.")

    def extract_control_access(self, element):
        terms = []
        for el in element.iter():
            if el.tag.endswith(('subject', 'geogname', 'persname', 'corpname', 'genreform')):
                value = ''.join(el.itertext()).strip()
                if value:
                    term = self.get_control_term(value)
                    if term:
                        terms.append(term)
        return terms

    def extract_id_from_href(self, href):
        match = re.search(r'id=([^\s&]+)', href)
        return match.group(1) if match else ""

if __name__ == "__main__":
    extractor = HerzfeldReverseExtractor()
    extractor.parse_and_process()
    print(f"🎉 Complete! Hierarchical structure with Series, Subseries, Resources, and IIIFManifest ready.")