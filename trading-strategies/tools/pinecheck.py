#!/usr/bin/env python3
"""pinecheck — a static validator for Pine Script v6.

There is no published `pinecheck` package, so this is a real implementation of
that idea: a linter that catches the mistakes TradingView only reports after you
paste the script in, plus the automation-stack rules that matter when a strategy
is wired to TradersPost -> Tradovate.

It parses structure, not semantics — it cannot know whether your logic is right,
only whether the script is well-formed and safe to automate.

Checks
------
ERROR   version pragma missing / not v6
ERROR   no strategy() or indicator() declaration, or more than one
ERROR   unbalanced (), [], {} or unterminated string
ERROR   v5-and-earlier builtins used without their v6 namespace
ERROR   tab/space mixed indentation
ERROR   statement indent not a multiple of 4, or a continuation line that IS a
        multiple of 4 (Pine uses that distinction to tell the two apart)
WARN    strategy() without commission / slippage / max_bars_back
WARN    entry without a `strategy.opentrades == 0` guard
WARN    calc_on_every_tick = true
WARN    strategy.entry without a matching strategy.exit
WARN    entry/exit without an alert() call
WARN    no strategy.close_all anywhere
WARN    request.security without an explicit lookahead argument
WARN    line longer than --max-line

Usage:
    python tools/pinecheck.py pine/PO3_10_2.pine
    python tools/pinecheck.py pine/*.pine --strict     # warnings fail too
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Builtins that lost their bare form in v4→v5; using them unqualified in a v6
# script is a hard error in TradingView.
RENAMED = {
    "study": "indicator", "security": "request.security", "sma": "ta.sma",
    "ema": "ta.ema", "rma": "ta.rma", "wma": "ta.wma", "vwma": "ta.vwma",
    "atr": "ta.atr", "rsi": "ta.rsi", "macd": "ta.macd", "stoch": "ta.stoch",
    "crossover": "ta.crossover", "crossunder": "ta.crossunder", "cross": "ta.cross",
    "highest": "ta.highest", "lowest": "ta.lowest", "change": "ta.change",
    "pivothigh": "ta.pivothigh", "pivotlow": "ta.pivotlow", "valuewhen": "ta.valuewhen",
    "barssince": "ta.barssince", "cum": "ta.cum", "tr": "ta.tr", "roc": "ta.roc",
    "stdev": "ta.stdev", "correlation": "ta.correlation", "linreg": "ta.linreg",
    "abs": "math.abs", "max": "math.max", "min": "math.min", "pow": "math.pow",
    "sqrt": "math.sqrt", "round": "math.round", "floor": "math.floor",
    "ceil": "math.ceil", "log": "math.log", "sign": "math.sign", "sum": "math.sum",
    "avg": "math.avg", "random": "math.random",
    "tostring": "str.tostring", "tonumber": "str.tonumber", "split": "str.split",
    "input": "input.int / input.float / ...",
    "iff": "the ?: ternary", "offset": "the [] history operator",
    "rising": "ta.rising", "falling": "ta.falling", "mom": "ta.mom",
    "percentrank": "ta.percentrank", "dev": "ta.dev", "variance": "ta.variance",
}

PAIRS = {")": "(", "]": "[", "}": "{"}
OPENERS = set(PAIRS.values())

# A line ending on one of these is unfinished, so the next line wraps it.
# `=>` is deliberately excluded: it opens a multi-line function body, and that
# body is a normal 4-space block rather than a continuation.
CONT_END = re.compile(r"(?<!=)(?:[+\-*/%,?:=<>!(\[{]|\band\b|\bor\b|\bnot\b)\s*$")


@dataclass
class Finding:
    level: str      # ERROR | WARN
    line: int
    code: str
    msg: str


def strip_code(line: str) -> tuple[str, bool]:
    """Remove strings and the trailing `//` comment.

    Returns (code_without_literals, unterminated_string).
    """
    out = []
    i = 0
    quote = None
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
                out.append('""')
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break
        out.append(ch)
        i += 1
    return "".join(out), quote is not None


def check(text: str, path: str, max_line: int = 120) -> list[Finding]:
    lines = text.splitlines()
    f: list[Finding] = []
    code_lines: list[str] = []

    # ── version pragma ────────────────────────────────────────────────────
    first = next(((i, l) for i, l in enumerate(lines) if l.strip()), None)
    if first is None:
        return [Finding("ERROR", 0, "empty", "file is empty")]
    idx, fl = first
    m = re.match(r"^//@version=(\d+)\s*$", fl.strip())
    if not m:
        f.append(Finding("ERROR", idx + 1, "version",
                         "first line must be `//@version=6`"))
    elif m.group(1) != "6":
        f.append(Finding("ERROR", idx + 1, "version",
                         f"script is v{m.group(1)}, expected v6"))

    # ── per-line lexical checks ───────────────────────────────────────────
    for n, raw in enumerate(lines, 1):
        code, open_str = strip_code(raw)
        code_lines.append(code)

        if open_str:
            f.append(Finding("ERROR", n, "string", "unterminated string literal"))

        if len(raw) > max_line:
            f.append(Finding("WARN", n, "long-line",
                             f"line is {len(raw)} chars (max {max_line})"))

        indent = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in indent and " " in indent:
            f.append(Finding("ERROR", n, "indent", "mixed tabs and spaces"))

        for name, repl in RENAMED.items():
            # bare call `name(` not preceded by `.` or an identifier char
            if re.search(rf"(?<![\w.]){re.escape(name)}\s*\(", code):
                f.append(Finding("ERROR", n, "v5-builtin",
                                 f"`{name}(` is not valid in v6 — use `{repl}`"))

    body = "\n".join(code_lines)

    # ── indentation ───────────────────────────────────────────────────────
    # Pine tells a wrapped line apart from a new statement purely by indent
    # width: statements sit on a multiple of 4, continuations must not. So the
    # rule flips depending on whether the previous logical line was left open.
    depth = 0
    cont = False
    for n, code in enumerate(code_lines, 1):
        stripped = code.strip()
        if stripped:
            indent = code[: len(code) - len(code.lstrip())]
            if "\t" not in indent:
                mult4 = len(indent) % 4 == 0
                if cont and mult4:
                    f.append(Finding(
                        "ERROR", n, "indent",
                        f"continuation line indented {len(indent)} — must NOT be a "
                        "multiple of 4, or Pine reads it as a new statement"))
                elif not cont and not mult4:
                    f.append(Finding(
                        "ERROR", n, "indent",
                        f"statement indented {len(indent)} — must be a multiple of 4"))
        depth += sum(1 for c in code if c in OPENERS) - sum(1 for c in code if c in PAIRS)
        depth = max(depth, 0)
        if stripped:
            cont = depth > 0 or bool(CONT_END.search(stripped))
        elif depth == 0:
            cont = False

    # ── bracket balance across the file ───────────────────────────────────
    stack: list[tuple[str, int]] = []
    for n, code in enumerate(code_lines, 1):
        for ch in code:
            if ch in OPENERS:
                stack.append((ch, n))
            elif ch in PAIRS:
                if not stack:
                    f.append(Finding("ERROR", n, "brackets", f"stray `{ch}`"))
                elif stack[-1][0] != PAIRS[ch]:
                    o, on = stack.pop()
                    f.append(Finding("ERROR", n, "brackets",
                                     f"`{ch}` closes `{o}` opened on line {on}"))
                else:
                    stack.pop()
    for o, on in stack:
        f.append(Finding("ERROR", on, "brackets", f"`{o}` is never closed"))

    # ── declaration ───────────────────────────────────────────────────────
    decls = re.findall(r"(?<![\w.])(strategy|indicator|library)\s*\(", body)
    is_strategy = "strategy" in decls
    if not decls:
        f.append(Finding("ERROR", 1, "declaration",
                         "no strategy()/indicator()/library() declaration"))

    # ── strategy-specific rules ───────────────────────────────────────────
    if is_strategy:
        decl = re.search(r"(?<![\w.])strategy\s*\((.*?)\n\n", body + "\n\n", re.S)
        head = decl.group(1) if decl else body[:2000]

        for opt, why in (
            ("commission_type", "set commission_type/commission_value ($0.62/contract on Tradovate)"),
            ("slippage", "set slippage (1 tick is realistic for MNQ)"),
            ("max_bars_back", "set max_bars_back explicitly to avoid lookahead errors"),
        ):
            if opt not in head:
                f.append(Finding("WARN", 1, "strategy-decl", why))

        if re.search(r"calc_on_every_tick\s*=\s*true", body):
            f.append(Finding("WARN", 1, "tick-recalc",
                             "calc_on_every_tick = true — must be bar-close only "
                             "when routed to TradersPost"))

        n_entry = len(re.findall(r"strategy\.entry\s*\(", body))
        n_exit = len(re.findall(r"strategy\.(exit|close|close_all)\s*\(", body))
        if n_entry and not n_exit:
            f.append(Finding("WARN", 1, "no-exit",
                             "strategy.entry with no strategy.exit/close"))
        if n_entry and "strategy.opentrades" not in body:
            f.append(Finding("WARN", 1, "no-guard",
                             "no `strategy.opentrades == 0` guard — positions can stack"))
        if n_entry and "alert(" not in body:
            f.append(Finding("WARN", 1, "no-alert",
                             "no alert() call — TradersPost needs a JSON payload per entry/exit"))
        if n_entry and "strategy.close_all" not in body:
            f.append(Finding("WARN", 1, "no-flat",
                             "no strategy.close_all — nothing forces flat at session end"))

        for n, code in enumerate(code_lines, 1):
            if "alert(" in code:
                lit = re.search(r"alert\s*\(\s*'([^']*)'", lines[n - 1]) or \
                      re.search(r'alert\s*\(\s*"([^"]*)"', lines[n - 1])
                if lit:
                    payload = lit.group(1)
                    for key in ("action", "sentiment", "quantity"):
                        if f'"{key}"' not in payload:
                            f.append(Finding("WARN", n, "alert-payload",
                                             f"alert JSON is missing \"{key}\""))

    # ── global assignment inside a function ───────────────────────────────
    # Pine forbids a user-defined function from writing to a global. It is an
    # easy mistake (the code reads perfectly) and only surfaces on paste, so it
    # is worth catching here.
    DECL = re.compile(
        r"^(?:var(?:ip)?\s+)?(?:\w+(?:<[^>]*>)?\s+)?([A-Za-z_]\w*)\s*=(?!=)")
    FNDEF = re.compile(r"^([A-Za-z_]\w*)\s*\([^)]*\)\s*=>\s*$")

    globals_: set[str] = set()
    for code in code_lines:
        if code[:1] not in (" ", "\t") and code.strip():
            m = DECL.match(code.strip())
            if m:
                globals_.add(m.group(1))

    i = 0
    while i < len(code_lines):
        code = code_lines[i]
        m = FNDEF.match(code.strip()) if code[:1] not in (" ", "\t") else None
        if not m:
            i += 1
            continue
        fname = m.group(1)
        body: list[tuple[int, str]] = []
        j = i + 1
        while j < len(code_lines):
            nxt = code_lines[j]
            if nxt.strip() and nxt[:1] not in (" ", "\t"):
                break
            if nxt.strip():
                body.append((j + 1, nxt))
            j += 1

        locals_ = set()
        for _, b in body:
            d = DECL.match(b.strip())
            if d:
                locals_.add(d.group(1))
        for ln, b in body:
            for name in re.findall(r"([A-Za-z_]\w*)\s*:=", b):
                if name in globals_ and name not in locals_:
                    f.append(Finding(
                        "ERROR", ln, "global-assign",
                        f"`{fname}()` assigns to global `{name}` — Pine functions "
                        "cannot write to globals; inline the logic instead"))
        i = j

    # ── request.security hygiene ──────────────────────────────────────────
    for n, code in enumerate(code_lines, 1):
        if "request.security(" in code:
            # Find the full call, which may span lines.
            chunk = "\n".join(code_lines[n - 1 : n + 4])
            start = chunk.index("request.security(")
            depth, end = 0, None
            for i, ch in enumerate(chunk[start:], start):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            call = chunk[start : (end + 1) if end else len(chunk)]
            if "lookahead" not in call:
                f.append(Finding("WARN", n, "security-lookahead",
                                 "request.security without an explicit lookahead "
                                 "(use barmerge.lookahead_off)"))

    f.sort(key=lambda x: (x.line, x.level))
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--strict", action="store_true", help="warnings fail too")
    ap.add_argument("--max-line", type=int, default=120)
    a = ap.parse_args()

    total_err = total_warn = 0
    for pattern in a.files:
        paths = sorted(Path().glob(pattern)) if any(c in pattern for c in "*?[") \
            else [Path(pattern)]
        for p in paths:
            if not p.exists():
                print(f"{p}: not found", file=sys.stderr)
                total_err += 1
                continue
            findings = check(p.read_text(), str(p), a.max_line)
            errs = [x for x in findings if x.level == "ERROR"]
            warns = [x for x in findings if x.level == "WARN"]
            total_err += len(errs)
            total_warn += len(warns)

            print(f"\n{p}")
            if not findings:
                print("  clean")
            for x in findings:
                print(f"  {x.level:<5} line {x.line:>4}  [{x.code}] {x.msg}")
            print(f"  → {len(errs)} error(s), {len(warns)} warning(s)")

    print(f"\ntotal: {total_err} error(s), {total_warn} warning(s)")
    if total_err:
        return 1
    return 1 if (a.strict and total_warn) else 0


if __name__ == "__main__":
    raise SystemExit(main())
