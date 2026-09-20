"""Discover physical document structure without interpreting financial meaning.

Offsets are half-open Python string offsets; lines and table coordinates are
one-based. ``grid`` expands merged cells using IDs, while ``cells`` contains
each original physical cell exactly once. No numeric repair or row joining is
performed here. Separate page tables remain separate evidence blocks.
"""
from bisect import bisect_right
from hashlib import sha256
from html.parser import HTMLParser
import re


VERSION = 'document-map-v1'
_ATX = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$')
_SETEXT = re.compile(r'^ {0,3}(=+|-+)\s*$')
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')


def _line_starts(text):
    return [0] + [m.end() for m in re.finditer('\n', text)]


def _id(*parts):
    return sha256(':'.join(str(part) for part in parts).encode()).hexdigest()[:32]


def _fenced_ranges(text):
    ranges, opened, offset = [], None, 0
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line)
        if match:
            marker = match[1]
            if opened is None:
                opened = (offset, marker[0], len(marker))
            elif marker[0] == opened[1] and len(marker) >= opened[2] and not line[match.end():].strip():
                ranges.append((opened[0], offset + len(line)))
                opened = None
        offset += len(line)
    if opened:
        ranges.append((opened[0], len(text)))
    return ranges


class _Tables(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text, self.starts, self.depth, self.spans = text, _line_starts(text), 0, []
        self.opened = 0

    def source_offset(self):
        line, column = self.getpos()
        return self.starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            if not self.depth:
                self.opened = self.source_offset()
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == 'table' and self.depth:
            self.depth -= 1
            if not self.depth:
                end = self.text.find('>', self.source_offset()) + 1
                self.spans.append((self.opened, end, 'html', []))


class _Cells(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text, self.starts = text, _line_starts(text)
        self.depth, self.rows, self.active, self.issues = 0, [], None, []

    def source_offset(self):
        line, column = self.getpos()
        return self.starts[line - 1] + column

    def finish_cell(self, end, unclosed=False):
        if self.active is not None:
            self.active.update(end_offset=end, text=''.join(self.active.pop('parts')).strip())
            self.rows[-1].append(self.active)
            self.active = None
            if unclosed:
                self.issues.append('unclosed_cell')

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth > 1:
                self.issues.append('nested_table')
            return
        if self.depth != 1:
            return
        if tag == 'tr':
            self.finish_cell(self.source_offset(), True)
            self.rows.append([])
        elif tag in ('td', 'th'):
            self.finish_cell(self.source_offset(), True)
            if not self.rows:
                self.rows.append([])
                self.issues.append('cell_without_row')
            attributes = dict(attrs)
            spans = {}
            for name in ('rowspan', 'colspan'):
                raw = attributes.get(name, '1') or '1'
                if not raw.isdigit() or not 1 <= int(raw) <= 1000:
                    self.issues.append('invalid_' + name)
                    spans[name] = 1
                else:
                    spans[name] = int(raw)
            self.active = dict(start_offset=self.source_offset(), parts=[], is_header=tag == 'th', **spans)
        elif tag == 'br' and self.active is not None:
            self.active['parts'].append('\n')

    def handle_data(self, data):
        if self.depth == 1 and self.active is not None:
            self.active['parts'].append(data)

    def handle_endtag(self, tag):
        if tag == 'table':
            if self.depth == 1:
                self.finish_cell(self.source_offset(), True)
            self.depth = max(0, self.depth - 1)
        elif self.depth == 1 and tag in ('td', 'th'):
            self.finish_cell(self.text.find('>', self.source_offset()) + 1)
        elif self.depth == 1 and tag == 'tr':
            self.finish_cell(self.source_offset(), True)


def _pipe_cells(line):
    """Return literal cell spans, ignoring escaped pipes and inline code pipes."""
    edges, index, code = [], 0, 0
    while index < len(line):
        char = line[index]
        if char == '\\':
            index += 2
            continue
        if char == '`':
            end = index + 1
            while end < len(line) and line[end] == '`':
                end += 1
            run = end - index
            if not code:
                code = run
            elif run == code:
                code = 0
            index = end
            continue
        if char == '|' and not code:
            edges.append(index)
        index += 1
    if not edges:
        return []
    spans = list(zip([0] + [n + 1 for n in edges], edges + [len(line.rstrip('\r\n'))]))
    if not line[:edges[0]].strip():
        spans.pop(0)
    if not line[edges[-1] + 1:].strip():
        spans.pop()
    return [(start, end, line[start:end]) for start, end in spans]


def _markdown_tables(text, excluded):
    lines, starts = text.splitlines(keepends=True), _line_starts(text)
    spans, index = [], 0
    while index + 1 < len(lines):
        if any(start <= starts[index] < end for start, end in excluded):
            index += 1
            continue
        header, separator = _pipe_cells(lines[index]), _pipe_cells(lines[index + 1])
        if not header or len(header) != len(separator) or not all(re.fullmatch(r'\s*:?-{3,}:?\s*', cell[2]) for cell in separator):
            index += 1
            continue
        end = index + 2
        while end < len(lines) and not any(a <= starts[end] < b for a, b in excluded) and len(_pipe_cells(lines[end])) == len(header):
            end += 1
        stop = starts[end] if end < len(lines) else len(text)
        spans.append((starts[index], stop, 'markdown', []))
        index = end
    return spans


def _table_cells(block, line_starts):
    text = block['text']
    if block['format'] == 'html':
        parser = _Cells(text)
        parser.feed(text)
        parser.close()
        parser.finish_cell(len(text), True)
        physical_rows = parser.rows
        block['issues'].extend(parser.issues)
    else:
        physical_rows, offset = [], 0
        for index, line in enumerate(text.splitlines(keepends=True)):
            if index != 1:  # Keep the Markdown delimiter in source, not the grid.
                physical_rows.append([dict(text=raw.strip().replace('\\|', '|'), start_offset=offset + start, end_offset=offset + end, rowspan=1, colspan=1, is_header=index == 0) for start, end, raw in _pipe_cells(line)])
            offset += len(line)
    occupied, cells, width = {}, [], 0
    height = len(physical_rows)
    for row_number, physical_row in enumerate(physical_rows, 1):
        column = 1
        for cell in physical_row:
            while (row_number, column) in occupied:
                column += 1
            cell.update(row=row_number, column=column)
            cell['raw'] = text[cell['start_offset']:cell['end_offset']]
            cell['start_offset'] += block['start_offset']
            cell['end_offset'] += block['start_offset']
            cell['start_line'] = bisect_right(line_starts, cell['start_offset'])
            cell['end_line'] = bisect_right(line_starts, max(cell['start_offset'], cell['end_offset'] - 1))
            cell['id'] = _id(block['id'], cell['start_offset'], cell['end_offset'])
            cells.append(cell)
            if row_number + cell['rowspan'] - 1 > height:
                block['issues'].append('rowspan_outside_table')
            for row in range(row_number, min(height + 1, row_number + cell['rowspan'])):
                for col in range(column, column + cell['colspan']):
                    if (row, col) in occupied:
                        block['issues'].append('overlapping_cells')
                    else:
                        occupied[row, col] = cell
            width = max(width, column + cell['colspan'] - 1)
            column += cell['colspan']
    block['cells'] = cells
    block['rows'] = [[occupied[row, column]['text'] if (row, column) in occupied else '' for column in range(1, width + 1)] for row in range(1, height + 1)]
    block['grid'] = [[occupied[row, column]['id'] if (row, column) in occupied else None for column in range(1, width + 1)] for row in range(1, height + 1)]
    block['header_rows'] = [i for i, row in enumerate(physical_rows, 1) if row and all(cell['is_header'] for cell in row)]
    block['issues'] = list(dict.fromkeys(block['issues']))


def build_document_map(markdown: str) -> dict:
    """Build immutable physical evidence blocks and a lightweight discovery map.

    The map deliberately contains no inferred entity, period, scope, unit,
    accounting concept, statement category, or cross-page continuation link.
    Those decisions belong to semantic interpretation above this layer.
    """
    if not isinstance(markdown, str):
        raise TypeError('markdown_must_be_text')
    digest, starts = sha256(markdown.encode()).hexdigest(), _line_starts(markdown)
    fences = _fenced_ranges(markdown)
    masked = list(markdown)
    for begin, end in fences:
        masked[begin:end] = ['\n' if char == '\n' else ' ' for char in markdown[begin:end]]
    parser = _Tables(''.join(masked))
    parser.feed(''.join(masked))
    parser.close()
    if parser.depth:
        parser.spans.append((parser.opened, len(markdown), 'html', ['unclosed_table']))
    table_spans = parser.spans + _markdown_tables(markdown, fences + [(a, b) for a, b, _, _ in parser.spans])
    table_spans.sort()
    headings, blocks = [], []

    def add(begin, end, kind, **extra):
        if begin >= end:
            return
        block = dict(id=_id(VERSION, digest, begin, end), kind=kind, start_line=bisect_right(starts, begin), end_line=bisect_right(starts, max(begin, end - 1)), start_offset=begin, end_offset=end, text=markdown[begin:end], headings=[dict(h) for h in headings], **extra)
        blocks.append(block)
        return block

    def prose(begin, end):
        lines = markdown[begin:end].splitlines(keepends=True)
        offset, pending, index = begin, begin, 0
        while index < len(lines):
            line = lines[index]
            title = _ATX.match(line.rstrip('\r\n'))
            underline = _SETEXT.match(lines[index + 1].rstrip('\r\n')) if index + 1 < len(lines) and line.strip() else None
            fenced = any(a <= offset < b for a, b in fences)
            if not fenced and (title or underline):
                add(pending, offset, 'text')
                level, name = (len(title[1]), re.sub(r'[ \t]+#+[ \t]*$', '', title[2])) if title else (1 if underline[1][0] == '=' else 2, line.strip())
                while headings and headings[-1]['level'] >= level:
                    headings.pop()
                headings.append(dict(level=level, text=name, line=bisect_right(starts, offset)))
                stop = offset + len(line)
                if not title:
                    stop += len(lines[index + 1])
                    index += 1
                add(offset, stop, 'heading')
                offset = pending = stop
            else:
                offset += len(line)
                if not line.strip() and not fenced:
                    add(pending, offset, 'text')
                    pending = offset
            index += 1
        add(pending, end, 'text')

    cursor = 0
    for begin, end, format_name, issues in table_spans:
        prose(cursor, begin)
        block = add(begin, end, 'table', format=format_name, issues=list(issues))
        block['before'] = '\n'.join(markdown[:begin].splitlines()[-6:])[-2000:]
        block['after'] = '\n'.join(markdown[end:].splitlines()[:6])[:2000]
        _table_cells(block, starts)
        cursor = end
    prose(cursor, len(markdown))
    light = []
    for block in blocks:
        if not block['text'].strip():
            continue
        entry = {key: block[key] for key in ('id', 'kind', 'start_line', 'end_line', 'headings')}
        entry['preview'] = block['text'][:1000]
        if block['kind'] == 'table':
            entry.update(format=block['format'], row_count=len(block['rows']), column_count=len(block['rows'][0]) if block['rows'] else 0, header_rows=block['header_rows'], before=block['before'], after=block['after'], issues=block['issues'])
        light.append(entry)
    return dict(version=VERSION, markdown_sha256=digest, blocks=blocks, map=light)


def get_cell(document_map: dict, block_id: str, row: int, column: int) -> dict:
    """Resolve a one-based grid coordinate to its original physical cell.

    Covered positions of merged cells resolve to the same origin and ID.
    Missing cells and invalid coordinates are errors, never zero/empty facts.
    """
    if type(row) is not int or type(column) is not int or min(row, column) < 1:
        raise ValueError('invalid_cell_coordinate')
    block = next((block for block in document_map['blocks'] if block['id'] == block_id and block['kind'] == 'table'), None)
    if block is None:
        raise ValueError('table_block_not_found')
    try:
        cell_id = block['grid'][row - 1][column - 1]
    except IndexError as exc:
        raise ValueError('cell_not_found') from exc
    if cell_id is None:
        raise ValueError('cell_not_found')
    cell = next(cell for cell in block['cells'] if cell['id'] == cell_id)
    return dict(cell, block_id=block_id)
