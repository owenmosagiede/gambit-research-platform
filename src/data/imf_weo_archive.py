"""Original IMF WEO inflation parsers, preserving each edition's actual-status evidence."""
import csv
import io
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path


class ArchiveBytes(io.BytesIO):
    def read_bytes(self):
        return self.getvalue()


CURRENCIES = dict(zip(
    'AUD CAD CHF CNH CZK EUR GBP HKD HUF ILS JPY MXN NOK NZD PLN SEK SGD USD ZAR'.split(),
    'AUS CAN CHE CHN CZE G163 GBR HKG HUN ISR JPN MEX NOR NZL POL SWE SGP USA ZAF'.split(),
    strict=True,
))

COUNTRIES = {entity: currency for currency, entity in CURRENCIES.items()}

IMF_CODES = dict(zip(
    CURRENCIES.values(),
    '193 156 146 924 935 163 112 532 944 436 158 273 142 196 964 144 576 111 199'.split(),
    strict=True,
))

SDMX_ENTITIES = {value: key for key, value in IMF_CODES.items()}

INDICATOR = 'PCPIPCH'

XLSX_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def legacy_series(path, archive_year, is_group):
    raw = path.read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    elif b'\0' in raw[:32]:
        text = raw.decode('utf-16-le')
    else:
        text = raw.decode('cp1252')
    rows = csv.DictReader(io.StringIO(text), delimiter='\t')
    identity = 'WEO Country Group Code' if is_group else 'ISO'
    if not {identity, 'WEO Subject Code'} <= set(rows.fieldnames or []):
        raise ValueError(f'Unrecognized IMF archive: {path}')
    for row in rows:
        entity = 'G163' if is_group and row[identity] == '163' else row[identity]
        if row['WEO Subject Code'] != INDICATOR or entity not in COUNTRIES:
            continue
        actual = row.get('Estimates Start After', '')
        if is_group and not actual:
            actual = str(archive_year - 1)  # IMF group-level convention.
            evidence = 'IMF_group_convention'
        else:
            evidence = 'IMF_estimates_start_after'
        yield entity, actual, row, evidence

def workbook_series(path, published):
    with zipfile.ZipFile(path) as workbook:
        strings = [''.join(part.text or '' for part in row.iter(XLSX_NS + 't'))
                   for row in ET.fromstring(workbook.read('xl/sharedStrings.xml'))]
        for number in (2, 3):
            with workbook.open(f'xl/worksheets/sheet{number}.xml') as sheet:
                names = None
                for _, element in ET.iterparse(sheet, events=('end',)):
                    if element.tag != XLSX_NS + 'row':
                        continue
                    cells = {}
                    for cell in element.iter(XLSX_NS + 'c'):
                        value = cell.findtext(XLSX_NS + 'v')
                        if value is not None:
                            column = re.sub(r'\d+$', '', cell.attrib['r'])
                            cells[column] = strings[int(value)] if cell.get('t') == 's' else value
                    element.clear()
                    if names is None:
                        names = cells
                        if not {'LATEST_ACTUAL_ANNUAL_DATA', 'COUNTRY.ID', 'INDICATOR.ID'} <= set(names.values()):
                            raise ValueError('WEO workbook data layout changed')
                        continue
                    if cells.get('E') != INDICATOR:
                        continue
                    row = {names[key]: value for key, value in cells.items()}
                    entity = row['COUNTRY.ID']
                    if entity in COUNTRIES:
                        if row['PUBLICATION_DATE'][:10] != published:
                            raise ValueError(f'Incorrect WEO edition publication date: {entity}')
                        yield entity, row.get('LATEST_ACTUAL_ANNUAL_DATA', ''), row, 'IMF_latest_actual_annual_data'

def sdmx_series(path, edition):
    year, month = edition.split('-')
    with zipfile.ZipFile(path) as archive:
        names = [member for member in archive.infolist()
                 if re.fullmatch(fr'(?:weo(?:_pub_)?|xmlfile_){month}{year}\.xml', Path(member.filename).name, re.I)]
        if len(names) != 1 or names[0].file_size > 40_000_000:
            raise ValueError(f'Unexpected WEO SDMX archive members: {edition}')
        member = names[0]
        try:
            raw = archive.read(member)  # Verify the central directory CRC normally.
        except zipfile.BadZipFile:
            # Two original publisher archives have a stale central directory.
            # The local member header binds the complete stream independently.
            package = path.read_bytes()
            header = struct.unpack_from('<IHHHHHIIIHH', package, member.header_offset)
            signature, _, flags, compression, _, _, checksum, packed, length, name_len, extra_len = header
            filename_start = member.header_offset + 30
            offset = filename_start + name_len + extra_len
            if (signature != 0x04034B50 or flags != 0 or compression != zipfile.ZIP_DEFLATED
                    or not 0 < length <= 40_000_000 or offset + packed > len(package)
                    or package[filename_start:filename_start + name_len] != member.filename.encode('ascii')):
                raise ValueError(f'Invalid original IMF ZIP member: {edition}')
            inflater = zlib.decompressobj(-15)
            raw = inflater.decompress(package[offset:offset + packed], length + 1)
            if len(raw) != length or zlib.crc32(raw) != checksum or not inflater.eof or inflater.unused_data:
                raise ValueError(f'Original IMF local CRC or length failed: {edition}')
    prepared = None
    sender = None
    matched = set()
    for _, node in ET.iterparse(io.BytesIO(raw), events=('end',)):
        name = node.tag.rsplit('}', 1)[-1]
        if name == 'Prepared':
            prepared = node.text
        if name == 'Sender':
            sender = node.get('id')
        if name != 'Series':
            continue
        entity = SDMX_ENTITIES.get(node.get('REF_AREA'))
        if entity and node.get('FREQ') == 'A' and node.get('CONCEPT') == INDICATOR:
            if entity in matched:
                raise ValueError(f'Duplicate WEO annual inflation series: {edition} {entity}')
            matched.add(entity)
            actual = node.get('LASTACTUALDATE', '')
            evidence = 'IMF_sdmx_last_actual_date'
            if entity == 'G163' and not actual.isdigit():
                actual = str(int(year) - 1)
                evidence = 'IMF_group_convention'
            values = {child.attrib['TIME_PERIOD']: child.attrib['OBS_VALUE'] for child in node
                      if 'TIME_PERIOD' in child.attrib and 'OBS_VALUE' in child.attrib}
            yield entity, actual, values, evidence
        node.clear()
    if sender != 'IMF' or prepared is None or not prepared.startswith(year) or matched != set(COUNTRIES):
        raise ValueError(f'IMF SDMX edition metadata or currency coverage differs: {edition}')
