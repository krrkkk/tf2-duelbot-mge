from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path


def _plain_python(data: bytes) -> bytes:
    text = data.decode("utf-8-sig")
    tree = ast.parse(text)
    comments = [node for node in ast.walk(tree)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    keep_pass = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            continue
        for _, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
                if all(item in comments for item in value):
                    keep_pass.add(id(value[0]))
    lines = text.encode().splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    raw = text.encode()
    for node in sorted(comments, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        start = offsets[node.lineno - 1] + node.col_offset
        end = offsets[node.end_lineno - 1] + node.end_col_offset
        segment = raw[start:end]
        replacement = bytes(10 if c == 10 else 32 for c in segment)
        own_line = not lines[node.lineno - 1][:node.col_offset].strip() and not lines[node.end_lineno - 1][node.end_col_offset:].strip()
        if id(node) in keep_pass or not own_line:
            replacement = b"pass" + replacement[4:] if len(replacement) >= 4 else b"pass"
        raw = raw[:start] + replacement + raw[end:]
    text = raw.decode()
    tokens = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT and not (token.start[0] == 1 and token.string.startswith("#!")):
            token = token._replace(string="")
        tokens.append(token)
    text = tokenize.untokenize(tokens)
    protected = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.STRING and token.end[0] > token.start[0]:
            protected.update(range(token.start[0], token.end[0] + 1))
    result = []; blank = 0
    for number, line in enumerate(text.splitlines(), 1):
        if number not in protected:
            line = line.rstrip()
            blank = blank + 1 if not line else 0
            if blank > 2:
                continue
        else:
            blank = 0
        result.append(line)
    cleaned = "\n".join(result).strip() + "\n"
    compile(cleaned, "<public source>", "exec")
    return cleaned.encode()


def public_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix == ".py":
        return _plain_python(data)
    if path.suffix in (".c", ".h"):
        text = data.decode()
        pattern = r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|//[^\n]*|/\*[\s\S]*?\*/'''
        text = re.sub(pattern, lambda m: m.group(1) if m.group(1) else "\n" * m.group().count("\n"), text)
        return (re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip() + "\n").encode()
    if path.suffix in (".yaml", ".yml"):
        return ("\n".join(line for line in data.decode().splitlines() if not line.lstrip().startswith("#")) + "\n").encode()
    return data
