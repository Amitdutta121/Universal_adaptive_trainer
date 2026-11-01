"""Record a line-by-line trace (line, variables, heap objects, output so far) of small programs,
the way the lesson 'trace' and 'memory' blocks show them. Python Tutor-style: names point at
object ids, so aliasing is visible."""
import sys, io, json, contextlib

def trace(code):
    steps, out = [], io.StringIO()
    lines = code.split("\n")
    def snap(frame, line):
        heap, names = {}, {}
        def oid(v):
            k = f"o{id(v) % 100000}"
            if isinstance(v, (list, dict, tuple, set)) and k not in heap:
                heap[k] = {"type": type(v).__name__, "value": repr(v)}
            return k
        for n, v in frame.f_locals.items():
            if n.startswith("__") or callable(v) or type(v).__name__ == "module":
                continue
            names[n] = {"ref": oid(v)} if isinstance(v, (list, dict, tuple, set)) else {"value": repr(v)}
        # renumber object ids o1, o2 … in first-seen order so they're stable
        ren = {}
        for n in names.values():
            if "ref" in n and n["ref"] not in ren: ren[n["ref"]] = f"o{len(ren) + 1}"
        names = {k: ({"ref": ren[v["ref"]]} if "ref" in v else v) for k, v in names.items()}
        heap = {ren[k]: v for k, v in heap.items() if k in ren}
        steps.append({"line": line, "names": names, "heap": heap, "out": out.getvalue()})
    def tr(frame, event, arg):
        if frame.f_code.co_filename != "<lesson>": return tr
        if event == "line": snap(frame, frame.f_lineno)
        return tr
    g = {}
    with contextlib.redirect_stdout(out):
        sys.settrace(tr)
        try: exec(compile(code, "<lesson>", "exec"), g)
        finally: sys.settrace(None)
    # final state after the last line
    class F: pass
    f = F(); f.f_locals = g
    snap(f, None)
    return steps

progs = {
  "aliasing": "groceries = ['eggs', 'milk']\nshared = groceries\nshared.append('bread')\ncopy = groceries[:]\ncopy.append('jam')\nprint(groceries)\nprint(copy)",
  "range_loop": "total = 0\nfor price in range(2, 8, 2):\n    total += price\nprint(total)",
}
res = {k: {"code": v, "steps": trace(v)} for k, v in progs.items()}
json.dump(res, open(sys.argv[1], "w"), indent=1)
for k, v in res.items():
    print(k, len(v["steps"]), "steps; final out:", repr(v["steps"][-1]["out"]))
    print("  last:", v["steps"][-1]["names"], v["steps"][-1]["heap"])
