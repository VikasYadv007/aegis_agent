"""Windowed application entry point and diagnostic logging."""

import ctypes
import importlib
import logging
import os
from logging.handlers import RotatingFileHandler
import sys
from aegis_core import data_dir


def main():
    handler = RotatingFileHandler(
        data_dir() / "aegis.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # Windowed executables have no console streams; some GUI dependencies write diagnostics.
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if "--smoke-test" in sys.argv:
        from aegis_smoke import run

        run(sys.argv[sys.argv.index("--smoke-test") + 1])
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, "Local\\AegisFileOrganizer-1")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        ctypes.windll.user32.MessageBoxW(
            None, "Aegis is already running. Check your taskbar.", "Aegis", 64
        )
        kernel.CloseHandle(mutex)
        return
    try:
        module = importlib.import_module("aegis_app")
        app = module.AegisAgentApp()

        def report_error(kind, value, traceback):
            logging.error("UI error", exc_info=(kind, value, traceback))
            module.messagebox.showerror(
                "Aegis", f"{value}\n\nDetails: {data_dir() / 'aegis.log'}"
            )

        app.report_callback_exception = report_error
        app.mainloop()
    finally:
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Startup failed")
        if "--smoke-test" not in sys.argv:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"Aegis could not start. See {data_dir() / 'aegis.log'}",
                "Aegis",
                16,
            )
        sys.exit(1)
