"""Execution tracer for the Python code visualiser.

Runs a snippet of user code under ``sys.settrace`` and records a list of
*steps*.  Each step is a JSON-serialisable snapshot of the program state:

* the line about to execute and the kind of event (line/call/return/exception)
* the call stack (outermost frame first) with each frame's local variables
* the heap: every list/dict/object reachable from those variables
* everything printed so far
* the *effects* of the previous step (new/changed/deleted variables,
  mutated objects, printed output, calls and returns)

Usage as a script: JSON ``{"code": "...", "stdin": "..."}`` on stdin,
JSON trace on stdout.  The server runs it in a subprocess with a timeout.
"""

import builtins
import inspect
import io
import json
import os
import sys
import types

USER_FILE = "<main>"
MAX_STEPS = 1000
MAX_ITEMS = 50          # max elements shown per container
MAX_DEPTH = 8           # max nesting depth when encoding objects
MAX_STR = 200           # max length of an inline string/repr
MAX_RENDER = 2000       # max length of a rendered value used for diffing
MAX_STDOUT = 20000      # max captured output characters

INLINE_TYPES = (int, float, complex, bool, str, bytes, type(None))
SEQ_TYPES = {list: "list", tuple: "tuple", set: "set", frozenset: "frozenset"}


class StepLimitExceeded(BaseException):
    """Raised inside user code once MAX_STEPS have been recorded."""


def _short(text, limit=MAX_STR):
    return text if len(text) <= limit else text[: limit - 3] + "..."


class Tracer:
    def __init__(self, code, stdin="", max_steps=MAX_STEPS):
        self.code = code
        self.max_steps = max_steps
        self.steps = []
        self.stdout = io.StringIO()
        self.stdin_lines = stdin.splitlines()
        self.truncated = False
        # Stable, small ids for objects and frames.  Objects are kept alive
        # so that CPython cannot reuse an id() for a different object.
        self._obj_ids = {}
        self._keepalive = []
        self._frame_ids = {}
        self._exc_frames = set()
        self._last_exception_step = None

    # ------------------------------------------------------------------ ids
    def _oid(self, obj):
        key = id(obj)
        if key not in self._obj_ids:
            self._obj_ids[key] = len(self._obj_ids) + 1
            self._keepalive.append(obj)
        return self._obj_ids[key]

    def _fid(self, frame):
        if frame not in self._frame_ids:
            self._frame_ids[frame] = len(self._frame_ids) + 1
        return self._frame_ids[frame]

    # ------------------------------------------------------------- encoding
    def _encode(self, value, heap, depth=0):
        if isinstance(value, INLINE_TYPES):
            return {"p": _short(repr(value)), "t": type(value).__name__}
        if isinstance(value, (types.ModuleType, types.BuiltinFunctionType)) or depth > MAX_DEPTH:
            return {"p": _short(repr(value)), "t": type(value).__name__}

        oid = self._oid(value)
        if oid not in heap:
            heap[oid] = None  # placeholder: guards against cycles
            heap[oid] = self._encode_object(value, heap, depth + 1)
        return {"r": oid}

    def _encode_object(self, value, heap, depth):
        enc = lambda v: self._encode(v, heap, depth)  # noqa: E731

        kind = SEQ_TYPES.get(type(value))
        if kind:
            items = list(value)
            return {
                "t": kind,
                "items": [enc(v) for v in items[:MAX_ITEMS]],
                "more": max(0, len(items) - MAX_ITEMS),
            }
        if isinstance(value, dict):
            pairs = list(value.items())
            return {
                "t": "dict",
                "items": [[enc(k), enc(v)] for k, v in pairs[:MAX_ITEMS]],
                "more": max(0, len(pairs) - MAX_ITEMS),
            }
        if isinstance(value, (types.FunctionType, types.MethodType)):
            func = value.__func__ if isinstance(value, types.MethodType) else value
            try:
                sig = str(inspect.signature(func))
            except (TypeError, ValueError):
                sig = "(...)"
            return {"t": "function", "name": func.__qualname__, "sig": sig}
        if isinstance(value, type):
            attrs = [
                [k, enc(v)]
                for k, v in vars(value).items()
                if not (k.startswith("__") and k.endswith("__")) or isinstance(v, types.FunctionType)
            ]
            return {"t": "class", "name": value.__name__, "attrs": attrs[:MAX_ITEMS]}
        if hasattr(value, "__dict__") and isinstance(getattr(value, "__dict__", None), dict):
            attrs = [[k, enc(v)] for k, v in vars(value).items()]
            return {"t": "instance", "name": type(value).__name__, "attrs": attrs[:MAX_ITEMS]}
        # Anything else (range, generator, iterator, ...) is shown by repr.
        try:
            text = repr(value)
        except Exception:  # pragma: no cover - defensive against odd __repr__
            text = "<%s object>" % type(value).__name__
        return {"t": "other", "name": type(value).__name__, "repr": _short(text)}

    # ------------------------------------------------------------ rendering
    @staticmethod
    def render(enc, heap, seen=None):
        """Render an encoded value back to a Python-like string."""
        if "p" in enc:
            return enc["p"]
        oid = enc["r"]
        obj = heap.get(oid)
        if obj is None:
            return "..."
        seen = seen or set()
        if oid in seen:
            return {"list": "[...]", "dict": "{...}"}.get(obj["t"], "...")
        seen = seen | {oid}
        r = lambda e: Tracer.render(e, heap, seen)  # noqa: E731
        t = obj["t"]
        more = ", ..." if obj.get("more") else ""
        if t in ("list", "tuple", "set", "frozenset"):
            inner = ", ".join(r(e) for e in obj["items"]) + more
            if t == "list":
                return "[%s]" % inner
            if t == "tuple":
                return "(%s)" % (inner + ("," if len(obj["items"]) == 1 else ""))
            if not obj["items"]:
                return "set()" if t == "set" else "frozenset()"
            return "{%s}" % inner if t == "set" else "frozenset({%s})" % inner
        if t == "dict":
            return "{%s}" % (", ".join("%s: %s" % (r(k), r(v)) for k, v in obj["items"]) + more)
        if t == "function":
            return "<function %s%s>" % (obj["name"], obj["sig"])
        if t == "class":
            return "<class %s>" % obj["name"]
        if t == "instance":
            return "%s(%s)" % (obj["name"], ", ".join("%s=%s" % (k, r(v)) for k, v in obj["attrs"]))
        return obj["repr"]

    # -------------------------------------------------------------- snapshot
    def _user_frames(self, frame):
        frames = []
        while frame is not None:
            if frame.f_code.co_filename == USER_FILE:
                frames.append(frame)
            frame = frame.f_back
        frames.reverse()
        return frames

    @staticmethod
    def _visible_vars(frame, is_module):
        names = frame.f_globals if is_module else frame.f_locals
        out = []
        for name, value in list(names.items()):
            if name.startswith("__") and name.endswith("__"):
                continue
            if is_module and isinstance(value, types.ModuleType):
                continue
            out.append((name, value))
        return out

    def _snapshot(self, frame, event, arg):
        heap = {}
        stack = []
        user_frames = self._user_frames(frame)
        for f in user_frames:
            is_module = f.f_code.co_name == "<module>"
            entry = {
                "id": self._fid(f),
                "name": "Global frame" if is_module else getattr(f.f_code, "co_qualname", f.f_code.co_name),
                "func": f.f_code.co_name,
                "line": f.f_lineno,
                "vars": [[n, self._encode(v, heap)] for n, v in self._visible_vars(f, is_module)],
            }
            stack.append(entry)

        step = {
            "event": event,
            "line": frame.f_lineno,
            "stack": stack,
            "heap": {str(k): v for k, v in heap.items()},
            "stdout": self.stdout.getvalue()[:MAX_STDOUT],
        }
        if event == "return":
            if frame in self._exc_frames:
                step["unwinding"] = True
            else:
                step["returnValue"] = self._encode(arg, heap)
                step["heap"] = {str(k): v for k, v in heap.items()}
        if event == "exception":
            exc_type, exc_value, _ = arg
            step["exception"] = "%s: %s" % (exc_type.__name__, exc_value) if str(exc_value) else exc_type.__name__
        return step

    # ------------------------------------------------------------- effects
    def _rendered_vars(self, step):
        heap = {int(k): v for k, v in step["heap"].items()}
        out = {}
        for fr in step["stack"]:
            out[fr["id"]] = {
                name: _short(self.render(enc, heap), MAX_RENDER) for name, enc in fr["vars"]
            }
        return out, heap

    def _compute_effects(self, prev, cur):
        effects = []
        prev_vars, prev_heap = self._rendered_vars(prev)
        cur_vars, cur_heap = self._rendered_vars(cur)
        names = {fr["id"]: fr["name"] for fr in cur["stack"]}
        names.update({fr["id"]: fr["name"] for fr in prev["stack"]})

        for fid, vars_now in cur_vars.items():
            if fid not in prev_vars:
                continue  # a brand new frame: reported as a call
            before = prev_vars[fid]
            for name, val in vars_now.items():
                if name not in before:
                    effects.append({"kind": "new", "frame": fid, "frameName": names[fid],
                                    "name": name, "value": _short(val, 80)})
                elif before[name] != val:
                    effects.append({"kind": "changed", "frame": fid, "frameName": names[fid],
                                    "name": name, "old": _short(before[name], 80),
                                    "value": _short(val, 80)})
            for name in before:
                if name not in vars_now:
                    effects.append({"kind": "deleted", "frame": fid, "frameName": names[fid],
                                    "name": name})

        new_frames = [fr for fr in cur["stack"] if fr["id"] not in prev_vars]
        for fr in new_frames:
            args = ", ".join("%s=%s" % (n, _short(v, 40)) for n, v in cur_vars[fr["id"]].items())
            effects.append({"kind": "call", "frame": fr["id"], "frameName": fr["name"], "args": args})
        for fr in prev["stack"]:
            if fr["id"] not in cur_vars:
                effects.append({"kind": "popped", "frame": fr["id"], "frameName": fr["name"]})

        mutated = []
        for key, obj in cur_heap.items():
            if key in prev_heap and prev_heap[key] != obj:
                mutated.append(key)
        if mutated:
            effects.append({"kind": "mutated", "objects": mutated})

        printed = cur["stdout"][len(prev["stdout"]):]
        if printed:
            effects.append({"kind": "output", "text": printed})
        return effects

    # ---------------------------------------------------------------- trace
    def _record(self, frame, event, arg):
        if len(self.steps) >= self.max_steps:
            self.truncated = True
            raise StepLimitExceeded()
        step = self._snapshot(frame, event, arg)
        step["effects"] = self._compute_effects(self.steps[-1], step) if self.steps else []
        self.steps.append(step)
        if event == "exception":
            self._last_exception_step = step

    def _trace(self, frame, event, arg):
        if frame.f_code.co_filename != USER_FILE:
            return None
        if self.truncated:
            raise StepLimitExceeded()
        is_module = frame.f_code.co_name == "<module>"
        self._fid(frame)
        if event == "call":
            self._exc_frames.discard(frame)
            if not is_module:
                self._record(frame, "call", arg)
        elif event == "line":
            self._exc_frames.discard(frame)
            self._record(frame, "line", arg)
        elif event == "exception":
            self._record(frame, "exception", arg)
            self._exc_frames.add(frame)
        elif event == "return":
            self._record(frame, "return", arg)
        return self._trace

    def _input(self, prompt=""):
        self.stdout.write(str(prompt))
        if not self.stdin_lines:
            raise EOFError("EOF when reading a line (add lines to the input box)")
        line = self.stdin_lines.pop(0)
        self.stdout.write(line + "\n")
        return line

    def run(self):
        try:
            compiled = compile(self.code, USER_FILE, "exec")
        except SyntaxError as exc:
            return {
                "steps": [],
                "error": {"type": type(exc).__name__, "message": exc.msg,
                          "line": exc.lineno, "offset": exc.offset},
                "truncated": False,
            }

        user_builtins = dict(vars(builtins))
        user_builtins["input"] = self._input
        user_globals = {"__name__": "__main__", "__builtins__": user_builtins}

        error = None
        real_stdout, real_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = self.stdout
        sys.settrace(self._trace)
        try:
            exec(compiled, user_globals)
        except StepLimitExceeded:
            pass
        except BaseException as exc:  # user code raised
            error = {"type": type(exc).__name__, "message": str(exc)}
            tb = exc.__traceback__
            line = None
            while tb is not None:
                if tb.tb_frame.f_code.co_filename == USER_FILE:
                    line = tb.tb_lineno
                tb = tb.tb_next
            error["line"] = line
        finally:
            sys.settrace(None)
            sys.stdout, sys.stderr = real_stdout, real_stderr

        if error and self._last_exception_step is not None:
            final = dict(self._last_exception_step)
            final["event"] = "uncaught_exception"
            final["line"] = error["line"] or final["line"]
            final["exception"] = "%s: %s" % (error["type"], error["message"]) if error["message"] else error["type"]
            final["stdout"] = self.stdout.getvalue()[:MAX_STDOUT]
            final["effects"] = []
            self.steps.append(final)

        return {"steps": self.steps, "error": error, "truncated": self.truncated}


def trace(code, stdin="", max_steps=MAX_STEPS):
    return Tracer(code, stdin, max_steps).run()


def _limit_resources():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
        mem = 1 << 30
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    except (ImportError, ValueError, OSError):
        pass


def main():
    request = json.load(sys.stdin)
    # Keep a private handle to the real stdout and point fd 1 at /dev/null so
    # that user code writing to sys.__stdout__ cannot corrupt the JSON result.
    out = os.fdopen(os.dup(1), "w")
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    sys.stdin = io.StringIO("")
    _limit_resources()
    result = trace(request.get("code", ""), request.get("stdin", ""))
    json.dump(result, out)
    out.flush()


if __name__ == "__main__":
    main()
