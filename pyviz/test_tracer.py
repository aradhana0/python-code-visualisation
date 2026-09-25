import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server import run_trace  # noqa: E402
from tracer import Tracer, trace  # noqa: E402


def frame_vars(step, index=-1):
    frame = step["stack"][index]
    heap = {int(k): v for k, v in step["heap"].items()}
    return {name: Tracer.render(enc, heap) for name, enc in frame["vars"]}


class TracerTests(unittest.TestCase):
    def test_line_steps_and_variables(self):
        res = trace("x = 1\ny = x + 1\n")
        self.assertIsNone(res["error"])
        self.assertEqual([s["line"] for s in res["steps"] if s["event"] == "line"], [1, 2])
        self.assertEqual(frame_vars(res["steps"][-1]), {"x": "1", "y": "2"})

    def test_call_stack_grows_with_recursion(self):
        code = "def f(n):\n    if n == 0:\n        return 0\n    return f(n - 1)\n\nf(2)\n"
        res = trace(code)
        depths = [len(s["stack"]) for s in res["steps"]]
        self.assertEqual(max(depths), 4)  # global + f(2) + f(1) + f(0)
        calls = [s for s in res["steps"] if s["event"] == "call"]
        self.assertEqual([frame_vars(s)["n"] for s in calls], ["2", "1", "0"])
        returns = [s for s in res["steps"] if s["event"] == "return" and len(s["stack"]) > 1]
        self.assertTrue(all(s["returnValue"] == {"p": "0", "t": "int"} for s in returns))

    def test_effects_report_new_changed_and_output(self):
        res = trace("a = [1]\na.append(2)\nprint(a)\nb = 0\n")
        effects = [e for s in res["steps"] for e in s["effects"]]
        kinds = {(e["kind"], e.get("name")) for e in effects}
        self.assertIn(("new", "a"), kinds)
        self.assertIn(("changed", "a"), kinds)
        self.assertIn(("mutated", None), kinds)
        self.assertIn(("output", None), kinds)
        changed = next(e for e in effects if e["kind"] == "changed")
        self.assertEqual((changed["old"], changed["value"]), ("[1]", "[1, 2]"))

    def test_aliases_share_heap_object(self):
        res = trace("a = [1, 2]\nb = a\nc = list(a)\n")
        last = res["steps"][-1]
        refs = dict(last["stack"][0]["vars"])
        self.assertEqual(refs["a"], refs["b"])
        self.assertNotEqual(refs["a"], refs["c"])

    def test_instances_and_cycles(self):
        code = ("class Node:\n    def __init__(self, v):\n        self.v = v\n        self.next = self\n\n"
                "n = Node(5)\nd = {}\nd['self'] = d\n")
        res = trace(code)
        self.assertIsNone(res["error"])
        values = frame_vars(res["steps"][-1])
        self.assertEqual(values["n"], "Node(v=5, next=...)")
        self.assertEqual(values["d"], "{'self': {...}}")

    def test_uncaught_exception(self):
        res = trace("x = 1\ny = x / 0\n")
        self.assertEqual(res["error"]["type"], "ZeroDivisionError")
        self.assertEqual(res["error"]["line"], 2)
        final = res["steps"][-1]
        self.assertEqual(final["event"], "uncaught_exception")
        self.assertIn("division by zero", final["exception"])

    def test_syntax_error(self):
        res = trace("def broken(:\n    pass\n")
        self.assertEqual(res["steps"], [])
        self.assertEqual(res["error"]["type"], "SyntaxError")
        self.assertEqual(res["error"]["line"], 1)

    def test_step_limit_stops_infinite_loop(self):
        res = trace("while True:\n    pass\n", max_steps=50)
        self.assertTrue(res["truncated"])
        self.assertEqual(len(res["steps"]), 50)

    def test_input_uses_provided_lines(self):
        res = trace("name = input('Name? ')\nprint('hi', name)\n", stdin="Ada")
        self.assertIsNone(res["error"])
        self.assertEqual(res["steps"][-1]["stdout"], "Name? Ada\nhi Ada\n")

    def test_input_without_lines_raises_eoferror(self):
        res = trace("input()\n")
        self.assertEqual(res["error"]["type"], "EOFError")


class ServerTests(unittest.TestCase):
    def test_subprocess_round_trip(self):
        res = run_trace("import sys\nsys.__stdout__.write('noise')\nx = 3\n")
        self.assertIsNone(res["error"])
        self.assertEqual(frame_vars(res["steps"][-1]), {"x": "3"})


if __name__ == "__main__":
    unittest.main()
