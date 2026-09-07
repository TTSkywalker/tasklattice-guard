"""Source-preserving Colang linking using the pinned NeMo grammar's ranges."""
from __future__ import annotations

import json
import re
from ast import literal_eval

from lark import Tree
from nemoguardrails.colang.v2_x.lang.parser import ColangParser

from .domain import PlanCompilationError
from ..nemo.actions.names import ACTION_RECORD_POLICY, ACTION_RECORD_OWNED_POLICY


def parse_source_tree(content: str) -> tuple[str, Tree]:
    parser = ColangParser()
    # Use the same NeMo expansion as parse_content so ranges and execution agree.
    content = parser._apply_pre_parsing_expansions(content)
    return content, parser.get_parsing_tree(content)


def symbol_name(node: Tree) -> str:
    return " ".join(str(token) for token in node.scan_values(lambda value: not isinstance(value, Tree)))


def expand_policy_parameters(content: str, parameters: tuple[tuple[str, str], ...]) -> str:
    """Interpolate parameters as literal string data, never Colang source.

    Unicode escapes survive NeMo's expression/interpolation pre-processing and
    are decoded only when its string expression is evaluated. In particular,
    raw dollars/braces would otherwise be treated as variables/expressions.
    Substitute once so parameter values cannot introduce more placeholders.
    """
    placeholder = re.compile(r"\$\{([^{}\r\n]+)\}")
    if not placeholder.search(content):
        return content
    try:
        content, tree = parse_source_tree(content)
    except Exception as error:
        raise PlanCompilationError(
            "Policy parameter placeholders must occur inside quoted strings in valid Colang."
        ) from error
    values = dict(parameters)

    def replacement(match: re.Match) -> str:
        name = match.group(1)
        if name not in values:
            raise PlanCompilationError(f"Missing Policy parameter {name!r}.")
        # Escape both quote styles, including triple-quoted author strings.
        encoded = json.dumps(values[name], ensure_ascii=True)[1:-1]
        encoded = encoded.replace('\\"', r"\u0022")
        for character in "'$}{":
            encoded = encoded.replace(character, f"\\u{ord(character):04x}")
        return encoded

    edits = []
    for node in tree.iter_subtrees():
        if node.data not in {"string", "doc_string"}:
            continue
        start, end = node.meta.start_pos, node.meta.end_pos
        original = content[start:end]
        if placeholder.search(original):
            edits.append((start, end, placeholder.sub(replacement, original)))
    for start, end, value in sorted(edits, reverse=True):
        content = content[:start] + value + content[end:]
    return content


def link_policy_source(content: str, tree: Tree, replacements: dict[str, str], *, policy_id: str, version: str) -> str:
    edits: list[tuple[int, int, str]] = []
    for parent in tree.iter_subtrees():
        if parent.data not in {"flow_def", "spec"}:
            continue
        node = next((child for child in parent.children if isinstance(child, Tree) and child.data == "spec_name"), None)
        if node is None:
            continue
        name = symbol_name(node)
        # Match NeMo's SpecType classification: uppercase specs are Actions or
        # events, even if an author also declares a similarly named Flow.
        if name in replacements and (parent.data == "flow_def" or name.islower()):
            edits.append((node.meta.start_pos, node.meta.end_pos, replacements[name]))
    # Core is already imported once by the generated entrypoint. Import nodes,
    # unlike line regexes, cannot include lookalike text inside string literals.
    for node in tree.find_data("import_stmt"):
        target = node.children[0]
        raw = content[target.meta.start_pos:target.meta.end_pos]
        imported = literal_eval(raw) if target.data == "string" else raw
        if imported != "core":
            raise PlanCompilationError(f"Policy {policy_id!r} uses forbidden import {imported!r}.")
        edits.append((node.meta.start_pos, node.meta.end_pos, ""))
    for node in tree.find_data("spec"):
        name = next((child for child in node.children if isinstance(child, Tree) and child.data == "spec_name"), None)
        if name is None or symbol_name(name) != ACTION_RECORD_POLICY:
            continue
        edits.append((name.meta.start_pos, name.meta.end_pos, ACTION_RECORD_OWNED_POLICY))
        args = next((child for child in node.children if isinstance(child, Tree)
            and child.data in {"classic_arguments", "simple_arguments"}), None)
        if args is not None:
            for argument in args.children:
                if isinstance(argument, Tree) and argument.data == "expr":
                    raise PlanCompilationError(f"Policy {policy_id!r}: RecordPolicy requires named arguments.")
                if not isinstance(argument, Tree) or argument.data not in {"argvalue", "simple_argvalue"}:
                    continue
                first = argument.children[0]
                if not isinstance(first, Tree) or first.data not in {"name", "var_name"}:
                    raise PlanCompilationError(f"Policy {policy_id!r}: RecordPolicy requires named arguments.")
                if isinstance(first, Tree) and first.data in {"name", "var_name"}:
                    key = content[first.meta.start_pos:first.meta.end_pos].lstrip("$")
                    if key in {"policy_id", "policy_version"}:
                        raise PlanCompilationError(f"Policy {policy_id!r} uses compiler-owned RecordPolicy argument {key!r}.")
        scope = {"policy_id": policy_id, "policy_version": str(version)}
        if args is not None and args.data == "simple_arguments":
            position = args.meta.end_pos
            suffix = "".join(f" ${key}={json.dumps(value)}" for key, value in scope.items())
        else:
            suffix = ", ".join(f"{key}={json.dumps(value)}" for key, value in scope.items())
            if args is None:
                position = name.meta.end_pos
                suffix = f"({suffix})"
            else:
                position = args.meta.end_pos - 1
                if content[args.meta.start_pos + 1:position].strip():
                    suffix = ", " + suffix
        edits.append((position, position, suffix))
    for start, end, replacement in sorted(edits, reverse=True):
        content = content[:start] + replacement + content[end:]
    return content
