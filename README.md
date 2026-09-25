# Python Code Visualiser

Step through a Python program line by line and see what each line does:

- **Line pointers.** A green arrow marks the line that just ran and a red arrow marks the next line to run. Exceptions get a ✖.
- **Call stack.** Each function call pushes a frame with its local variables. Frames are popped when the function returns, and the return value is shown.
- **Objects (heap).** Lists, tuples, sets, dicts, class instances, classes and functions are drawn as boxes. Arrows run from variables to the objects they point to, so aliasing (`b = a`) and shared or cyclic structures are visible.
- **Effects.** A "What happened" panel explains each step, for example new variables, `x changed: 1 → 2`, objects modified in place, printed output, calls, returns and exceptions. Changed variables are highlighted and mutated objects are outlined.
- **Playback.** You can step forward and back, jump to the first or last step, drag the slider, or autoplay at several speeds.
- **Examples and input.** There are ten example programs, covering recursion, aliasing, sorting, linked lists, closures, generators, exceptions and more. You can also supply lines for `input()`.

## Run it

The app needs Python 3.8+ and has no dependencies.

```bash
cd pyviz
python3 server.py            # then open http://127.0.0.1:8000
python3 server.py --port 9000
```

Keyboard: `←` / `→` step, `space` play/pause, `Home` / `End` jump, `Ctrl+Enter` in the editor visualises.

## How it works

```
pyviz/
├── tracer.py        # runs code under sys.settrace, records every step as JSON
├── server.py        # stdlib HTTP server: static files + POST /api/trace
├── test_tracer.py   # unit tests
└── static/          # frontend (plain HTML/CSS/JS, no build step)
    ├── index.html
    ├── style.css
    ├── app.js
    └── examples.js
```

1. The browser posts the code to `/api/trace`.
2. The server runs `tracer.py` in a separate Python process with a 10 s timeout, a CPU limit and a memory limit.
3. The tracer records a snapshot of the program state at every `line`, `call`, `return` and `exception` event. A snapshot holds the stack frames and their variables, the reachable objects, stdout and a diff against the previous step. Runs stop after 1000 steps, so infinite loops are safe.
4. The frontend renders the snapshot for the current step and draws the pointer arrows as SVG.

You can also use the tracer directly:

```bash
echo '{"code": "x = [1, 2]\nx.append(3)\n"}' | python3 pyviz/tracer.py
```

## Tests

```bash
cd pyviz && python3 -m unittest -v
```

## Security note

The code you visualise is real Python running on the machine that hosts the server. The limits stop runaway programs, not malicious ones. By default the server listens only on `127.0.0.1`. Do not expose it to the internet without proper sandboxing.
