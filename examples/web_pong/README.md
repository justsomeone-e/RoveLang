# Rove Web Pong

The game state, physics, keyboard dispatch, animation loop, and Canvas calls are
implemented in `pong.rove`. The generated ABI v1 runtime is the only JavaScript
bridge; `index.html` only loads the generated module and invokes `pong_start`.

```bash
rove bundle pong.rove --output dist --package
python -m http.server 8000
```

Open `http://localhost:8000` and use W/S to move the paddle.
