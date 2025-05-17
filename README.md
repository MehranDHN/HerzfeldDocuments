# `On the Construction`...
# Herzfeld Archive Data Extraction and RDF Transformation

This repository contains tools to extract metadata from the [Ernst Herzfeld Papers](https://sova.si.edu/record/fsa.a.06), transform a subset of the data into Turtle (TTL) format using a custom ontology, and query the resulting RDF data with SPARQL. The project focuses on the archival structure of series, subseries, and resources (files and items) from the Smithsonian's Freer and Sackler Archives.
While using the Smithsonian Official API to search for IIIF resources on Ernst Herzfeld, I discovered a significant XML file. It appeared to be the primary data source for Herzfeld's documents on the Smithsonian website.
I extracted relevant data, focusing on the structure of collections, series, and subseries. This file contains well-integrated data with Wikidata, LCSH, and AAT, making it ideal for creating a Knowledge Graph to highlight key entities and their relationships. Despite the advanced technologies at the Smithsonian, including an Open Access RESTful API, they lack a machine-readable catalog.

<img src="imgsrc/image_cover.JPG" alt="Cover">

## Table of Contents
- [Project Overview](#project-overview)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
- [Ontology](#ontology)
- [Sample Data](#sample-data)
- [SPARQL Queries](#sparql-queries)
- [Contributing](#contributing)
- [License](#license)

## Project Overview
The Ernst Herzfeld Papers (FSA A.06) document the archaeological work of Ernst Herzfeld (1879–1948). This project:
1. **Extracts** metadata from the EAD XML file using Python (`extract_herzfeld_data.py`).
2. **Transforms** a subset of the JSON output into Turtle format using RDFlib (`transform_to_ttl.py`) and a custom ontology (`herzfeld_ontology.ttl`).
3. **Queries** the RDF data with SPARQL examples to retrieve specific information (e.g., resources with digital images).

The sample data focuses on subseries `ref6808` (“Ernst Herzfeld’s Sketchbooks”) with resources like `ref6809` (file) and `ref6810` (item).

## Repository Structure
```
herzfeld-rdf/
├── extract_herzfeld_data.py      # Script to extract JSON from XML
├── transform_to_ttl.py           # Script to convert JSON to Turtle
├── herzfeld_ontology.ttl         # Custom ontology for Herzfeld data
├── imgsrc                        # Images used in readme.md
├── output.ttl                    # Generated Turtle file
├── queries/
│   ├── query1.rq                 # SPARQL: List items with digital images
│   ├── query2.rq                 # SPARQL: Find resources by control access term
├── README.md                     # This file
└── LICENSE                       # MIT License
```

## Prerequisites
- Python 3.8+
- Libraries: `lxml`, `requests`, `rdflib`
- SPARQL client (e.g., `rdflib` or a triplestore like Apache Jena Fuseki)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/herzfeld-rdf.git
   cd herzfeld-rdf
   ```
2. Install dependencies:
   ```bash
   pip install lxml requests rdflib
   ```
3. (Optional) Set up a triplestore (e.g., Fuseki) for SPARQL queries:
   - Download and run Apache Jena Fuseki.
   - Load `output.ttl` into a dataset.

## Usage
1. **Extract JSON**:
   Run the extraction script to download and process the XML:
   ```bash
   python extract_herzfeld_data.py
   ```
   This generates `herzfeld_archive.json`. For testing, use `sample_data.json`.

2. **Transform to Turtle**:
   Convert the JSON to Turtle using the ontology:
   ```bash
   python transform_to_ttl.py
   ```
   This generates `output.ttl`.

3. **Run SPARQL Queries**:
   - Use `rdflib` to query `output.ttl` locally:
     ```python
     from rdflib import Graph
     g = Graph()
     g.parse("output.ttl", format="turtle")
     q = open("queries/query1.rq").read()
     results = g.query(q)
     for row in results:
         print(row)
     ```
   - Or load `output.ttl` into a triplestore and query via its SPARQL endpoint.

## Ontology
The custom ontology (`herzfeld_ontology.ttl`) defines classes and properties for the Herzfeld archive, aligned with Dublin Core and CIDOC-CRM where applicable.

### Namespace
- `mdhn: <http://example.org/archival#>`

### Classes
- `mdhn:Series`: A top-level archival series.
- `mdhn:Subseries`: A subdivision of a series.
- `mdhn:Resource`: An archival resource (subclasses: `mdhn:File`, `mdhn:Item`).
- `mdhn:DigitalObject`: A digital representation of a resource.
- `mdhn:ControlAccessTerm`: A controlled vocabulary term (e.g., geographic or genre).

### Properties
- **Object Properties**:
  - `mdhn:hasSubseries`: Links `Series` to `Subseries`.
  - `mdhn:hasResource`: Links `Subseries` to `Resource`.
  - `mdhn:hasDigitalObject`: Links `Resource` to `DigitalObject`.
  - `mdhn:controlAccess`: Links `Resource` or `Subseries` to `ControlAccessTerm`.
- **Data Properties**:
  - `mdhn:title`, `mdhn:unitid`, `mdhn:scopecontent`, `mdhn:unitdate`, `mdhn:physdesc`.
  - `mdhn:href`, `mdhn:daoTitle` (for `DigitalObject`).
  - `mdhn:termType`, `mdhn:termValue`, `mdhn:altrender`, `mdhn:source`, `mdhn:authfilenumber` (for `ControlAccessTerm`).

### Example
```turtle
@prefix mdhn: <http://example.org/archival#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .

mdhn:ref6808 a mdhn:Subseries ;
    dc:title "Ernst Herzfeld's Sketchbooks" ;
    mdhn:unitid "2" ;
    mdhn:hasResource herz:ref6809 .

mdhn:ref6809 a mdhn:File ;
    dc:title "SK-I Persien" ;
    mdhn:unitid "FSA A.06 02.01.01" ;
    mdhn:hasDigitalObject mdhn:dao_ref6809 ;
    mdhn:controlAccess mdhn:ca_persepolis .

mdhn:dao_ref6809 a mdhn:DigitalObject ;
    mdhn:href "https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.06_02.01.01" ;
    mdhn:daoTitle "Excavation of Persepolis (Iran): Sketchbook" .

herz:ca_persepolis a herz:ControlAccessTerm ;
    mdhn:termType "geogname" ;
    mdhn:termValue "Persepolis (Iran)" .
```

## Sample Data
The `sample_data.json` file contains a subset of the Herzfeld archive for testing:
- **Subseries**: `ref6808` (“Ernst Herzfeld’s Sketchbooks”).
- **Resources**:
  - `ref6809` (file): A sketchbook with a digital object.
  - `ref6810` (item): A sketch with a digital image.
- **Fields**: Includes `title`, `unitid`, `control_access` (e.g., “Persepolis (Iran)”), and `dao` (URLs and descriptions).

Example snippet:
```json
{
  "series": [
    {
      "id": "ref6807",
      "title": "Sketchbooks",
      "subseries": [
        {
          "id": "ref6808",
          "title": "Ernst Herzfeld's Sketchbooks",
          "unitid": "2",
          "resources": [
            {
              "id": "ref6809",
              "type": "file",
              "title": "SK-I Persien",
              "unitid": "FSA A.06 02.01.01",
              "control_access": [
                {
                  "type": "geogname",
                  "value": "Persepolis (Iran)",
                  "altrender": "geographic",
                  "source": "lcsh",
                  "authfilenumber": ""
                }
              ],
              "dao": {
                "href": "https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.06_02.01.01",
                "title": "Excavation of Persepolis (Iran): Sketchbook",
                "description": "Excavation of Persepolis (Iran): Sketchbook"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

## SPARQL Queries
The `queries/` directory contains example SPARQL queries to explore the RDF data.

### Query 1: List Items with Digital Images
File: `queries/query1.rq`
```sparql
PREFIX herz: <http://example.org/herzfeld#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?item ?title ?href
WHERE {
  ?item a herz:Item ;
        dc:title ?title ;
        herz:hasDigitalObject ?dao .
  ?dao herz:href ?href .
}
```

**Example Result**:
```
?item: herz:ref6810
?title: "SK-II Persien"
?href: "https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.06_02.01.02"
```

### Query 2: Find Resources by Control Access Term
File: `queries/query2.rq`
```sparql
PREFIX herz: <http://example.org/herzfeld#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?resource ?title ?termValue
WHERE {
  ?resource a herz:Resource ;
            dc:title ?title ;
            herz:controlAccess ?term .
  ?term herz:termValue ?termValue .
  FILTER(?termValue = "Persepolis (Iran)")
}
```

**Example Result**:
```
?resource: herz:ref6809
?title: "SK-I Persien"
?termValue: "Persepolis (Iran)"
```

## Contributing
Contributions are welcome! Please:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit changes (`git commit -m 'Add your feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

*Developed by MehranDHN. For questions, contact [mehrandhn@gmail.com].*
