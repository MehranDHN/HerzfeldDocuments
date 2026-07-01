import importlib.util
import os
import tempfile

spec = importlib.util.spec_from_file_location('step5', 'scripts/HerzfeldExractionStep5.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

xml = '''<ead><archdesc><dsc><c level="series" id="s1"><did><unittitle>Series One</unittitle></did><c level="subseries" id="ss1"><did><unittitle>Sub One</unittitle></did><c level="file" id="f1"><did><unittitle>File One</unittitle><unitid>U1</unitid></did><dao href="https://example.com/img.jpg"><daodesc>Image</daodesc></dao><controlaccess><subject>Foo</subject></controlaccess></c></c></dsc></archdesc></ead>'''

with tempfile.NamedTemporaryFile('w', suffix='.xml', delete=False, encoding='utf-8') as fh:
    fh.write(xml)
    path = fh.name

try:
    data = mod.parse_herzfeld_xml(path)
    print('series', data['series'][0]['title'])
    print('subseries', data['series'][0]['subseries'][0]['title'])
    print('resource', data['series'][0]['subseries'][0]['resources'][0]['dao']['href'])
finally:
    os.unlink(path)
