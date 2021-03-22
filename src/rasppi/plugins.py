import logging
import pathlib
import os, importlib
logger = logging.getLogger("plugins")

#pathlib.Path(__file__).parent.absolute()

def load_plugins(subdir):
    plugins = []
    origdir = pathlib.Path(__file__).parent.absolute()
    plugin_dir = origdir / "auth"
    for module in os.listdir(plugin_dir):
        try:
            m = importlib.import_module(f"auth.{module[:-3]}")
        except ModuleNotFoundError as mnfe:
            pass  # don't worry about it
    from auth.auth_plugin import AuthPlugin
    for sc in AuthPlugin.__subclasses__():
        plugins.append(sc())
    return plugins