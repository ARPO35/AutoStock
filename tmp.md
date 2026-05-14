# Unfinished Notes

- Backend health was restored after restarting the local server: `GET http://127.0.0.1:8000/api/health` returned `{"status":"ok","version":"0.1.0"}`.
- The target backend test set passed before the interruption: `.venv\Scripts\python.exe -m pytest tests/test_market.py tests/test_mvp.py tests/test_view.py tests/test_replay_clock.py` reported `54 passed`.
- Reload validation is not fully closed. A reload was triggered and health still responded, but `pytemp/uvicorn.err.log` showed `ASGI 'lifespan' protocol appears unsupported` and only logged `Reloading...` without a clean shutdown/startup completion sequence.
- A direct follow-up command was started to force uvicorn lifespan mode with `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8765 --lifespan on`, but the user interrupted the turn before it completed.
- Follow-up should confirm that the production entrypoint `app.main:app` runs lifespan shutdown under uvicorn reload, or adjust the lazy ASGI wrapper so uvicorn reliably treats it as ASGI3 with lifespan support.
