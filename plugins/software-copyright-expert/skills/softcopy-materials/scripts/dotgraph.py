import re
from typing import Any
from common import DOT_LABEL_LIMIT, text_width, wrap_columns
def _strip_dot_comments(src: str) -> str:
    out: list[str] = []
    for line in src.splitlines():
        kept: list[str] = []
        quote: str | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            nxt = line[i + 1] if i + 1 < len(line) else ""
            if quote:
                kept.append(ch)
                if ch == "\\" and nxt:
                    kept.append(nxt)
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ("\"", "'"):
                quote = ch
                kept.append(ch)
                i += 1
                continue
            if ch == "/" and nxt == "/":
                break
            if ch == "/" and nxt == "*":
                break
            kept.append(ch)
            i += 1
        out.append("".join(kept))
    return "\n".join(out)
def _split_top(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("\"", "'"):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            parts.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts
def _attr_label(attrs: str | None) -> str:
    if not attrs:
        return ""
    match = re.search(r"label\s*=\s*\"((?:[^\"\\]|\\.)*)\"", attrs)
    if not match:
        return ""
    return re.sub(r"\\[nlr]", "\n", match.group(1))
def _parse_ref(part: str) -> tuple[str, str | None]:
    piece = part.strip()
    if not piece:
        return "", None
    attrs: str | None = None
    if piece.endswith("]") and "[" in piece:
        idx = piece.rfind("[")
        attrs = piece[idx:]
        piece = piece[:idx].strip()
    if piece.startswith("\""):
        inner = re.match(r"\"((?:[^\"\\]|\\.)*)\"", piece)
        if inner:
            return inner.group(1), attrs
    tokens = piece.split()
    return (tokens[0] if tokens else ""), attrs
def _statements(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("\"", "'"):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
            if ch == "}" and depth == 0:
                buf.append(ch)
                parts.append("".join(buf))
                buf = []
                i += 1
                continue
        elif ch == ";" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p for p in (part.strip() for part in parts) if p]
ATTR_STMT_RE = re.compile(r"^(?:graph|node|edge)\s*\[", re.I)
BARE_ATTR_RE = re.compile(r"^[A-Za-z_]\w*\s*=[^=]")
def parse_dot(src: str) -> dict[str, Any]:
    cleaned = _strip_dot_comments(src)
    opened = re.search(r"\b(?:strict\s+)?digraph\s+\w*\s*\{", cleaned)
    if not opened:
        raise ValueError("未找到 digraph 开头")
    body = cleaned[opened.end():]
    if body.rfind("}") >= 0:
        body = body[: body.rfind("}")]
    graph: dict[str, Any] = {"nodes": [], "edges": [], "clusters": []}
    index_of: dict[str, int] = {}
    def ensure_node(nid: str, label: str = "") -> None:
        if not nid:
            return
        if nid not in index_of:
            index_of[nid] = len(graph["nodes"])
            graph["nodes"].append({"id": nid, "label": label or nid})
        elif label:
            graph["nodes"][index_of[nid]]["label"] = label
    def walk(text: str, cluster_label: str = "") -> None:
        for stmt in _statements(text):
            brace = stmt.find("{")
            if brace >= 0 and re.match(r"^(?:subgraph\s+\S+\s*(?:\[[^\]]*\]\s*)?)?$", stmt[:brace].strip()):
                inner = stmt[brace + 1: stmt.rfind("}")] if "}" in stmt else stmt[brace + 1:]
                title_match = re.match(r'^\s*label\s*=\s*"((?:[^"\\]|\\.)*)"', inner.strip())
                title = cluster_label or (re.sub(r"\\[nlr]", "\n", title_match.group(1)) if title_match else "")
                before = len(graph["nodes"])
                walk(inner, title)
                members = [n["id"] for n in graph["nodes"][before:]]
                graph["clusters"].append({"label": title, "members": members})
                continue
            if re.match(r"^\s*label\s*=", stmt):
                continue
            if ATTR_STMT_RE.match(stmt) or BARE_ATTR_RE.match(stmt):
                continue
            if "->" in stmt:
                chain = _split_top(stmt, "->")
                src_id = ""
                for idx, piece in enumerate(chain):
                    nid, attrs = _parse_ref(piece)
                    if not nid:
                        continue
                    last = idx == len(chain) - 1
                    attr_label = _attr_label(attrs)
                    edge_label = attr_label if last else ""
                    node_label = "" if last else attr_label
                    ensure_node(nid, node_label)
                    if src_id:
                        graph["edges"].append({"src": src_id, "dst": nid, "label": edge_label})
                    src_id = nid
                continue
            nid, attrs = _parse_ref(stmt)
            if nid:
                ensure_node(nid, _attr_label(attrs))
    walk(body)
    if not graph["nodes"] and not graph["edges"]:
        raise ValueError("digraph 内未解析到任何节点或连线")
    return graph
def _layers(graph: dict[str, Any]) -> list[list[str]]:
    nodes = [n["id"] for n in graph["nodes"]]
    incoming = {nid: 0 for nid in nodes}
    outgoing: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in graph["edges"]:
        if edge["dst"] not in incoming or edge["src"] not in outgoing:
            continue
        incoming[edge["dst"]] += 1
        outgoing[edge["src"]].append(edge["dst"])
    queue = [nid for nid in nodes if incoming[nid] == 0]
    rank = {nid: 0 for nid in queue}
    while queue:
        current = queue.pop(0)
        for nxt in outgoing[current]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0 and nxt not in rank:
                rank[nxt] = rank[current] + 1
                queue.append(nxt)
    fallback = (max(rank.values()) + 1) if rank else 0
    for nid in nodes:
        if nid not in rank:
            rank[nid] = fallback
    width = max(rank.values()) + 1
    layers: list[list[str]] = [[] for _ in range(width)]
    for nid in nodes:
        layers[rank[nid]].append(nid)
    for layer in layers:
        layer.sort()
    return layers
def _label_of(graph: dict[str, Any], nid: str) -> str:
    for node in graph["nodes"]:
        if node["id"] == nid:
            return node["label"]
    return nid
def _cluster_of(graph: dict[str, Any], nid: str) -> str:
    for cluster in graph["clusters"]:
        if nid in cluster["members"] and cluster["label"]:
            return cluster["label"]
    return ""
def _wrap_label(label: str, limit: int = DOT_LABEL_LIMIT) -> list[str]:
    rows: list[str] = []
    for raw in label.split("\n"):
        rows.extend(wrap_columns(raw, limit))
    return rows or [""]
def _box(lines: list[str]) -> list[str]:
    inner = max((text_width(line) for line in lines), default=0)
    width = max(inner + 4, 8)
    top = "┌" + "─" * (width - 2) + "┐"
    bottom = "└" + "─" * (width - 2) + "┘"
    mids = ["│  " + line + " " * (width - 4 - text_width(line)) + "│" for line in lines]
    return [top, *mids, bottom]
def render_text_diagram(graph: dict[str, Any]) -> str:
    layers = _layers(graph)
    outgoing: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        outgoing.setdefault(edge["src"], set()).add(edge["dst"])
    gap = "    "
    rendered: list[str] = []
    for index, layer in enumerate(layers):
        rendered.append(f"第{index + 1}层")
        boxes = [_box(_wrap_label(_label_of(graph, nid))) for nid in layer]
        widths = [text_width(box[0]) for box in boxes]
        height = max(len(box) for box in boxes)
        for row in range(height):
            cells = [box[row] if row < len(box) else " " * widths[pos] for pos, box in enumerate(boxes)]
            rendered.append(gap.join(cells))
        if index < len(layers) - 1:
            marks: list[str] = []
            for pos, nid in enumerate(layer):
                width = widths[pos]
                if outgoing.get(nid):
                    center = width // 2
                    marks.append(" " * center + "▼" + " " * (width - center - 1))
                else:
                    marks.append(" " * width)
            rendered.append(gap.join(marks))
        rendered.append("")
    groups: list[str] = []
    for cluster in graph["clusters"]:
        if cluster["label"]:
            members = "、".join(_label_of(graph, nid).replace("\n", "") for nid in cluster["members"])
            groups.append(f"{cluster['label']}：{members}")
    if groups:
        rendered.append("分组：" + "；".join(groups))
        rendered.append("")
    rendered.append("连接关系：")
    for edge in graph["edges"]:
        src = _label_of(graph, edge["src"]).replace("\n", "")
        dst = _label_of(graph, edge["dst"]).replace("\n", "")
        mark = f"（{edge['label']}）" if edge["label"] else ""
        rendered.append(f"{src} ──{mark}──▶ {dst}")
    return "\n".join(rendered) + "\n"
def text_diagram_from_dot(src: str) -> str:
    return render_text_diagram(parse_dot(src))
