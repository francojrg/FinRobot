"""
Robustere Tool-Aufrufe fuer AutoGen-Agenten (vor allem lange Build-Aufrufe mit vielen Textfeldern).

Beobachtet im Komplettlauf (Haiku ueber OpenRouter): bei sehr langen Argumenten
  a) bricht das JSON nach einem fertigen Textfeld ab ("Expecting ',' delimiter" am Ende der Zeichenkette),
  b) rutscht die native XML-Schreibweise des Modells in einen Textwert ("...</parameter>", "<parameter name=...>"),
     sodass spaetere Argumente fehlen ("missing 3 required positional arguments").
Das Modell schickte dann immer wieder den kompletten, gleich langen Aufruf und scheiterte erneut.

Abhilfe (installiert sich in ConversableAgent.execute_function, die Tools selbst bleiben unveraendert):
  1. abgeschnittenes JSON schliessen (offene Zeichenketten, Listen, Objekte), XML-Reste herausschneiden und
     als Argumente lesen;
  2. fehlen Pflichtargumente, werden die erhaltenen Argumente je Agent und Tool zwischengespeichert und das Modell
     gebeten, das Tool erneut NUR mit den fehlenden Argumenten aufzurufen; beim naechsten Aufruf wird zusammengefuehrt.
So werden die Folgeaufrufe kurz und laufen durch.
"""
import inspect
import json
import re

_DRAFTS = {}
_XML_TAG = re.compile(r'<parameter name=\\?"(\w+)\\?">|</parameter>|</?(\w+)>')


def close_json(s):
    """Abgeschnittenes JSON schliessen: offene Zeichenkette, dann offene Listen/Objekte in umgekehrter Reihenfolge."""
    stack, in_str, esc = [], False, False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()
    out = s + ('"' if in_str else "")
    out = re.sub(r"[,:\s]+$", "", out)
    if out.endswith('"') and stack and stack[-1] == "}":
        # endet mit einem Schluessel ohne Wert ({"a": 1, "b") -> Schluessel entfernen
        m = re.search(r',\s*"[^"]*"$', out)
        if m and not re.search(r':\s*"[^"]*"$', out):
            out = out[:m.start()]
    return out + "".join(reversed(stack))


def parse_args(raw):
    """JSON-Argumente lesen, notfalls abgeschnittenes JSON schliessen. Rueckgabe: (dict oder None, repariert?)."""
    if isinstance(raw, dict):
        return raw, False
    try:
        v = json.loads(raw)
        return (v if isinstance(v, dict) else None), False
    except Exception:
        pass
    try:
        v = json.loads(close_json(raw.strip()))
        return (v if isinstance(v, dict) else None), True
    except Exception:
        return None, False


def strip_xml(args, params):
    """XML-Reste in Textwerten entfernen; '<parameter name="k">v</parameter>' bzw. '<k>v</k>' werden zu Argumenten."""
    extra, changed = {}, False
    for k, v in list(args.items()):
        if not isinstance(v, str):
            continue
        m = re.search(r'</parameter>|<parameter name=|</(' + "|".join(map(re.escape, params)) + r')>', v) if params else None
        if not m:
            continue
        head, tail = v[:m.start()], v[m.start():]
        args[k] = _maybe_json(re.sub(r"(\\n|\s)+$", "", head), k, params)
        changed = True
        for mm in re.finditer(r'<parameter name=\\?"(\w+)\\?">(.*?)(?:</parameter>|$)', tail, re.S):
            extra.setdefault(mm.group(1), mm.group(2))
        for p in params:
            mm = re.search(r"<" + re.escape(p) + r">(.*?)</" + re.escape(p) + ">", tail, re.S)
            if mm:
                extra.setdefault(p, mm.group(1))
    for k, v in extra.items():
        if k in params and k not in args:
            args[k] = _maybe_json(v.replace('\\"', '"').replace("\\n", "\n").strip(), k, params)
    return changed or bool(extra)


def _maybe_json(v, k, params):
    """Listen/Objekte, die als Text ankamen, wieder einlesen (nur fuer Argumente mit Listen-/Dict-Typ)."""
    ann = str(params.get(k, "")) if isinstance(params, dict) else ""
    if isinstance(v, str) and ("List" in ann or "list" in ann or "dict" in ann or "Dict" in ann):
        try:
            return json.loads(v)
        except Exception:
            try:
                return json.loads(close_json(v))
            except Exception:
                return v
    return v


def _params(func):
    try:
        sig = inspect.signature(func)
    except Exception:
        return None, None
    return sig, {n: p.annotation for n, p in sig.parameters.items()}


def install():
    try:
        from autogen import ConversableAgent
    except Exception:
        return False
    if getattr(ConversableAgent, "_tool_repair_installed", False):
        return True
    orig = ConversableAgent.execute_function

    def execute_function(self, func_call, verbose=False):
        name = func_call.get("name", "")
        func = self._function_map.get(name)
        if func is None:
            return orig(self, func_call, verbose)
        raw = self._format_json_str(func_call.get("arguments", "{}") or "{}")
        args, repaired = parse_args(raw)
        if args is None:
            return orig(self, func_call, verbose)
        sig, params = _params(func)
        if sig is None:
            return orig(self, func_call, verbose)
        cleaned = strip_xml(args, params)
        key = (id(self), name)
        merged = {**_DRAFTS.get(key, {}), **args}
        if not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            dropped = [k for k in merged if k not in sig.parameters]   # erfundene Argumente (z. B. 'headline_placeholder')
            if dropped and (key in _DRAFTS or repaired or cleaned):
                merged = {k: v for k, v in merged.items() if k in sig.parameters}
        try:
            sig.bind(**merged)
        except TypeError as e:
            missing = [n for n, p in sig.parameters.items()
                       if p.default is inspect.Parameter.empty and n not in merged
                       and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
            unknown = [k for k in merged if k not in sig.parameters]
            if missing and not unknown:
                _DRAFTS[key] = merged
                note = ("Your previous call arrived incomplete" + (" (the JSON was cut off)" if repaired else "")
                        + (" (XML tags inside a text value were removed)" if cleaned else "") + ". ")
                content = (f"Error: {note}Received and stored: {', '.join(sorted(merged))}. Missing: {', '.join(missing)}. "
                           f"Call {name} again with ONLY the missing argument(s) {', '.join(missing)}; the stored "
                           "arguments are added automatically. Pass lists and objects as JSON arrays/objects, not "
                           "as strings, and do not use XML tags.")
                return False, {"name": name, "role": "function", "content": content}
            return orig(self, func_call, verbose)
        _DRAFTS.pop(key, None)
        if repaired or cleaned or merged != args:
            func_call = {**func_call, "arguments": json.dumps(merged)}
        return orig(self, func_call, verbose)

    ConversableAgent.execute_function = execute_function
    ConversableAgent._tool_repair_installed = True
    return True
